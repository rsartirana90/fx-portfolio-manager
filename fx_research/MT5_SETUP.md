# XM MT5 collector on the Windows VM

12 October 2026: user confirmed Windows and MT5. No VM connection or deployment has occurred. Account type, feed access, exact symbol, storage permissions and uptime remain unverified. This is a raw-data qualification collector, not a trading engine or qualified research dataset.

## Start locally on the VM

Use AnyDesk yourself. Leave the intended XM MT5 terminal open and logged in. No VM/broker password is supplied to Python. No orders are placed; the script only selects a Market Watch symbol and reads terminal data. Existing terminal trading settings need not be enabled for this script.

1. Obtain the latest repository on the VM at https://github.com/rsartirana90/fx-portfolio-manager (Git clone/pull, or GitHub Download ZIP and extract).
2. Install 64-bit Python on Windows if it is not installed. Open PowerShell in the repository's `fx_research` directory. Install the MetaQuotes package:

```powershell
py -3 -m pip install MetaTrader5
```

3. Find the exact XM `terminal64.exe` path using the terminal shortcut's Properties/Target. Substitute that path below; the sample is only a placeholder. Discover broker-specific EUR/USD names:

```powershell
py -3 collect_mt5.py --terminal "C:\PATH\TO\XM\terminal64.exe" --list-symbols
```

4. Use the exact symbol returned (which may have a suffix). First perform a one-batch connection check:

```powershell
py -3 collect_mt5.py --terminal "C:\PATH\TO\XM\terminal64.exe" --symbol EURUSD --once
```

5. Start continuous capture, using the same command without `--once`:

```powershell
py -3 collect_mt5.py --terminal "C:\PATH\TO\XM\terminal64.exe" --symbol EURUSD
```

The default archive is `%USERPROFILE%\FXData\xm_eurusd.sqlite3`, outside the repository. Keep the VM, terminal and collector running. Disconnecting AnyDesk is fine only if the Windows session and processes remain running; logging out or rebooting can stop them. Ctrl+C stops cleanly. Restarting the same command resumes from the stored request checkpoint, with bounded overlapping recovery queries. No Windows service, reboot startup task or remote data transfer is configured yet.

Start immediately to check the connection; leave it running into tomorrow, 13 October. The default origin is first startup time, not a historical-data request. Recovery may retrieve broker history after that origin. A changed broker server or demo/live class requires a separate database. Use `--db "C:\Users\YOUR_USER\FXData\other.sqlite3"` for another feed/symbol.

## What is stored

SQLite retains zlib-compressed raw JSON batches, SHA-256 hashes, query bounds, row counts, ordered tick fields, UTC request/return wall-clock times, monotonic query duration, run metadata and connection/error events. Duplicate rows and overlapping batches are preserved deliberately. The checkpoint commits atomically with the batch. `observed_ns` means available when the Python API returned the batch; it is not each tick's arrival at MT5. Package/Python/terminal versions and symbol metadata are stored; account login, personal details, balance and passwords are not.

Polling uses COPY_TICKS_ALL over at most a 60-second advance plus 10 seconds of trailing overlap. Empty responses are archived and are not proof of complete history or a disconnect. MT5 may later synchronize history outside that overlap; a closed-interval requery is still needed for qualification. The code preserves what is returned and cannot certify all broker updates. Wall-clock errors, terminal crashes and unavailable retained history can prevent complete recovery. No raw batches are automatically deduplicated, interpolated or fed to the existing engine.

## Bring results back for qualification

After a short capture, stop cleanly before copying the SQLite file. Do not copy only the main database during capture: SQLite may also have `-wal` and `-shm` files. Do not commit any of them to the public repository. Share only through an authorized private file path/upload, after confirming permitted use of XM data. We will inspect genuine row coverage, spreads, timestamp ordering, tied events and repeated-window stability before running models. Archive records contain broker-server metadata; they should stay private.

Next: verify an actual batch and account permissions, then configure reboot recovery and secure transfer if useful. We do not yet have an actual paper ledger or P&L.

## Primary references

- https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py — connection to the selected terminal and existing account.
- https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py — tick fields, bounded retrieval and UTC convention.
- https://www.mql5.com/en/docs/series/copyticks — history synchronization and tick/event limitations.
