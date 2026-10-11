# Research register
Updated: 11 October 2026. No empirical trading result exists.

| Candidate / hypothesis | Data readiness | Completed experiment / evidence | Risks | Next action |
|---|---|---|---|---|
| Data acquisition and provenance | Proposed GLBX.MDP3 MBP-1/definitions sample; no authenticated estimate | Adapter software checks pass with mocks | Unverified symbol/liquidity, licensing, estimate, flags and status handling | Verify source and cost metadata before authorized acquisition |
| OU mean reversion benchmark | No genuine quotes | Offline replay and accounting checks; no profitability evidence | Nonstationarity, spread/latency assumptions, one-session split | Inspect genuine sample, then establish baseline |
| Local-level/trend state-space | No genuine quotes | Hypothesis specified; not implemented/evaluated | Filter calibration, leakage, noise versus tradable drift | Specify causal forecasts and rolling protocol |
| Time-varying volatility / regimes | No genuine quotes | Research candidate only | Better forecast calibration may not improve trading P&L | Define falsifiable comparison against simpler models |
| Order-flow-conditioned dynamics | No genuine trades/books | Research candidate only | Top-of-book lacks queue/depth information | Assess schema and features before buying added depth |
| Options protection | No options data | Comparison framework specified | Fast direction changes and premium costs | Compare protection with futures size reduction/event abstention |
| Delta-hedged long volatility | No options data | Comparison framework specified | Theta, spreads, hedging costs and surface quality | Define holding horizon and executable implied-volatility inputs |
| Defined-risk short volatility | No options data | Comparison framework specified | Jumps, skew, liquidity and correlated losses | Define stress losses and incremental portfolio benefit |

## Experiment history
- 11 October 2026: 17 local software checks passed. Synthetic and mocked inputs only. No market performance statistics are recorded.
- 11 October 2026: repository initialized with standing instructions, current state, research specifications and existing offline code. No live services started.
