# Research register
Updated: 12 October 2026. No empirical trading result exists.

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
