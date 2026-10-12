# FX Portfolio Manager

An ongoing FX futures research and paper-trading programme, supervised in the [ChatGPT project](https://chatgpt.com/g/g-p-6acc10bfbf3081919721b3cd85821cc2/project).

Typical futures holding time: seconds to a few minutes. Options are a potential slower risk sleeve; their purpose remains undecided.

## Current status — 12 October 2026

- Offline research code, estimate-first historical-data adapter and read-only MT5 raw-batch collector exist.
- 31 software checks pass, including six signal/journal/export checks. Provider tests use mocks; synthetic demonstrations establish software behavior only.
- The user reports the VM is running repository-based models with virtual money: Claude executes Python signals and a separate procedure handles orders. That VM procedure is not checked into this repository or independently inspected here. No genuine market batch has been shared for analysis.
- A standard signal contract, private demo journal and weekly export are available in [VM_INTEGRATION.md](fx_research/VM_INTEGRATION.md). They require wiring into the existing VM runner; adding files alone does not activate logging.
- Capital, financial risk limits and data spending authorization remain undecided.
- The existing weekday ChatGPT review around 08:00 Europe/London, with a broader Friday review, remains the supervision workflow. This repository does not create another schedule or run a trading service.

## Working process

Read [AGENTS.md](AGENTS.md) before changing code or running research. Maintain [the research register](research/REGISTER.md) and [project state](research/STATE.md) as verified work progresses.

Code and detailed usage: [fx_research/README.md](fx_research/README.md). From the repository root:

```bash
cd fx_research
python3 -m unittest discover -s tests -v
python3 acquire.py plan
```

The plan command is offline. Authenticated estimation is a separate step. Downloads require explicit spending authorization.

## Repository scope

Version research code, specifications and concise non-sensitive evidence here. Keep credentials, licensed raw feeds, local databases, personal account records and generated trading ledgers outside this public repository. Data provenance should identify source, schema, contract, time range, transformations and hashes without disclosing secrets.

GitHub preserves changes and supports code review. It does not automatically synchronize the ChatGPT conversation, collect ticks or execute trades.

## XM data collection on your Windows VM

Windows and MT5 are confirmed by the user; the precise collector deployment remains unverified here. Follow [MT5_SETUP.md](fx_research/MT5_SETUP.md) for exact-symbol discovery, a one-batch check and continuous capture using the terminal's existing login. No order calls or credential entry are involved. Keep raw captures private and outside this public repository. Raw overlapping batches need qualification/reconciliation before model replay. The user's current review plan is weekly batches with completed M5 candles and precise model/execution logs across all available sessions.
