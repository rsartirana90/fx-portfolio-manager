"""Chronological rolling forecast evaluation, NOT an execution backtest."""
import argparse
import csv
from dataclasses import asdict
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path

try:
    from .signals import ModelConfig, canonical, generate_signal, prepare_bars, read_bars, utc
    from .models import MODEL_VERSION
except ImportError:
    from signals import ModelConfig, canonical, generate_signal, prepare_bars, read_bars, utc
    from models import MODEL_VERSION


def evaluate(bars,config=None,availability='recorded'):
    cfg=(config or ModelConfig()).validate()
    if availability not in ('recorded','bar_close_assumption'):
        raise ValueError('Unknown availability mode')
    grouped={}
    for p in bars:
        p=dict(p)
        if availability=='bar_close_assumption':
            p['available_utc']=(utc(p['timestamp_utc'])+timedelta(seconds=cfg.bar_seconds)).isoformat()
        # Validate targets too, rather than only feature candles used by core.
        validate_at=max(utc(p['available_utc']),utc(p['timestamp_utc'])+timedelta(seconds=cfg.bar_seconds))
        prepare_bars([p],p['symbol'],validate_at.isoformat(),cfg)
        key=(p['symbol'],utc(p['timestamp_utc']))
        if key in grouped and canonical(grouped[key])!=canonical(p):
            raise ValueError('Conflicting candle versions')
        grouped[key]=p
    predictions=[]; skipped={}; seen=set()
    for symbol in sorted({k[0] for k in grouped}):
        series=sorted((p for (s,t),p in grouped.items() if s==symbol),key=lambda p:utc(p['timestamp_utc']))
        for p in series:
            close=utc(p['timestamp_utc'])+timedelta(seconds=cfg.bar_seconds)
            decision=max(close,utc(p['available_utc']))
            result=generate_signal(series,symbol=symbol,decision_utc=decision.isoformat(),config=cfg)
            if utc(result['data_cutoff_utc'])!=close:
                skipped['batch_already_contains_later_bars']=skipped.get('batch_already_contains_later_bars',0)+1
                continue
            target=utc(result['target_utc'])
            target_open=target-timedelta(seconds=cfg.bar_seconds)
            observed=grouped.get((symbol,target_open))
            key=(symbol,close)
            if key in seen:continue
            seen.add(key)
            if result['history_bars']<cfg.min_bars or not observed or target<=decision:
                reason='warmup_or_missing_future_target'
                skipped[reason]=skipped.get(reason,0)+1;continue
            # No forward-fill or target crossing a gap. Core selected segment
            # ends at close; verify every subsequent target-interval candle.
            needed=[close+timedelta(seconds=k*cfg.bar_seconds) for k in range(cfg.horizon_bars)]
            if any((symbol,t) not in grouped for t in needed):
                skipped['target_crosses_gap']=skipped.get('target_crosses_gap',0)+1;continue
            actual=math.log(observed['close']/p['close'])
            components=[c for c in result['components'] if c['status']=='ready']
            for comp in components:
                predictions.append(dict(symbol=symbol,decision_utc=decision.isoformat(),origin_utc=close.isoformat(),target_utc=target.isoformat(),model=comp['model'],forecast_log_return_bps=10000*comp['mean_log_return'],actual_log_return_bps=10000*actual))
            if components:
                denom=sum(cfg.weights[c['model']] for c in components)
                mu=sum(cfg.weights[c['model']]*c['mean_log_return'] for c in components)/denom
                predictions.append(dict(symbol=symbol,decision_utc=decision.isoformat(),origin_utc=close.isoformat(),target_utc=target.isoformat(),model='ensemble',forecast_log_return_bps=mu*10000,actual_log_return_bps=actual*10000))
            predictions.append(dict(symbol=symbol,decision_utc=decision.isoformat(),origin_utc=close.isoformat(),target_utc=target.isoformat(),model='random_walk',forecast_log_return_bps=0.0,actual_log_return_bps=actual*10000))
    # Pair each model only with random-walk predictions for the SAME targets.
    rw={(p['symbol'],p['origin_utc']):p for p in predictions if p['model']=='random_walk'}
    scores={}
    for model in sorted({p['model'] for p in predictions}):
        values=[p for p in predictions if p['model']==model]
        errors=[p['actual_log_return_bps']-p['forecast_log_return_bps'] for p in values]
        baseline=[rw[p['symbol'],p['origin_utc']]['actual_log_return_bps'] for p in values]
        scores[model]=dict(observations=len(values),rmse_bps=math.sqrt(sum(e*e for e in errors)/len(errors)),
            mae_bps=sum(abs(e) for e in errors)/len(errors),
            paired_random_walk_rmse_bps=math.sqrt(sum(e*e for e in baseline)/len(baseline)))
    per_session={}
    for p in predictions:
        key=p['symbol']+'|'+p['origin_utc'][:10]+'|'+p['model']
        per_session.setdefault(key,[]).append(p['actual_log_return_bps']-p['forecast_log_return_bps'])
    sessions={k:dict(observations=len(v),rmse_bps=math.sqrt(sum(x*x for x in v)/len(v))) for k,v in per_session.items()}
    summary=dict(model_version=MODEL_VERSION,config=asdict(cfg),availability=availability,
        status='FORECAST_DIAGNOSTIC_ONLY' if predictions else 'INSUFFICIENT_QUALIFIED_HISTORY',
        scores=scores,per_symbol_session=sessions,skipped=skipped,
        source_hash=hashlib.sha256(canonical(bars).encode()).hexdigest(),
        caveat='Rolling refits use only available prior bars. No automatic tuning, random splits, fills or P&L. Correlated and overlapping targets are not independent. Reserve later sessions before selecting models.')
    return summary,predictions


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bars',required=True)
    p.add_argument('--config');p.add_argument('--out',required=True)
    p.add_argument('--availability',choices=['recorded','bar_close_assumption'],default='recorded')
    a=p.parse_args();cfg=ModelConfig(**json.loads(Path(a.config).read_text())) if a.config else ModelConfig()
    summary,records=evaluate(read_bars(a.bars),cfg,a.availability)
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (out/'forecasts.csv').open('w',newline='') as f:
        header=list(records[0]) if records else ['symbol','model','status']
        w=csv.DictWriter(f,fieldnames=header);w.writeheader();w.writerows(records)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
