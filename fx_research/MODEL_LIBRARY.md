# Multi-model signal library v2

This repository is the authoritative model/signal library for the VM. The VM's
separate procedure supplies prices, records diagnostics and handles orders.
The entry point is **`signals.generate_signal`**, not the older `engine.py`.
There are no broker connections, account reads, sizing or order functions in
the new model modules. A GitHub update alone does not switch the VM runner.

## Implemented models

| Component | Implementation | Role |
|---|---|---|
| OU | OLS AR(1) on log price levels, with intercept; reject phi outside (0, 0.995) | Reversion to an estimated local equilibrium |
| Kalman | Filtered log level and damped slope, causal EWMA-scaled process/observation noise | Transient trend with changing uncertainty |
| Return AR(1) | No-intercept regression on log returns, ridge shrinkage, beta clipped to [-0.98, 0.98] | Short-lag persistence or reversal |
| Volatility diagnostic | Recent 16-return RMS / full-window return RMS | Common volatility-shock gate; not another directional model or HMM |

The AR model is deliberately a small complementary candidate, not proof of
independent alpha. All three use the same prices and can be strongly dependent.
No order-flow model or HMM probability is fabricated from candle data.

The new OU implementation works on completed-bar log prices. It is a separately
versioned bar model, not a claim that the old tick-replay model now supports M5
without changing its assumptions. The legacy engine remains available unchanged
apart from the database-lifecycle fix supplied in the VM archive.

The initial profile is M5, **one bar / five minutes ahead**, min 64 consecutive
completed bars and a rolling window of at most 256 bars. This is an auxiliary
research profile matching the currently supplied format, not a validated optimum
or the legacy daily five-trading-day model. With genuine M1 bars, explicitly set
bar_seconds=60, horizon_bars and freshness limits appropriately in a new config.
Do not interpolate M5 candles to invent finer observations. The 64-bar warm-up
is an engineering minimum, not a statistical sufficiency guarantee or a lowered
threshold to make the 17-bar sample generate results.

## Exact model conventions

All models return conditional **log-return mean and variance** over the same h
future bars. Conversion to simple-return moments uses the lognormal formula:
E[R]=exp(mu+v/2)-1 and Var[R]=(exp(v)-1)exp(2mu+v). Gaussian conditional moments
and parameter point estimates are approximations; parameter uncertainty is not
included. Model diagnostics preserve fitted coefficients/filtered state.

OU: x[t+1]=a+phi*x[t]+epsilon. Mean is a/(1-phi), decay is phi^h, forecast variance
is residual variance times sum(phi^(2j), j=0..h-1). Invalid stationarity or zero
residual variance returns unavailable with a reason; it is not a zero forecast.

Kalman: level'=level+slope; slope'=damping*slope, with diagonal process covariance
(q_level*v, q_slope*v) and observation variance measurement_noise*v. Initial
return variance uses the first 16 returns of the available training window;
initial state covariance is diag(10v,v). Filter the complete training window,
update EWMA after each observation, then propagate h times using the final v.
No smoothed future states or full-sample parameter estimation is used. Noise
ratios/damping are fixed research defaults, not MLE fits or latent stochastic
volatility. Every forecast refits/re-filters only its available rolling history.

AR: r[t+1]=beta*r[t]+epsilon; beta=sum(x*y)/(sum(x^2)+ridge*n*sample_variance(r)).
The h-return mean is r[t]*sum(beta^k,k=1..h). The cumulative-return variance is
sigma^2 * sum((sum(beta^k,k=0..j))^2,j=0..h-1), accounting for dependent future
returns instead of multiplying a one-step variance blindly by h.

## How models produce a score

Initial weights are fixed and equal; none was selected from observed profits.
Unavailable models are excluded and remaining positive weights renormalised.
By default at least two models must be available. For log-return forecast mu_i
and variance v_i:

    score = sum(w_i * tanh(mu_i / sqrt(v_i)))

Score ranges from -1 to +1. It is **not a probability or a calibrated confidence**.
We also mix each model's simple-return moments, retaining between-model disagreement:

    mean = sum(w_i * mean_i)
    variance = sum(w_i * (variance_i + (mean_i - mean)^2))

This is a predictive mixture, not the variance of an independently diversified
average of models. It deliberately does not divide uncertainty by model count.
Before live-quote eligibility checks, each target distribution is rebased from
the last candle close to a fresh quote on the same bid/ask/mid price basis.

Buy/sell entry candidates require all of:

- Target remains in the future; current bars and quote satisfy freshness limits.
- At least two active models; at least two directional supporters with component
  |mu|/SD >= 0.25 and at least 2/3 of active weight supporting the mixed direction.
- |score| >= 0.20 and score sign consistent with mixed expected return.
- Recent/window volatility ratio <= 3.0.
- Net expected edge positive and at least 0.5 mixture standard deviations.

For midpoint forecasts, the bps cost hurdle is:

    (entry_spread_bps + estimated_exit_spread_bps)/2
      + round_trip_fees_bps + 2*slippage_bps_per_side + edge_buffer_bps

Spread is observed from the supplied fresh quote; other values must be supplied
explicitly. Buffer defaults to 0.5 bps. Missing costs/quote means forecast-only
abstention, never invented zero cost. These are initial research rules requiring
out-of-sample validation and cost sensitivity, not approved capital/risk limits.

For bid-to-bid forecasts, spread cost is the full entry spread for longs and the
estimated exit spread for shorts. For ask-to-ask forecasts, those roles reverse.
This avoids charging half-spreads incorrectly for bid candles. Supply bps costs
relative to the current reference price on the specified price basis.

No-trade/abstain **does not mean close an existing position**. Signals carry
`intent=entry_candidate|abstain` and `abstention_is_exit=false`. Entry candidacy
does not certify order eligibility, account exposure or a fill. Exit policies,
position limits and reconciliation remain responsibilities of the separate runner.

## Call from the VM

From the repository root (core uses the standard library only):

```python
from fx_research.signals import ModelConfig, generate_signal, telemetry_signal

result = generate_signal(
    completed_bars,
    symbol="EURUSD#",                # exact broker identifier
    decision_utc=actual_decision_utc,
    quote=current_quote,             # symbol, timestamp_utc, bid, ask
    costs=verified_cost_estimates,    # exit_spread_bps, round_trip_fees_bps,
                                     # slippage_bps_per_side
    config=ModelConfig(),
)
# Preserve result in full, including all components and rejected decisions.
# result['direction'] is buy / sell / no_trade. No order is sent here.
journal.signal(run_id, telemetry_signal(result))
journal.record(run_id, 'operational', result['signal_id'] + '|diagnostics', {
    'timestamp_utc': result['timestamp_utc'],
    'kind': 'model_diagnostics', 'message': 'v2 forecast and decision',
    'signal_id': result['signal_id'], 'result': result,
})
```

The telemetry adapter needs a supplied quote and future signal expiry. If a
target has elapsed or no quote is available, preserve the full result as an
operational record rather than inventing a valid journal signal. Each signal
has a deterministic input/config hash; retain the actual Git commit separately
in the immutable journal run. Normal rolling state updates are documented per
signal, not hidden changes to static run configuration. Start a new run for a
code/config/instrument change; preserve rolling-state diagnostics for every call.
The versioned journal `model_id` must match `fx-models-2.0.0`.

Bars need symbol, UTC opening timestamp, UTC observed availability, complete=true,
price_basis=bid|ask|mid and OHLC. Only actually available, already closed bars are
used. Conflicting duplicates/mixed bases are rejected. A gap resets the usable
segment; no forward-fill or weekend transition is invented. Stale histories
can still produce diagnostics but cannot become entry candidates. Predictions
refer to the bar-aligned target time; horizon_seconds is the remaining wall-clock
time at decision, rather than incorrectly counting trading days as calendar days.

## Commands

```bash
# Synthetic API example, not a market backtest:
python -m fx_research.example_models

# JSON list of bars, or an XLSX with records/kind/payload as supplied:
python -m fx_research.signals --bars PRIVATE_BARS.xlsx --symbol EURUSD# \
  --decision-utc 2026-10-19T20:21:30+00:00 \
  --config fx_research/ensemble_config.json

# Pass --quote PRIVATE_QUOTE.json --costs PRIVATE_COSTS.json to test eligibility.
# XLSX support only: pip install -r fx_research/requirements-research.txt

# Rolling forecast comparison, no fills or trading P&L:
python -m fx_research.evaluate_models --bars PRIVATE_BARS.xlsx \
  --config fx_research/ensemble_config.json --out PRIVATE_RESULTS
```

`evaluate_models` compares each model and a weighted log-mean ensemble with the
zero-return/random-walk baseline on matching targets. It reports MAE/RMSE and
per-symbol UTC-date diagnostics. Recorded availability is the default. Explicit
`--availability bar_close_assumption` is a retrospective assumption and does not
measure the real VM's historical latency. Targets crossing missing bars are
excluded. All defaults are fixed; there is no automatic parameter search or
selection of the best model. Do not use aggregate model scores over different
availability masks without checking the paired random-walk score. Reserve later
sessions as validation/test before selecting any model or ensemble weights.

The existing 17–18-bar current sample remains insufficient. The evaluator reports
`INSUFFICIENT_QUALIFIED_HISTORY`; it does not output fictional profits. Forecast
improvement alone will not establish an executable edge. The existing tick replay
engine is separate and retains futures assumptions, not XM defaults.

## Migration for the VM's existing procedure

1. Pull the new repository commit and preserve the old model/run identity.
2. Read the exact XM instrument metadata and feed completed bars into this API.
   Keep raw inputs and journals private. Do not carry over CME multipliers/fees.
3. Supply fresh quotes and explicit cost estimates. Start in diagnostic/shadow
   mode and log every component, reason, input hash and code version.
4. Verify a complete decision/journal/restart cycle. If the existing procedure
   is later switched to consuming these entry candidates, make that switch
   explicit; this repository update alone does not perform it.

## Primary references and implementation choices

- Local linear trend state-space structure: [Statsmodels local linear trend
  example](https://www.statsmodels.org/stable/examples/notebooks/generated/statespace_local_linear_trend.html).
- Autoregression: [Statsmodels AutoReg documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.ar_model.AutoReg.html).

Our damping, EWMA adaptation, ridge rule, mixture score, costs and thresholds are
explicit research design choices, not claims established by those references.
All synthetic tests verify software only. No market profitability, VM deployment
or real execution validation is claimed for this release.
