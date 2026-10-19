"""Multi-model signal API and JSON CLI. No sizing, orders or broker connection."""
import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path

try:
    from .models import MODEL_VERSION, forecasts
except ImportError:
    from models import MODEL_VERSION, forecasts


def utc(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None or d.utcoffset().total_seconds()!=0:
        raise ValueError('Expected explicit UTC timestamp')
    return d


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


@dataclass(frozen=True)
class ModelConfig:
    bar_seconds: int = 300
    horizon_bars: int = 1
    min_bars: int = 64
    window_bars: int = 256
    weights: dict = field(default_factory=lambda:{'ou':1.0,'kalman':1.0,'return_ar':1.0})
    min_models: int = 2
    min_supporters: int = 2
    min_agreement: float = 2/3
    min_component_z: float = 0.25
    min_score: float = 0.20
    min_net_z: float = 0.50
    edge_buffer_bps: float = 0.5
    max_quote_age_seconds: float = 10.0
    max_bar_age_seconds: float = 450.0
    signal_ttl_seconds: float = 30.0
    max_vol_ratio: float = 3.0
    kalman_damping: float = 0.95
    ewma_decay: float = 0.94
    q_level: float = 0.05
    q_slope: float = 0.005
    measurement_noise: float = 0.5
    ar_ridge: float = 1.0

    def validate(self):
        ints=('bar_seconds','horizon_bars','min_bars','window_bars','min_models','min_supporters')
        for key in ints:
            if type(getattr(self,key)) is not int or getattr(self,key)<=0:
                raise ValueError('Invalid '+key)
        if self.min_bars<32 or self.window_bars<self.min_bars:
            raise ValueError('Require window_bars >= min_bars >= 32')
        if set(self.weights)!={'ou','kalman','return_ar'}:
            raise ValueError('Supply weights for all three models')
        for key,value in asdict(self).items():
            if isinstance(value,dict):
                if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in value.values()):
                    raise ValueError('Weights must be positive finite values')
            elif not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
                raise ValueError('Invalid '+key)
        if not 0<self.kalman_damping<1 or not 0<self.ewma_decay<1:
            raise ValueError('Damping and decay must be in (0,1)')
        if not 0<self.min_agreement<=1 or not 0<=self.min_score<=1:
            raise ValueError('Invalid score/agreement thresholds')
        if self.min_models>3 or self.min_supporters>3 or self.max_vol_ratio<=1:
            raise ValueError('Invalid ensemble gate')
        if min(self.measurement_noise,self.ar_ridge,self.max_quote_age_seconds,
               self.max_bar_age_seconds,self.signal_ttl_seconds)<=0:
            raise ValueError('Noise, ridge and freshness limits must be positive')
        return self


def prepare_bars(bars,symbol,decision,config):
    """Select actually available closed bars, reject duplicates, use last segment."""
    config.validate(); decision=utc(decision)
    selected={}; basis=None
    for p in bars:
        if p['symbol']!=symbol:
            continue
        opened,available=utc(p['timestamp_utc']),utc(p['available_utc'])
        if available>decision or opened+timedelta(seconds=config.bar_seconds)>decision:
            continue
        if p.get('complete') is not True or available<opened+timedelta(seconds=config.bar_seconds):
            raise ValueError('Incomplete candle or invalid availability')
        if int(opened.timestamp())%config.bar_seconds or opened.microsecond:
            raise ValueError('Candle is not aligned to bar_seconds')
        if p.get('price_basis') not in ('bid','ask','mid'):
            raise ValueError('Unknown price_basis')
        if basis is not None and basis!=p['price_basis']:
            raise ValueError('Mixed price bases')
        basis=p['price_basis']
        for k in ('open','high','low','close'):
            if isinstance(p[k],bool) or not isinstance(p[k],(int,float)) or not math.isfinite(p[k]) or p[k]<=0:
                raise ValueError('Invalid price')
        if not p['low']<=min(p['open'],p['close'])<=max(p['open'],p['close'])<=p['high']:
            raise ValueError('Invalid OHLC')
        if opened in selected and canonical(selected[opened])!=canonical(p):
            raise ValueError('Conflicting duplicate candle')
        selected[opened]=p
    ordered=sorted(selected)
    segment=[]
    for t in ordered:
        if segment and (t-utc(segment[-1]['timestamp_utc'])).total_seconds()!=config.bar_seconds:
            segment=[]
        segment.append(selected[t])
    return segment[-config.window_bars:]


def combine(components,config):
    active=[x for x in components if x['status']=='ready']
    if not active:
        return dict(expected_return=0.0,forecast_sd_return=0.0,score=0.0,
                    agreement=0.0,supporters=0,active_models=0)
    total=sum(config.weights[x['model']] for x in active)
    mu=sum(config.weights[x['model']]*x['expected_return'] for x in active)/total
    var=sum(config.weights[x['model']]*(x['forecast_sd_return']**2+(x['expected_return']-mu)**2) for x in active)/total
    score=sum(config.weights[x['model']]*math.tanh(x['mean_log_return']/math.sqrt(x['variance_log_return'])) for x in active)/total
    direction=1 if mu>0 else -1 if mu<0 else 0
    support=[x for x in active if direction*x['mean_log_return']>0 and abs(x['mean_log_return'])/math.sqrt(x['variance_log_return'])>=config.min_component_z]
    return dict(expected_return=mu,forecast_sd_return=math.sqrt(max(0,var)),score=score,
                agreement=sum(config.weights[x['model']] for x in support)/total,
                supporters=len(support),active_models=len(active))


def generate_signal(bars, *, symbol, decision_utc, quote=None, costs=None, config=None):
    """Return a versioned intent + diagnostics; never execute it.

    quote: symbol, timestamp_utc, bid, ask. costs: exit_spread_bps,
    round_trip_fees_bps, slippage_bps_per_side. Values are explicit estimates;
    signal generation is blocked when quote/cost metadata is absent.
    """
    cfg=(config or ModelConfig()).validate(); now=utc(decision_utc)
    bars=prepare_bars(bars,symbol,decision_utc,cfg)
    result=dict(schema_version=2,model_id=MODEL_VERSION,symbol=symbol,
        timestamp_utc=now.isoformat(),direction='no_trade',filter_passed=False,
        evidence='UNVALIDATED_RESEARCH_MODEL',parameters=asdict(cfg),components=[],
        history_bars=len(bars),reason='insufficient_history',
        expected_return=0.0,forecast_sd_return=0.0,score=0.0,agreement=0.0,
        supporters=0,active_models=0,trade_eligible=False)
    result['data_cutoff_utc']=(utc(bars[-1]['timestamp_utc'])+timedelta(seconds=cfg.bar_seconds)).isoformat() if bars else now.isoformat()
    cutoff=utc(result['data_cutoff_utc']); target=cutoff+timedelta(seconds=cfg.horizon_bars*cfg.bar_seconds)
    result.update(target_utc=target.isoformat(),horizon_seconds=max(0,(target-now).total_seconds()),
        expires_utc=min(now+timedelta(seconds=cfg.signal_ttl_seconds),target).isoformat())
    if quote is not None:
        if quote.get('symbol')!=symbol:
            raise ValueError('Quote symbol mismatch')
        bid,ask=quote['bid'],quote['ask']
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in (bid,ask)) or ask<bid:
            raise ValueError('Invalid bid/ask')
        age=(now-utc(quote['timestamp_utc'])).total_seconds()
        if age<0:raise ValueError('Future quote')
        result.update(bid=bid,ask=ask,quote_age_seconds=age)
    if len(bars)>=cfg.min_bars:
        prices=[p['close'] for p in bars]
        result['price_basis']=bars[-1]['price_basis']
        result['reference_price']=prices[-1]
        result['components']=[x.to_dict() for x in forecasts(prices,cfg)]
        r=[math.log(b/a) for a,b in zip(prices,prices[1:])]
        long=sum(x*x for x in r)/len(r)
        short=sum(x*x for x in r[-16:])/min(16,len(r))
        ratio=math.sqrt(short/long) if long>0 else 1.0
        result['regime']={'recent_to_window_vol_ratio':ratio,
                          'kind':'descriptive_volatility_ratio; not an HMM probability'}
        result.update(combine(result['components'],cfg))
        result['reason']='forecast_only_missing_quote_or_costs'
        if quote is not None:
            reference={'bid':bid,'ask':ask,'mid':(bid+ask)/2}[result['price_basis']]
            # Rebase each target-price distribution from last bar close to the
            # fresh quote on the SAME basis before applying today's cost hurdle.
            shift=math.log(prices[-1]/reference)
            for comp in result['components']:
                if comp['status']=='ready':
                    comp['bar_origin_mean_log_return']=comp['mean_log_return']
                    mu=comp['mean_log_return']+shift;v=comp['variance_log_return']
                    comp.update(mean_log_return=mu,mean_log_return_bps=mu*10000,
                        expected_return=math.expm1(mu+v/2),
                        forecast_sd_return=math.sqrt(math.expm1(v)*math.exp(2*mu+v)))
            result['reference_price']=reference
            result.update(combine(result['components'],cfg))
            if costs is not None:
                fields=('exit_spread_bps','round_trip_fees_bps','slippage_bps_per_side')
                if any(k not in costs or isinstance(costs[k],bool) or not isinstance(costs[k],(int,float)) or not math.isfinite(costs[k]) or costs[k]<0 for k in fields):
                    raise ValueError('Supply nonnegative finite cost estimates')
                entry_spread=(ask-bid)/reference*10000
                basis=result['price_basis'];long=result['expected_return']>0
                if basis=='bid':spread_cost=entry_spread if long else costs['exit_spread_bps']
                elif basis=='ask':spread_cost=costs['exit_spread_bps'] if long else entry_spread
                else:spread_cost=(entry_spread+costs['exit_spread_bps'])/2
                hurdle=spread_cost+costs['round_trip_fees_bps']+2*costs['slippage_bps_per_side']+cfg.edge_buffer_bps
                edge=abs(result['expected_return'])*10000-hurdle
                z=edge/max(1e-12,result['forecast_sd_return']*10000)
                result.update(cost_estimates=dict(costs),entry_spread_bps=entry_spread,
                              spread_cost_bps=spread_cost,cost_hurdle_bps=hurdle,
                              net_edge_bps=edge,net_edge_z=z)
                checks=[(now>=target,'forecast_target_elapsed'),
                    ((now-cutoff).total_seconds()>cfg.max_bar_age_seconds,'stale_bars'),
                    (age>cfg.max_quote_age_seconds,'stale_quote'),
                    (result['active_models']<cfg.min_models,'insufficient_active_models'),
                    (ratio>cfg.max_vol_ratio,'volatility_shock'),
                    (result['supporters']<cfg.min_supporters or result['agreement']+1e-12<cfg.min_agreement,'insufficient_agreement'),
                    (abs(result['score'])<cfg.min_score or result['score']*result['expected_return']<=0,'weak_or_conflicting_score'),
                    (edge<=0 or z<cfg.min_net_z,'below_cost_or_uncertainty_hurdle')]
                result['reason']=next((reason for failed,reason in checks if failed),'ensemble_signal')
                if result['reason']=='ensemble_signal':
                    result.update(direction='buy' if result['expected_return']>0 else 'sell',
                                  filter_passed=True,trade_eligible=True)
    identity={'version':MODEL_VERSION,'symbol':symbol,'decision':decision_utc,
        'config':asdict(cfg),'bars':bars,'quote':quote,'costs':costs}
    result['input_config_sha256']=hashlib.sha256(canonical(identity).encode()).hexdigest()
    result['signal_id']=MODEL_VERSION+'|'+symbol+'|'+result['input_config_sha256'][:24]
    result['intent']='entry_candidate' if result['trade_eligible'] else 'abstain'
    result['abstention_is_exit']=False
    # Reject non-finite values before handing anything to the external runner.
    canonical(result)
    return result


def telemetry_signal(result):
    """Explicit adapter for the existing journal. Keep full diagnostics separately."""
    try:
        from .telemetry import Signal
    except ImportError:
        from telemetry import Signal
    if 'bid' not in result or utc(result['expires_utc'])<=utc(result['timestamp_utc']):
        raise ValueError('Journal signal needs quote and a future validity deadline')
    fields=('signal_id','model_id','symbol','timestamp_utc','data_cutoff_utc',
            'expires_utc','direction','horizon_seconds','expected_return',
            'forecast_sd_return','filter_passed','reason','bid','ask')
    return Signal(**{k:result[k] for k in fields}).validate()


def read_bars(path):
    """Read JSON list/{bars:...} or the uploaded runs/records XLSX convention."""
    path=Path(path)
    if path.suffix.lower()=='.xlsx':
        import openpyxl  # optional, analysis adapter only
        w=openpyxl.load_workbook(path,read_only=True,data_only=True)
        try:
            it=iter(w['records'].values);h=next(it)
            out=[]
            for row in it:
                r=dict(zip(h,row))
                if r['kind']=='candles':out.append(json.loads(r['payload']))
            return out
        finally:w.close()
    data=json.loads(path.read_text())
    return data['bars'] if isinstance(data,dict) else data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bars',required=True);p.add_argument('--symbol',required=True)
    p.add_argument('--decision-utc',required=True);p.add_argument('--config')
    p.add_argument('--quote',help='Private JSON file; symbol/timestamp_utc/bid/ask')
    p.add_argument('--costs',help='Private JSON file; explicit bps estimates')
    a=p.parse_args();load=lambda path:json.loads(Path(path).read_text()) if path else None
    result=generate_signal(read_bars(a.bars),symbol=a.symbol,decision_utc=a.decision_utc,
        config=ModelConfig(**(load(a.config) or {})),quote=load(a.quote),costs=load(a.costs))
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
