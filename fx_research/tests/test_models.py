"""Synthetic software checks only. No assertions about market profitability."""
import copy
from datetime import datetime,timedelta,timezone
import math
import random
import unittest
from unittest.mock import patch

from models import Forecast, ar_forecast, kalman_forecast, ou_forecast
from signals import ModelConfig,combine,generate_signal,telemetry_signal
from evaluate_models import evaluate


def fixture(n=100,kind='ou'):
    rng=random.Random(781);state=0.0;values=[]
    for i in range(n):
        state=.82*state+rng.gauss(0,.00012)
        level=state if kind=='ou' else i*.00015+state
        values.append(1.1*math.exp(level))
    return values


def candles(values):
    start=datetime(2026,1,5,tzinfo=timezone.utc);out=[]
    for i,p in enumerate(values):
        opened=start+timedelta(seconds=i*300)
        out.append(dict(symbol='EURUSD#',timestamp_utc=opened.isoformat(),
            available_utc=(opened+timedelta(seconds=300)).isoformat(),
            open=p,high=p,low=p,close=p,complete=True,price_basis='bid',tick_volume=1))
    return out


def decision(bars):
    return bars[-1]['available_utc']


def quote(bars,side=0):
    p=bars[-1]['close']
    return dict(symbol='EURUSD#',timestamp_utc=decision(bars),bid=p,ask=p+.00001)


COSTS=dict(exit_spread_bps=.1,round_trip_fees_bps=0.0,slippage_bps_per_side=0.0)


class ModelChecks(unittest.TestCase):
    def test_ou_stationary_and_forecast_sign(self):
        prices=fixture(200);prices[-1]=max(prices)+.001
        f=ou_forecast(prices,2)
        self.assertEqual(f.status,'ready');self.assertLess(f.mean_log_return,0)
        self.assertGreater(f.variance_log_return,0)

    def test_ou_rejects_explosive_level(self):
        prices=[math.exp(.001*1.05**i) for i in range(80)]
        self.assertEqual(ou_forecast(prices,1).status,'unavailable')

    def test_kalman_recovers_noisy_positive_slope(self):
        f=kalman_forecast(fixture(160,'trend'),2)
        self.assertEqual(f.status,'ready');self.assertGreater(f.mean_log_return,0)
        self.assertGreater(f.diagnostics['filtered_slope'],0)

    def test_ar_negative_dependence_and_cumulative_variance(self):
        rng=random.Random(12);r=.001;prices=[1.1]
        for _ in range(160):
            r=-.75*r+rng.gauss(0,.0001);prices.append(prices[-1]*math.exp(r))
        f=ar_forecast(prices,3)
        self.assertLess(f.diagnostics['beta'],0)
        beta=f.diagnostics['beta'];sigma=f.diagnostics['residual_variance']
        expected=sigma*(1+(1+beta)**2+(1+beta+beta**2)**2)
        self.assertAlmostEqual(f.variance_log_return,expected)

    def test_constant_series_does_not_invent_information(self):
        for f in (ou_forecast,kalman_forecast,ar_forecast):
            self.assertEqual(f([1.1]*80,1).status,'unavailable')

    def test_model_warmup(self):
        for f in (ou_forecast,kalman_forecast,ar_forecast):
            self.assertEqual(f(fixture(17),1).reason,'insufficient_history')

    def test_lognormal_moments(self):
        f=Forecast('x','ready',.001,.0001).to_dict()
        self.assertAlmostEqual(f['expected_return'],math.exp(.001+.00005)-1)

    def test_disagreement_increases_mixture_uncertainty(self):
        cfg=ModelConfig();a=Forecast('ou','ready',.002,1e-6).to_dict()
        b=Forecast('kalman','ready',-.002,1e-6).to_dict()
        c=combine([a,b],cfg)
        self.assertGreater(c['forecast_sd_return'],.002)


class SignalChecks(unittest.TestCase):
    def setUp(self):self.bars=candles(fixture(100))
    def run_signal(self,bars=None,**kwargs):
        b=self.bars if bars is None else bars
        args=dict(symbol='EURUSD#',decision_utc=decision(b),quote=quote(b),costs=COSTS)
        args.update(kwargs);return generate_signal(b,**args)

    def test_future_bars_do_not_change_past_signal(self):
        extra=candles(fixture(120))
        a=self.run_signal();b=self.run_signal(extra,decision_utc=decision(self.bars),quote=quote(self.bars))
        self.assertEqual(a,b)

    def test_unavailable_historical_bar_is_excluded(self):
        b=copy.deepcopy(self.bars);b[-1]['available_utc']='2027-01-01T00:00:00+00:00'
        r=self.run_signal(b,decision_utc=decision(self.bars),quote=quote(self.bars))
        self.assertEqual(r['history_bars'],99)

    def test_gap_restarts_training_segment(self):
        b=self.bars[:20]+self.bars[40:]
        r=self.run_signal(b)
        self.assertEqual(r['history_bars'],60);self.assertEqual(r['reason'],'insufficient_history')

    def test_duplicate_conflict_rejected(self):
        b=self.bars+[dict(self.bars[-1],tick_volume=4)]
        with self.assertRaises(ValueError):self.run_signal(b)

    def test_warmup_can_be_journalled_with_quote(self):
        r=self.run_signal(self.bars[:17]);self.assertEqual(r['direction'],'no_trade')
        self.assertEqual(telemetry_signal(r).reason,'insufficient_history')

    def test_missing_costs_never_trade(self):
        r=self.run_signal(costs=None)
        self.assertFalse(r['trade_eligible']);self.assertEqual(len(r['components']),3)

    def test_nan_costs_rejected(self):
        with self.assertRaises(ValueError):self.run_signal(costs=dict(COSTS,exit_spread_bps=float('nan')))

    def test_future_quote_rejected(self):
        q=quote(self.bars);q['timestamp_utc']='2027-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):self.run_signal(quote=q)

    def test_fresh_consensus_can_buy_and_sell_and_costs_block(self):
        for sign,expected in [(1,'buy'),(-1,'sell')]:
            fs=[Forecast(n,'ready',sign*.001,1e-8) for n in ('ou','kalman','return_ar')]
            with patch('signals.forecasts',return_value=fs):
                r=self.run_signal();self.assertEqual(r['direction'],expected)
                self.assertFalse(r['abstention_is_exit'])
                telemetry_signal(r)
                costly=self.run_signal(costs=dict(COSTS,round_trip_fees_bps=100))
                self.assertEqual(costly['reason'],'below_cost_or_uncertainty_hurdle')

    def test_stale_quote_blocks_otherwise_strong_signal(self):
        fs=[Forecast(n,'ready',.001,1e-8) for n in ('ou','kalman','return_ar')]
        q=quote(self.bars);q['timestamp_utc']=(datetime.fromisoformat(q['timestamp_utc'])-timedelta(seconds=20)).isoformat()
        with patch('signals.forecasts',return_value=fs):
            r=self.run_signal(quote=q);self.assertEqual(r['reason'],'stale_quote')

    def test_costs_follow_bid_ask_price_basis(self):
        for basis in ('bid','ask','mid'):
            bars=[dict(p,price_basis=basis) for p in self.bars]
            for sign in (1,-1):
                fs=[Forecast(n,'ready',sign*.001,1e-8) for n in ('ou','kalman','return_ar')]
                with patch('signals.forecasts',return_value=fs):
                    r=self.run_signal(bars,costs=dict(COSTS,exit_spread_bps=3))
                    entry=r['entry_spread_bps']
                    expected=(entry+3)/2 if basis=='mid' else entry if (basis=='bid' and sign>0) or (basis=='ask' and sign<0) else 3
                    self.assertAlmostEqual(r['spread_cost_bps'],expected)

    def test_warmup_floor_and_invalid_weights(self):
        with self.assertRaises(ValueError):ModelConfig(min_bars=17).validate()
        with self.assertRaises(ValueError):ModelConfig(weights={'ou':1}).validate()

    def test_target_elapsed_never_trade(self):
        now=(datetime.fromisoformat(decision(self.bars))+timedelta(seconds=600)).isoformat()
        q=dict(quote(self.bars),timestamp_utc=now)
        r=self.run_signal(decision_utc=now,quote=q)
        self.assertEqual(r['reason'],'forecast_target_elapsed');self.assertFalse(r['trade_eligible'])


class EvaluationChecks(unittest.TestCase):
    def test_small_sample_reports_no_scores(self):
        s,r=evaluate(candles(fixture(17)))
        self.assertEqual(s['status'],'INSUFFICIENT_QUALIFIED_HISTORY');self.assertEqual(r,[])

    def test_actual_walk_forward_and_matched_benchmark(self):
        bars=candles(fixture(100));s,r=evaluate(bars)
        self.assertIn('random_walk',s['scores']);self.assertIn('kalman',s['scores'])
        for p in r:self.assertLess(p['decision_utc'],p['target_utc'])
        key=(r[0]['symbol'],r[0]['origin_utc'],r[0]['model'])
        later=copy.deepcopy(bars);later[-1]['close']*=1.01
        later[-1].update(high=later[-1]['close'],low=min(later[-1]['open'],later[-1]['close']))
        _,r2=evaluate(later)
        p1=next(p for p in r if (p['symbol'],p['origin_utc'],p['model'])==key)
        p2=next(p for p in r2 if (p['symbol'],p['origin_utc'],p['model'])==key)
        self.assertEqual(p1,p2)

    def test_backfilled_history_is_not_live_history(self):
        bars=candles(fixture(100))
        for p in bars:p['available_utc']='2026-01-07T00:00:00+00:00'
        actual,_=evaluate(bars);assumed,_=evaluate(bars,availability='bar_close_assumption')
        self.assertEqual(actual['scores'],{})
        self.assertTrue(assumed['scores'])


if __name__=='__main__':unittest.main()
