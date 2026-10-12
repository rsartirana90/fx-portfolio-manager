# XM / MetaTrader feed qualification
Date: 12 October 2026. Status: public-documentation research completed; no VM connection, market sample, backtest or collector deployment.

## Decision
Treat XM as a conditional broker-FX research route alongside the unresolved CME futures route. Prefer MT5 tick-history retrieval if the existing VM supports it. Do not assume the VM is Windows, continuously running, MT5, demo or live: these remain unknown. Neither data access nor storage rights have been verified for the user's account.

## Verified findings
1. MetaQuotes' Python copy_ticks_range retrieves terminal ticks over a date range, including bid/ask and flags. Its example includes time_msc. Use timezone-aware UTC requests; the API documents UTC tick timestamps. https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py
2. CopyTicks synchronizes local tick history with the trade server where history is available. Synchronization can be incomplete or delayed. Its documentation explicitly warns that OnTick notifications can represent several updates. A latest-quote poll or an OnTick callback alone does not establish complete capture. https://www.mql5.com/en/docs/series/copyticks
3. MQL4 also suppresses new tick events while a previous OnTick event is executing. An MT4 quote logger therefore needs an explicit observed-update limitation; it is not equivalent to a verified full tick archive. https://docs.mql4.com/runtime/event_fire
4. MqlTick includes bid, ask, last, volume, time_msc and change flags. Those field names do not establish that this account supplies genuine exchange trades or consolidated order flow. https://www.mql5.com/en/docs/constants/structures/mqltick
5. XM offers Forex and MT4/MT5 platforms, but platform availability does not verify this user's account, symbol definition or historical tick coverage. https://www.xm.com/

## Proposed acquisition contract (not deployed)
- Discover the actual EUR/USD symbol and preserve broker/server label, demo/live classification, terminal/package versions, price units, lot/contract and trading-session metadata. Never save credentials or private account identifiers in this public repository.
- Store immutable returned batches with query bounds, error/status, extraction UTC timestamp, batch sequence, row ordinal and file hash. Preserve all tick fields.
- Use explicit bounded requests and overlapping recovery windows. Persist a checkpoint only after durable storage. Requery a closed interval to check stability and incomplete synchronization.
- Preserve multiple records sharing a millisecond, including identical records within a response. Do not deduplicate by timestamp or by a global set of row values. Reconcile overlapping batches by ordered row multiplicities; flag inconsistent histories and ambiguous matches instead of silently deleting events.
- Label extraction time as first observed by the collector, not terminal arrival time. Historical/recovered ticks cannot reveal actual network latency or when an online strategy could have seen them. Maintain a separate availability ledger for prospective batches and outages.
- Keep raw prices outside this public repository unless rights to distribute are verified. Code and non-sensitive aggregate diagnostics can be versioned.

## First sample acceptance experiment
Request one completed London daytime EUR/USD session, then re-extract a closed interval and compare ordered records; follow with a prospective session to inspect availability. This is data qualification, not model selection.
Report returned rows and coverage by minute, bid/ask positivity and crossing, timestamp ordering, tied timestamps, flags, spread distribution, no-update intervals, query errors and overlap mismatches. Do not label every no-update interval a dropout: compare trading hours, terminal connectivity and retry results.
Quarantine crossed/zero quotes and unresolved ordering/overlap inconsistencies. No interpolation through outages and no inferred trades from tick-count volume. Acceptability depends on the observed gap distribution relative to the intended holding time; no arbitrary completeness percentage certifies the feed.

## Effect on model research
Prioritize random-walk, causal OU and local-level/trend comparisons at a provisional 60-second horizon using broker bid/ask. Time-varying volatility remains a calibration/risk hypothesis. Defer exchange order-flow and queue models for this feed unless the necessary semantics and depth/trade fields are verified.
A broker-quote replay is an indicative cost experiment, not an executed paper ledger. Model entry at the opposite quote after explicit availability plus latency, exit at the appropriate bid/ask; commissions, slippage and rejection remain unverified scenarios. A recovered historical tick timestamp alone cannot support a measured-latency claim.
CME profitability still requires contract-specific futures data and costs. No options allocation follows from this data work.

## Current measurements and next action
Net P&L, drawdown, turnover and uncertainty: not measured.
Next public-source action: lock a causal 60-second local-level/trend benchmark and execution specification, with rolling chronological calibration and cost break-even reporting. VM/account details and a genuine sample are the empirical gap; no repeated connection request is needed to continue research.
