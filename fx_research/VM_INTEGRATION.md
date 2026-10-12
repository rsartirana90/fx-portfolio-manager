# Python model and weekly evidence integration

Claude executes the Python model code on the Windows VM; an existing, separate
procedure handles demo orders. This module adds a contract and journal for that
runner. It does not replace the runner, generate a new profitable model, connect
MT5 or send orders. Wire it into the existing procedure before expecting logs.

## Integration steps for Claude on the VM

1. Inspect the actual VM entry point and existing model outputs locally. Preserve
   current strategy calculations and order handling. Do not infer a live trading
   runner from `engine.py`: that file is an offline futures replay benchmark.
2. Create a private journal outside the checkout, e.g.
   `C:\FXData\research_journal.sqlite3`. Register a run using `Journal.start_run`.
   Obtain the exact commit from `git rev-parse HEAD`; create a new run ID whenever
   code, parameters, fitted model state or instrument settings change. Save fitted
   coefficients, calibration window/cutoff and seed in parameters. A restart may
   reuse the same ID only when these settings remain identical.
3. Read actual XM symbol metadata locally. Supply symbol, venue, quantity unit,
   contract size, tick size and profit currency, plus account currency. Do not
   reuse the CME multiplier/fees in `config.json` for XM. Quantity is explicit:
   lots and futures contracts are different units.
4. After each model calculation, convert its result to `Signal`, validate it and
   call `journal.signal(run_id, signal)` before passing the existing result to the
   order procedure. Log rejected and no-trade decisions too. A journal error must
   be surfaced, not silently dropped; the runner must define its response.
5. Record completed M5 candles, orders/fills, snapshots and operational events
   through `journal.record(run_id, kind, event_id, payload)`. Event IDs must be
   stable across retries. Identical retries are idempotent; conflicting events
   are rejected. Use unique fill IDs for partial fills.
6. Validate one complete demo decision/order/fill cycle and a restart on Windows.
   This code has offline tests only; deployment is not verified here.

Signal fields are declared in `telemetry.Signal`. Expected return and forecast
SD use decimal simple-return units over `horizon_seconds`, not annualised units.
Do not label forecast uncertainty as a stochastic volatility estimate: add a
separate model-specific volatility diagnostic to operational records if needed.
Use actual UTC observation/availability times; data cutoff cannot exceed decision
time. Expiry is the signal's validity deadline, not a guaranteed holding period.
The runner checks expiry, quote freshness and demo execution eligibility itself.
This module does not enforce trading risk limits or calculate position sizes.

## Record fields

- `candles`: symbol, timestamp_utc (opening time), available_utc (when received),
  open/high/low/close, tick_volume, price_basis (`bid`/`ask`/`mid`), complete=true.
  Only closed five-minute candles are accepted. Add spread and its units if known;
  do not invent zero volume/spread when unavailable. Preserve source quotes/ticks
  privately where possible; candles alone cannot reconstruct fast fills.
- `executions`: signal_id, order_id, status (`submitted`, `filled`, `partial_fill`,
  `rejected`, `cancelled`), symbol, side, quantity, quantity_unit, timestamp_utc.
  Each fill additionally requires fill_id, fill_price, commission, swap and
  cost_currency. Commission/swap are signed cashflows: debit negative, credit
  positive. Submission and fill are separate events. Add bid/ask, stop/target,
  rejection reason, broker position ID and entry/exit designation where available.
  Exit intent needs its own recorded signal. Cost adjustments arriving later are
  separate operational records linked to fill_id, never overwrites or invented
  zero costs. The schema stores costs; it does not infer total P&L.
- `snapshots`: timestamp_utc, account_currency, balance, equity, margin, positions
  (list containing symbol, strategy attribution, quantity/unit, side and position
  ID). Capture at the start/end and preferably every five minutes. If the account
  also runs other strategies, flag account totals as mixed; only explicitly linked
  executions can be attributed to our model.
- `operational`: timestamp_utc, kind, message; add relevant signal/order IDs,
  disconnect, restart, data gap, calibration or prediction diagnostics.

Payloads support additional JSON fields. Do not include passwords, API keys,
account login numbers or personally identifying account details in any payload.
JSON rejects NaN/infinity. No-trade decisions need a reason. Store late fills in
the original run that emitted the linked signal, even after upgrading the model.

## Weekly sharing

From `fx_research` on Windows, for each run active in the review period:

```powershell
python telemetry.py --db C:\FXData\research_journal.sqlite3 --run-id YOUR_RUN_ID --out C:\FXData\exports\week_01_run_01
```

The destination must not already exist. Share the generated `signals.csv`,
`candles.csv`, `executions.csv`, `snapshots.csv`, `operational.csv` and
`manifest.json` privately. Raw market data and journals stay outside this public
GitHub repository. The manifest includes config and file hashes, but no automatic
credential redaction: review all metadata before sharing.

Exports are consistent full-run snapshots. A run can span weeks; later snapshots
intentionally overlap and stable IDs permit reconciliation. This preserves
signals preceding later fills and carry-in context. Do not reset a running model
just to create a weekly boundary. Files are ordered by event ID; analysis sorts
by UTC event timestamps rather than assuming CSV row order is chronological.

Freeze model versions during each evaluation period. Test proposed refinements
on later unseen periods. The first weekly sample diagnoses behaviour and data
quality; it does not demonstrate a durable edge. Demo fills are separate from
live execution evidence. Shadow models must not create additional orders unless
the user explicitly changes the demo execution design.
