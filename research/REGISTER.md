# Research register
Updated: 20 October 2026. No profitability evidence exists for the new v2 models.

## Calibration audit — 20 October 2026

Completed 6,000 independent synthetic no-drift windows using frozen v2 defaults.
Kalman nominal 95% normal intervals covered 85.43% (64 bars) and 84.53%
(256 bars). OU's admissibility heuristic accepted 94.53% and 86.77% of
random-walk windows; this does not establish stationarity. Ensemble coverage
was 94.20% / 94.53%, unconditioned on trading gates. All 55 software checks pass.
Keep all candidates unvalidated, parameters unchanged; no genuine v2 P&L,
drawdown or turnover measured. Reproduction and limitations:
[null calibration audit](NULL_CALIBRATION_2026-10-20.md).

Next research action: conditional coverage and false trade eligibility under
frozen gates/cost scenarios, then shock/drift controls. Genuine testing remains
limited by insufficient consecutive completed bars and executable quote/cost
metadata; M5 broker-FX results cannot establish seconds-level futures edge.


## V2 candidates and validation status

| Candidate | Implementation / evidence | Remaining risk | Next action |
|---|---|---|---|
| Completed-bar OU | Implemented OLS log-level AR(1), stationarity/variance rejection | Equilibrium instability and parameter uncertainty | Prospective rolling/session evaluation |
| Adaptive damped Kalman trend | Implemented filtered level/slope and causal EWMA-scaled noise | Fixed noise ratios, weak drift, correlated model errors | Compare with random walk, OU and fixed-noise settings on reserved periods |
| Regularised return AR(1) | Implemented positive/negative lag dynamics and cumulative-horizon variance | Signal decay, shrinkage choices, redundancy with other models | Incremental forecast comparison and ablation |
| Ensemble | Implemented fixed weights, mixture uncertainty, agreement and basis-aware cost gate | Uncalibrated score/thresholds; conditional uncertainty omits parameter risk | Freeze defaults, log every component, test on later unseen sessions |

Software validation: 55 passing local checks. Workbook reader accepts the supplied
format; present sample is too short and returns insufficient-history status.
No live service, trades, genuine fills, model P&L or VM migration is claimed.
The evaluation CLI is forecast-only; exchange quote replay remains separate.

## Earlier register (historical)

| Candidate / hypothesis | Data readiness | Completed experiment / evidence | Risks | Next action |
|---|---|---|---|---|
| Data acquisition and provenance | Proposed GLBX.MDP3 MBP-1/definitions sample; no authenticated estimate | Adapter software checks pass with mocks | Unverified symbol/liquidity, licensing, estimate, flags and status handling | Verify source and cost metadata before authorized acquisition |
| XM broker-FX data route | Windows/MT5 confirmed by user; account and actual ticks unverified | Qualification specification and read-only collector implemented; 8 archive mock checks pass | OnTick event loss, ambiguous overlap, recovered timestamps lack arrival latency; FX feed is not CME evidence | Run Windows one-batch check, then qualify prospective capture and repeated intervals |
| OU mean reversion benchmark | No genuine quotes | Offline replay and accounting checks; no profitability evidence | Nonstationarity, spread/latency assumptions, one-session split | Inspect genuine sample, then establish baseline |
| Local-level/trend state-space | No genuine quotes | Hypothesis specified; not implemented/evaluated | Filter calibration, leakage, noise versus tradable drift | Specify causal forecasts and rolling protocol |
| Time-varying volatility / regimes | No genuine quotes | Research candidate only | Better forecast calibration may not improve trading P&L | Define falsifiable comparison against simpler models |
| Order-flow-conditioned dynamics | No genuine exchange trades/books; XM field semantics unverified | XM tick documentation reviewed; quote updates do not establish consolidated order flow | Top-of-book lacks queue/depth information | Defer XM order-flow/queue claims; verify exchange schema before added depth |
| Options protection | No options data | Comparison framework specified | Fast direction changes and premium costs | Compare protection with futures size reduction/event abstention |
| Delta-hedged long volatility | No options data | Comparison framework specified | Theta, spreads, hedging costs and surface quality | Define holding horizon and executable implied-volatility inputs |
| Defined-risk short volatility | No options data | Comparison framework specified | Jumps, skew, liquidity and correlated losses | Define stress losses and incremental portfolio benefit |

## Experiment history
- 11 October 2026: 17 local software checks passed. Synthetic and mocked inputs only. No market performance statistics are recorded.
- 11 October 2026: repository initialized with standing instructions, current state, research specifications and existing offline code. No live services started.

- 12 October 2026: completed XM/MetaTrader feed qualification from primary documentation. Conditional preference for MT5 batch recovery; MT4 OnTick capture has an explicit completeness limitation. Defined raw schema, overlap/clock provenance and sample acceptance checks. No collector deployed, no market sample retrieved and no software code changed. Next research action: specify causal 60-second state-space comparison and execution rules.

- 12 October 2026 (implementation): user confirmed Windows and MT5. Added collect_mt5.py and MT5_SETUP.md, preserving raw overlapping batches, tied/identical rows, query availability, hashes and atomic checkpoints. 25 local checks pass; Linux mocks do not verify the Windows/MT5 integration. No collector deployed, data acquired or trades sent. Account class, storage rights, uptime and symbol remain pending.

- 12 October 2026 (evening): user reports repository models running with virtual money on an always-on Windows VM, Python executed by Claude with separate order handling. Agreed weekly real-price/demo-activity batches and M5 candles across all sessions. Added signal contract, immutable/versioned run journal, linked demo execution logs, closed-candle validation and full-run CSV/manifest export. 31 local software checks pass, including six new telemetry checks. Existing strategy and order logic unchanged; VM wiring is required and unverified. No real market batch analysed and no performance claim. Next: verify runner integration and review first weekly data, then test refinements forward.
