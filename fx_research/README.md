# FX portfolio manager — research starter v0.2

Prepared 11 October 2026.

## Agreed mandate

- FX focus; futures core, smaller options sleeve eventually.
- Typical trade: seconds to a few minutes.
- Research and paper trading first; trading capital and loss tolerance undecided.
- No existing broker API or paid data subscription.

This is an executable offline research foundation with a historical-data acquisition adapter. It does not collect live data, place orders, run in the background or claim a profitable strategy. No genuine market data has been purchased or downloaded. Provider calls have been tested with mock responses only. Options, live monitoring, broker integration, and portfolio construction are future phases.

## First experiment

Proposed instrument: an explicit CME Euro FX (6E) futures expiry. Start with one expiry and one trading session at a time; never treat a back-adjusted continuous futures price as an executable quote. Its indicative configuration is 125,000 EUR per contract, USD/EUR quotation, 0.00005 tick ($6.25). Verify the actual contract definition before a real-data import.

Collect event-level best bid/ask, their sizes, and trades. Prices alone or minute candles cannot substantiate a seconds-level execution backtest. Depth is the next addition if we investigate order flow or passive fills. Vendor adapters must preserve raw data, sequence numbers, exchange and receive timestamps, status messages, contract definitions and timezone conventions. The Databento CSV adapter now captures raw MBP-1 and definitions, retains receive/event timestamps and sequences, produces provenance hashes and normalizes BBO quotes. Provider flags, exchange status and contract definitions still need independent review before interpreting backtests.

## Running on a Mac

Python 3.10+ recommended; no third-party packages needed. Run these commands from the fx_research folder:

```bash
python3 -m unittest discover -s tests -v
python3 engine.py --config config.json demo --csv demo.csv
python3 engine.py --config config.json ingest --csv demo.csv --db demo.sqlite --contract SYNTHETIC_6E --source synthetic
python3 engine.py --config config.json research --db demo.sqlite --out demo_results
```

The demonstration is a seeded, artificial mean-reverting process. It tests plumbing, not profitability. Its timestamps and quote sizes are synthetic. Do not use its results to assess a trading edge.

For real quotes, after a vendor export has been normalized and independently checked:

```bash
python3 engine.py --config config.json ingest --csv quotes.csv --db session.sqlite --contract ACTUAL_EXPIRY_SYMBOL --source VENDOR_DATASET
python3 engine.py --config config.json research --db session.sqlite --out session_results
```

Replace placeholders with the actual expiry and provider dataset. Import requires a new database per dataset; it rejects crossed quotes, zero sizes, prices off the tick grid and unordered receive timestamps. Equal timestamps are preserved when explicit sequences are provided, including multiple updates with the same receive time and sequence. An ordinal row key preserves source-file order. Do not feed an unmodified vendor CSV into this schema. Version 0.1 databases must be re-imported into fresh version 2 databases.

CSV schema:

```text
ts_event_ns,bid,ask,bid_size,ask_size
```

Timestamps are integer Unix nanoseconds in UTC. The normalized vendor schema adds ts_recv_ns and sequence; replay runs on receive time and preserves exchange time separately. Bid/ask are decimal quoted prices, sizes are integer contracts. One file is one explicit contract. The adapter retains the original raw CSV and a capture manifest. Vendor capture-server receive time is not your eventual broker/client receive time; additional measured feed and routing latency will be needed.

## What is implemented

1. Quote validation and transactional SQLite storage; bad imports roll back.
2. Chronological training/test split by elapsed time (60%/40%).
3. A discrete OU/AR(1) mean-reversion benchmark calibrated solely on the training portion. Calibration uses one-second previous-tick samples and skips stale intervals. Nonstationary or degenerate fits abstain by raising an explicit error.
4. Conditional mean and uncertainty forecasts at a configurable horizon.
5. One-contract market-order replay: buy at ask, sell at bid, apply fees and adverse slippage, wait for modeled latency and expire orders whose first eligible quote arrives too late.
6. P&L, liquidation-value drawdown, trade ledger, forecast ledger and equity ledger.
7. Forecast RMSE against a random-walk forecast, descriptive Gaussian interval coverage, no-trade P&L benchmark and a separate higher-cost/higher-latency simulation.
8. An illustrative research-batch loss halt. USD P&L is reported; percentage returns are undefined while capital is undecided.

A signal requires forecast movement greater than an estimated round-trip spread, fees, slippage and an extra edge buffer. This is a deliberately simple benchmark, not an optimized strategy. Fitting mean reversion to price levels can be unstable in trending FX sessions; rejection alone is not a full stationarity diagnostic.

Configuration values for fees, latency, slippage and the USD 250 batch loss limit are software placeholders, not broker quotes or agreed financial risk limits. The loss halt can overshoot due to gaps/latency. It is not a daily reset rule or a guaranteed stop loss. End-of-data positions are marked as terminal liquidations at the final quote with costs, an accounting convention that bypasses modeled latency. Reports count those liquidations.

## Outputs and current limitations

`summary.json` records configuration, calibrated model, dataset provenance, exact train/test boundaries, gap counts, forecast evaluation and execution-cost stress. `trades.csv`, `equity.csv` and `forecasts.csv` support independent inspection.

Current replay assumes the displayed one-contract BBO is executable. It does not simulate hidden liquidity, queue position, market impact, partial fills, disconnect recovery, exchange halts, delivery, margin or multi-currency cash accounting. No passive limit-order profitability claims are supported. Forecast labels overlap and are statistically dependent; coverage and RMSE are descriptive. A single split is not a walk-forward robustness study.

## Model research sequence

These are testable hypotheses, not selected winners:

- Benchmark: random walk for forecasting; no trade for net P&L; simple OU mean reversion for the first executable comparison.
- Next: local-level/local-trend state-space model with time-varying observation noise and volatility, to separate noisy quotes from latent price/trend.
- Then: regime-dependent dynamics and order-flow-conditioned drift. Consider Hawkes arrival models only after reliable trade/depth data and a defined execution question are available.
- Options: stochastic-volatility surface calibration and realized-versus-implied volatility research, after the options sleeve's purpose and holding horizon are agreed. Pricing sophistication by itself is not a directional futures edge.

Each candidate must beat simpler forecasts AND improve net trading outcomes on unseen sessions. Select parameters on training/validation only, lock them before test runs, and log every candidate tried. Report failures and sensitivity, not only a best configuration.

## Data routes to investigate

Databento: CME futures and options coverage; historical usage-based access and quote/depth schemas. Obtain an estimate for one expiry, a small date range and a specific schema before increasing coverage. Determine applicable licensing through the provider; employment in banking does not let us infer eligibility from this chat.

CME DataMine: exchange historical data alternative; compare quote and depth coverage, format, cost and ease of normalization.

IBKR: later execution/paper-broker candidate. Its market-data/API restrictions mean execution brokerage and research-history sourcing should be evaluated separately.

Provider pages checked on 11 October 2026:
- https://databento.com/pricing
- https://databento.com/datasets
- https://www.cmegroup.com/markets/fx.html
- https://www.cmegroup.com/markets/fx/g10/euro-fx/specs
- https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-live/tick-by-tick-data/request-tick-by-tick-data

Do not assume old advertised monthly fees apply to this project. Exact provider cost and usage rights remain unresolved.

## Next milestones

A. Choose a data budget, confirm licensing and get a small genuine quote/trade sample. Build the source adapter and inspect gaps, spreads, sizes, timestamps and contract identifiers before any result is interpreted.

B. Collect multiple sessions across different volatility conditions. Add chronological rolling train/validation/test windows, session handling, forecast calibration diagnostics, order-flow features and fuller cost sensitivity. Preserve a final untouched test period. Cost thresholds and stress values must come from the chosen broker/feed and measured latency.

C. Connect a real-time feed to persistent raw and normalized storage. Paper execution and monitoring need an always-on process outside this chat. Alert on stale feeds, reconnects, rejected orders, position mismatch, abnormal spread, loss limits and deteriorating forecast/fill quality; verify recovery behavior.

D. Add options research and multi-currency risk aggregation. Define whether options hedge futures exposure, express volatility views, or both; define a risk budget rather than just a fraction of notional or premium.

E. Only after independent historical and forward paper evidence: determine deployable capital, margin reserve, position limits and execution permissions. The current artifact cannot be switched into live trading.

## Decisions still needed

- Initial historical-data budget and ongoing monthly data/hosting budget.
- London trading hours only, or broader coverage.
- Options intended primarily for hedging or volatility trading; desired holding period.

The ChatGPT weekday research schedule already exists. This code does not start background jobs, connect broker/data accounts or place trades.


## Start here: the genuine-data request

The checked-in plan selects 15 weekday sessions from 21 September to 9 October 2026, 06:00–16:00 UTC (07:00–17:00 London during this sample). Proposed expiry: 6EZ6 (December 2026). It is unverified until the free symbology lookup succeeds; liquidity and contract properties must then be confirmed from downloaded data/definitions. We request MBP-1 (quotes and trades together) plus one day of instrument definitions. No second trade feed is requested.

1. Create or use a Databento account at https://databento.com/ and complete its applicable historical-data entitlement requirements. Exact account eligibility and credits are not assumed.
2. Obtain your API key from the provider account. It remains on your machine: the command below prompts for it with hidden input, or reads DATABENTO_API_KEY if already configured. It never writes the key into a result file.
3. From the fx_research folder, run:

```bash
python3 acquire.py plan
python3 acquire.py estimate --out cost_estimate.json
```

`plan` is offline. `estimate` calls only symbology and cost metadata, not chargeable historical time-series downloads. Share cost_estimate.json for review; it contains no API key. We still have no actual quote in this artifact. Provider documentation states metadata/symbology access is free, while actual historical usage is billed by transmitted data.

The proposed GBP 100 allowance is not converted automatically into a spending authorization. After checking the quote, credits, taxes and conversion, a download is an explicit separate command with a USD estimate cap:

```bash
python3 acquire.py download --max-usd YOUR_CHOSEN_USD_CAP --out captures
```

Replace YOUR_CHOSEN_USD_CAP with a numeric amount chosen after quote review. The command re-estimates immediately before capture and requires the estimate plus 10% headroom to fit the cap. This is an estimate check, not a guaranteed billing ceiling; actual billed bytes govern charges and provider-side budget limits should be used where supported. Existing completed or partial captures prevent automatic re-downloads. Interrupted streaming can incur partial charges; investigate before retrying.

For one captured session:

```bash
python3 acquire.py normalize --csv captures/mbp-1_2026-09-21.csv --out quotes_2026-09-21.csv
python3 engine.py --config config.json ingest --csv quotes_2026-09-21.csv --db session_2026-09-21.sqlite --contract 6EZ6 --source Databento_GLBX.MDP3_mbp-1
python3 engine.py --config config.json research --db session_2026-09-21.sqlite --out results_2026-09-21
```

Normalization deliberately blocks output when quotes are missing, crossed or invalid, while leaving the raw capture and quality report available. It does not silently manufacture, forward-fill or discard a bad quote interval. This is strict and may need an explicit exchange-status-aware policy after examining genuine data.

Run the current engine on one session at a time. It does not implement a complete multi-session rolling calibration/validation framework; combining separated days into one replay would introduce overnight gaps and unsuitable risk accounting. Fifteen sessions are an initial feasibility sample, not sufficient evidence of a durable strategy. Future rolling evaluation must train on prior sessions and test each later session independently.

Validation: 17 unit/integration checks pass, covering accounting, loss halt, no future interpolation, receive-order preservation, source parsing, budget rejection and no repeated downloads. API tests use mock responses and do not establish actual account connectivity or entitlements.

API reference used for this version:
https://databento.com/docs/api-reference-historical?historical=http
Schema reference:
https://databento.com/docs/schemas-and-data-formats/whats-a-schema
