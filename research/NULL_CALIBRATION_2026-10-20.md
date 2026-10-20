# Null-model calibration audit — 20 October 2026

Status: SYNTHETIC SOFTWARE / MODEL DIAGNOSTIC ONLY. No market backtest, fills or P&L.

## Frozen design

Code: fx-models-2.0.0 models.py and signals.combine, verified against GitHub on
20 October (models blob ab61bd16e20d62dbb7e56e2da4b2d05a771260dd;
signals blob 593c13880a1d2b2fd9b5584014df5703b17d4e87).
Defaults unchanged. Seed 20261020. 3,000 independent windows at each length,
64 then 256. Gaussian independent zero-mean log returns, SD 0.0001 (one bp);
initial price 1. One next-bar target is excluded from each fitting window.
No tuning, model selection, position sizing, cost assumptions or trading simulation.
The same RNG stream continues across lengths. Outputs use paired zero forecasts.

## Measured synthetic results

| Window | Candidate | Ready / 3,000 | RMSE / paired zero RMSE | Normal 95% interval coverage |
|---|---|---:|---:|---:|
| 64 | OU | 2,836 | 1.0208 | 93.62% |
| 64 | Kalman | 3,000 | 1.2099 | 85.43% |
| 64 | Return AR | 3,000 | 1.0002 | 94.37% |
| 64 | Ensemble | 3,000 | 1.0269 | 94.20% |
| 256 | OU | 2,603 | 1.0047 | 94.74% |
| 256 | Kalman | 3,000 | 1.2298 | 84.53% |
| 256 | Return AR | 3,000 | 1.0006 | 94.73% |
| 256 | Ensemble | 3,000 | 1.0342 | 94.53% |

Intervals here mean forecast mean +/- 1.959963984540054 forecast SD.
OU/Kalman/AR are evaluated in log returns. Ensemble uses its reported
simple-return mixture mean/SD and matching realised simple return. A mixture
need not be Gaussian: its normal-approximation interval is a diagnostic,
not an exact mixture quantile. Monte Carlo coverage standard errors are at
most about 0.7 percentage points for these counts. Other metrics have not
been given confidence intervals.

## Interpretation and candidate decisions

- Kalman is materially underdispersed for this no-drift null: its conditional
  variance assumptions do not deliver nominal coverage under this DGP.
  Keep it unvalidated; do not increase its weight or treat its z score as a
  calibrated probability. This is a misspecification stress test, not proof
  the Kalman covariance recursion is mathematically wrong under its own model.
- OU accepts 94.53% / 86.77% of these random-walk windows. The phi-range
  check is an admissibility heuristic, not a statistical stationarity test.
  Successful fitting cannot be reported as established mean reversion.
- Return AR stays close to the zero-forecast baseline. These differences do
  not establish an edge or justify ranking on genuine prices.
- Mixture dispersion is much closer to nominal on this null, but this says
  nothing about calibration conditional on its trade-selection gates.
- All 55 existing software checks pass. Passing unit tests does not resolve
  distributional calibration.
- No thresholds, weights or deployed signal code changed. Net P&L, drawdown
  and turnover for v2 remain not measured.

Next: test conditional coverage and false trade eligibility under the frozen
cost/agreement gates across no-drift, volatility-shock and known-drift synthetic
controls; distinguish diagnostics from market evidence. On sufficient genuine
sessions, score all components and abstentions against matched random-walk
targets, then evaluate execution separately. M5 broker-FX evidence does not
certify seconds-level CME futures performance.

## Reproduce from repository root

```python
import random, math, json
from fx_research.models import forecasts
from fx_research.signals import ModelConfig, combine
rng=random.Random(20261020)
N=3000
for window in (64,256):
 cfg=ModelConfig(min_bars=64,window_bars=window)
 sums={}
 for _ in range(N):
  returns=[rng.gauss(0,0.0001) for i in range(window)]
  prices=[1.0]
  for r in returns[:-1]:prices.append(prices[-1]*math.exp(r))
  actual=returns[-1]
  fs=[f.to_dict() for f in forecasts(prices,cfg) if f.status=='ready']
  for f in fs:
   s=sums.setdefault(f['model'],[0,0.,0.,0.,0.])
   error=actual-f['mean_log_return'];sd=math.sqrt(f['variance_log_return'])
   s[0]+=1;s[1]+=error*error;s[2]+=actual*actual
   s[3]+=abs(error)<=1.959963984540054*sd;s[4]+=sd
  c=combine(fs,cfg)
  if c['active_models']:
   a=math.expm1(actual);err=a-c['expected_return'];sd=c['forecast_sd_return']
   s=sums.setdefault('ensemble',[0,0.,0.,0.,0.])
   s[0]+=1;s[1]+=err*err;s[2]+=a*a
   s[3]+=abs(err)<=1.959963984540054*sd;s[4]+=sd
 print(json.dumps({'window':window,'replications':N,'seed':20261020,
  'synthetic_only':True,'results':{k:{
   'ready':v[0],'ready_pct':round(100*v[0]/N,2),
   'rmse_vs_paired_zero':round(math.sqrt(v[1]/v[2]),4),
   'normal_95_interval_coverage_pct':round(100*v[3]/v[0],2),
   'mean_sd_bps':round(10000*v[4]/v[0],4)}
   for k,v in sums.items()}},sort_keys=True))
```
