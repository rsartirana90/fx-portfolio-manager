# Verified project state
Updated: 19 October 2026.

## Current model-library release — 19 October 2026

- User clarified that GitHub is the authoritative signal/model library. VM data
  collection and order handling are separate. Do not expand this repo into an
  execution service or assume a GitHub change activates the VM.
- Compared the user-supplied VM repository archive with the inspected GitHub
  head. It contained the offline OU engine plus collector/journal, with local
  database-lifecycle fixes; those fixes are included in this release.
- Added new, explicitly versioned `fx-models-2.0.0`: completed-bar OU, adaptive
  damped Kalman trend and regularised return AR(1), combined by a signed score,
  predictive mixture uncertainty, agreement, freshness and cost hurdles.
- Main API: fx_research.signals.generate_signal. Initial M5 / one-bar forecast
  profile; 64 consecutive completed bars minimum and 256-bar rolling window.
  Finer genuine bars are configurable. Parameters/weights are fixed research
  choices, not optimised or proven profitable. The new bar models are not a
  reconstruction of an external legacy daily implementation.
- Added exact-symbol/UTC/availability validation, XLSX candle reader, synthetic
  API demonstration, telemetry adapter and rolling forecast evaluator with
  matched random-walk targets. No orders, position sizes or synthetic fills.
- 55 local software checks pass. The supplied short workbook is accepted by
  the reader but yields INSUFFICIENT_QUALIFIED_HISTORY, not performance metrics.
- Reviewed privately supplied activity/data formats; keep raw records, account
  details and numerical private ledger results out of this public repository.
  No genuine-data profitability evidence exists for v2. Windows/runner migration
  and prospective validation remain pending.
- Next: pull the release on the VM, wire the documented API in diagnostic mode,
  collect full sessions and all component outputs, then evaluate fixed models
  on chronological validation and untouched later sessions. Keep the existing
  ChatGPT schedule; no change was made to it.

## Earlier state and decisions (historical)

- Scope: seconds-to-minutes FX futures; research and paper trading first.
- Options role, capital and financial risk limits are undecided.
- ChatGPT project: https://chatgpt.com/g/g-p-6acc10bfbf3081919721b3cd85821cc2/project
- GitHub repository: https://github.com/rsartirana90/fx-portfolio-manager (public).
- Existing weekday supervision around 08:00 Europe/London, with broader Friday review; no schedule change in this repository setup.
- Offline OU benchmark, quote storage/replay and estimate-first adapter exist. 17 local checks passed on 11 October 2026. These include synthetic/model-mocked checks only.
- Earlier repository-only status: no broker/data connection was verified here. Updated user-reported VM deployment is recorded below; no genuine market batch has been received for analysis.
- Proposed sample: CME GLBX.MDP3, explicit Euro FX December 2026 6EZ6; 15 London daytime sessions, 21 September–9 October 2026; MBP-1 plus definitions. Symbol, liquidity and contract properties require verification.
- GBP 100 was a planning allowance, not an approved purchase or provider quote. Exact authenticated estimate and licensing are unresolved.
- Code risk settings are software placeholders, not agreed limits.
- GitHub setup versions code/instructions; it does not automatically synchronize chat content or run the scheduled ChatGPT workflow.

- Latest user proposal: an existing VM with XM installed may supply broker FX quotes. User confirmed Windows and MetaTrader 5 on 12 October. Account type, uptime, symbol metadata, storage permissions and tick availability remain unverified. No VM access exists here.
- 12 October: public-source feed qualification completed in research/XM_FEED_QUALIFICATION.md. MT5 stored-tick retrieval is preferred conditionally; OnTick logging alone does not certify complete capture. Recovered/extraction timestamps do not measure live latency.
- Broker FX research remains distinct from executable CME futures evidence.

Next: lock a causal 60-second local-level/trend benchmark and execution protocol using public research. When a genuine XM sample becomes available, qualify timestamps, bid/ask, overlap recovery and availability before empirical tests. CME symbol/definitions and authorized cost metadata remain unresolved.

- 12 October: read-only MT5 batch collector and Windows setup guide added to fx_research. 25 local software checks pass (17 existing + 8 archive mocks). No Windows integration test, deployment or real sample yet. The collector preserves overlapping raw batches; reconciliation/qualification is required before replay. Next operational action: user runs exact-symbol discovery and one-batch check on the VM; no remote credentials are needed.

## Latest session decisions and implementation — 12 October evening

- User reports virtual-money strategies already run on the always-on Windows VM. Claude executes repository Python models; a separate existing procedure handles orders. That procedure is not available in this checkout. Do not ask for the repository location again.
- Scope is an independent FX Python model library; the other technical-analysis strategies are inaccessible and are not dependencies. Stochastic volatility is intended primarily for new signals, secondarily filtering. Options remain a later research sleeve. No profitability evidence has been shared.
- User selects all available trading sessions and weekly collection/sharing of M5 candles plus activity logs. Precise signal/fill times and optional bid/ask ticks remain necessary to examine fast execution; M5 candles do not recover intrabar paths.
- Added telemetry.py: explicit signal contract, immutable run config, private SQLite journal and consistent full-run CSV/manifest export. VM_INTEGRATION.md describes how Claude wires the existing runner; the change does not activate logging or alter signals/orders on the VM.
- 31 local software checks pass. No Windows runner integration, genuine weekly batch or empirical strategy evaluation has been performed here. The offline engine/config retains CME assumptions; do not substitute those for XM metadata.
- Next: integrate journal on the VM, verify a demo cycle/restart and deliver the first weekly batch. Preserve model/code/config versions; evaluate refinements on later unseen batches.
