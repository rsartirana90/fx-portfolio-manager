# Verified project state
Updated: 12 October 2026.

- Scope: seconds-to-minutes FX futures; research and paper trading first.
- Options role, capital and financial risk limits are undecided.
- ChatGPT project: https://chatgpt.com/g/g-p-6acc10bfbf3081919721b3cd85821cc2/project
- GitHub repository: https://github.com/rsartirana90/fx-portfolio-manager (public).
- Existing weekday supervision around 08:00 Europe/London, with broader Friday review; no schedule change in this repository setup.
- Offline OU benchmark, quote storage/replay and estimate-first adapter exist. 17 local checks passed on 11 October 2026. These include synthetic/model-mocked checks only.
- No broker API, paid feed, genuine market dataset, continuous engine or actual paper ledger is connected.
- Proposed sample: CME GLBX.MDP3, explicit Euro FX December 2026 6EZ6; 15 London daytime sessions, 21 September–9 October 2026; MBP-1 plus definitions. Symbol, liquidity and contract properties require verification.
- GBP 100 was a planning allowance, not an approved purchase or provider quote. Exact authenticated estimate and licensing are unresolved.
- Code risk settings are software placeholders, not agreed limits.
- GitHub setup versions code/instructions; it does not automatically synchronize chat content or run the scheduled ChatGPT workflow.

- Latest user proposal: an existing VM with XM installed may supply broker FX quotes. VM OS, MT4/MT5, account type, uptime, symbol metadata, storage permissions and tick availability remain unverified. No VM access exists here.
- 12 October: public-source feed qualification completed in research/XM_FEED_QUALIFICATION.md. MT5 stored-tick retrieval is preferred conditionally; OnTick logging alone does not certify complete capture. Recovered/extraction timestamps do not measure live latency.
- Broker FX research remains distinct from executable CME futures evidence.

Next: lock a causal 60-second local-level/trend benchmark and execution protocol using public research. When a genuine XM sample becomes available, qualify timestamps, bid/ask, overlap recovery and availability before empirical tests. CME symbol/definitions and authorized cost metadata remain unresolved.
