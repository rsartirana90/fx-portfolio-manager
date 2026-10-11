# Research decisions and experiments

Date: 11 October 2026. Status: specified, no genuine market data acquired.

## Mandate

Seconds-to-minutes FX futures strategies; paper first; capital undecided. Options are a future smaller risk sleeve whose purpose remains open. Research cost allowance proposed at GBP 100 initially; recurring subscriptions deferred. No accounts, subscriptions or live processes have been created by this project.

## Fixed first sample

CME GLBX.MDP3, proposed explicit Euro FX December 2026 expiry 6EZ6, 15 weekday daytime windows between 21 September and 9 October 2026. Exchange symbology must resolve before acquisition; the expiry's liquidity is not assumed. MBP-1 includes quotes and trades. One day of instrument definitions is also requested. Use the free metadata estimate first.

The sample was selected by calendar, without observing returns. Its purpose is pipeline verification and preliminary model comparison. It is not a sealed final holdout. Do not label particular dates quiet, stressed or event-driven until evidence supports the label.

## Data review before results

Confirm expiry, quotation, tick, multiplier, lifecycle and source mapping from definitions; compare traded volume and quote activity if the selected expiry is not suitable. Preserve original capture, hashes and normalization reports. Review quote flags, missing books, sequence patterns, receive gaps, wide spreads and source availability. Timestamp order is receive time plus original row order; event time is kept separately. Tied timestamps must not be made unique by invented time offsets.

A schema-valid CSV is not automatically high-quality market data. Schema/clock checks are implemented; exchange status and flag policies require genuine-sample review.

## Futures hypotheses

A. OU benchmark: transient deviations revert at a pace sufficient to exceed costs. Already implemented as a simple calibration/replay, not a proven model.

B. State-space candidate: a latent local level and trend separate observation noise from a changing drift. Compare filtered conditional forecasts against random walk and OU at 5, 15, 30 and 60 seconds. Ensure all filtering uses only information received by the decision time.

C. Changing-volatility candidate: add time-of-day structure and conditional volatility; forecast distributions may improve even when conditional mean does not. Test whether calibration, position sizing and abstention improve net outcomes. Do not equate better volatility forecasts with profitable directional trades.

D. Order-flow candidate: test trade imbalance and BBO size imbalance as predictors, conditional on spread, volatility and session. Add depth or Hawkes models only when data and a specific hypothesis justify the extra expense.

For each model, define decisions, entry/exit rules, cost threshold, maximum holding time, position limits and risk halt before assessing held-out P&L. Initial defaults are engineering examples, not optimized or agreed financial settings.

## Evaluation to add after genuine acquisition

The current executable supports a within-session chronological split. Next implement rolling prior-session calibration and independent next-session evaluation, reserving later new data for a final test. Never retrain on future session observations. Record every candidate and parameter variant to make selection bias visible.

Evaluate forecast RMSE versus random walk, interval coverage, tail errors and performance by horizon/session. Evaluate trading P&L after all costs, liquidation-value drawdown, turnover, time in market, worst trade/session, fill delays and net exposure. Once capital is defined, add properly margined returns and risk-adjusted performance; do not divide P&L by arbitrarily chosen margin to inflate returns.

Cost stress should cover measured commission/exchange fees, observed spreads, adverse slippage and feed/routing latency. Current doubled-cost simulation is a plumbing check. Use temporal blocks or independent sessions for uncertainty estimates; overlapping forecasts and high trade counts do not create independent observations.

Reject an apparent edge if it disappears under plausible costs, depends on one session, fails after regime changes, or requires unrealistic fills. Exact acceptance thresholds will be set before final testing once sample size and broker economics are known. No model is currently selected for deployment.

## Options research comparison

Hedge experiment: simulate long puts against persistent long futures exposure and calls against persistent short exposure. Rebalance hedge budgets over a slower horizon than individual futures trades. Compare drawdown and tail-loss reduction net of premium/spread with reducing futures size and event abstention. A rapidly reversing futures book may have little persistent exposure to hedge.

Long-volatility experiment: compare forecast realized volatility over the actual holding/hedging horizon with executable implied volatility. Research long straddles or strangles with delta hedges. Decompose P&L into directional exposure, gamma, theta, vega, hedging and transaction costs. Holding horizon is initially an open research choice, likely longer than the futures signals.

Short-volatility experiment: consider defined-risk vertical/condor spreads, not premium received as a proxy for low risk. Evaluate losses under jumps, volatility repricing, skew changes and hedging failure. Compare risk-adjusted contribution and co-loss with the futures strategy.

Black-76 is the pricing/Greek benchmark for the relevant European options on futures; verify each contract's exercise/settlement style. Compare stochastic-volatility or smile models only on a question they can answer: distribution, relative value or hedge performance. Surface calibration quality by itself does not demonstrate an edge. SVI can describe a surface without being a stochastic process model.

Add an options sleeve only after its incremental net benefit is established. Allocate by stress loss, delta/gamma/vega and margin or premium-at-risk, not a simple percentage of futures notional. Options data requests are deliberately not included in the first futures download.

## Continuous operation later

An always-on collector, scheduled jobs, monitoring, persistence/backups and broker reconciliation must run outside this chat. Before unattended paper execution, implement feed freshness, restart/reconnect behavior, position reconciliation, risk halt and alert delivery. This repository currently supplies none of those as running services.
