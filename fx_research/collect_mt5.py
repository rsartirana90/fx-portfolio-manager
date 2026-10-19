"""Read-only MT5 batch archive. No orders or supplied credentials; no account IDs saved."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid
import zlib

FIELDS = ('time', 'bid', 'ask', 'last', 'volume', 'time_msc', 'flags', 'volume_real')


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc)


def serialize_ticks(ticks):
    # Preserve response order AND multiplicity. Overlap is intentional.
    rows = []
    for tick in ticks:
        row = {}
        for key in FIELDS:
            value = tick[key]
            row[key] = value.item() if hasattr(value, 'item') else value
        rows.append(row)
    return json.dumps(rows, separators=(',', ':'), allow_nan=True).encode('utf-8')


class Archive:
    def __init__(self, path, symbol, origin_ms, feed_identity):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        try:  # patch locale Bottana: chiude il database se l'apertura fallisce
            self._init(symbol, origin_ms, feed_identity)
        except BaseException:
            self.db.close()
            raise

    def _init(self, symbol, origin_ms, feed_identity):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_ns INTEGER, metadata TEXT);
            CREATE TABLE IF NOT EXISTS batches (
                id INTEGER PRIMARY KEY, run_id TEXT, start_ms INTEGER, end_ms INTEGER,
                requested_ns INTEGER, observed_ns INTEGER, elapsed_ns INTEGER,
                row_count INTEGER, sha256 TEXT, payload_zlib BLOB);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, run_id TEXT, observed_ns INTEGER, kind TEXT);
        ''')
        existing = dict(self.db.execute('SELECT key, value FROM config'))
        if existing:
            if existing['symbol'] != symbol or existing['feed_identity'] != feed_identity:
                raise ValueError('Archive belongs to a different symbol/feed; use a new database.')
            if origin_ms is not None and int(existing['origin_ms']) != origin_ms:
                raise ValueError('Start differs from archive origin; omit --start to resume.')
        else:
            if origin_ms is None:
                origin_ms = time.time_ns() // 1_000_000
            with self.db:
                self.db.executemany('INSERT INTO config VALUES (?, ?)', [
                    ('symbol', symbol), ('feed_identity', feed_identity),
                    ('origin_ms', str(origin_ms)), ('cursor_ms', str(origin_ms))])
        self.origin_ms = int(self.db.execute("SELECT value FROM config WHERE key='origin_ms'").fetchone()[0])
        self.run_id = uuid.uuid4().hex

    @property
    def cursor_ms(self):
        return int(self.db.execute("SELECT value FROM config WHERE key='cursor_ms'").fetchone()[0])

    def start_run(self, metadata):
        with self.db:
            self.db.execute('INSERT INTO runs VALUES (?, ?, ?)',
                            (self.run_id, time.time_ns(), json.dumps(metadata)))

    def event(self, kind):
        with self.db:
            self.db.execute('INSERT INTO events(run_id, observed_ns, kind) VALUES (?, ?, ?)',
                            (self.run_id, time.time_ns(), kind))

    def store(self, start_ms, end_ms, requested_ns, observed_ns, elapsed_ns, ticks):
        raw = serialize_ticks(ticks)
        with self.db:
            self.db.execute('''INSERT INTO batches(run_id,start_ms,end_ms,requested_ns,
                observed_ns,elapsed_ns,row_count,sha256,payload_zlib) VALUES (?,?,?,?,?,?,?,?,?)''',
                (self.run_id, start_ms, end_ms, requested_ns, observed_ns, elapsed_ns,
                 len(ticks), hashlib.sha256(raw).hexdigest(), zlib.compress(raw)))
            self.db.execute("UPDATE config SET value=? WHERE key='cursor_ms'",
                            (str(max(self.cursor_ms, end_ms)),))


def collect_once(mt5, archive, symbol, now_ms, overlap_ms=10_000, chunk_ms=60_000):
    terminal = mt5.terminal_info()
    if terminal is None or not terminal.connected:
        archive.event('terminal_disconnected')
        return False
    cursor = archive.cursor_ms
    if now_ms < cursor:
        archive.event('local_clock_before_checkpoint')
        return False
    start = max(archive.origin_ms, cursor - overlap_ms)
    end = min(now_ms, cursor + chunk_ms)
    requested = time.time_ns()
    timer = time.monotonic_ns()
    ticks = mt5.copy_ticks_range(symbol, utc(start), utc(end), mt5.COPY_TICKS_ALL)
    elapsed = time.monotonic_ns() - timer
    observed = time.time_ns()
    if ticks is None:
        # Error code only: avoid logging account-specific error text.
        error = mt5.last_error()
        archive.event('query_error_code_' + str(error[0] if error else 'unknown'))
        return False
    archive.store(start, end, requested, observed, elapsed, ticks)
    return True


def parse_start(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise argparse.ArgumentTypeError('Start must include timezone, e.g. 2026-10-13T07:00:00Z')
    return int(dt.timestamp() * 1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal', required=True, help='Exact path of running XM terminal64.exe')
    parser.add_argument('--list-symbols', action='store_true')
    parser.add_argument('--symbol', default='EURUSD', help='Exact broker symbol; inspect --list-symbols first')
    parser.add_argument('--db', default=str(Path.home() / 'FXData' / 'xm_eurusd.sqlite3'))
    parser.add_argument('--start', type=parse_start, help='Optional UTC origin; omit for prospective start/resume')
    parser.add_argument('--poll', type=float, default=1.0)
    parser.add_argument('--overlap-seconds', type=int, default=10)
    parser.add_argument('--once', action='store_true', help='Store one bounded batch and exit')
    args = parser.parse_args()
    if args.poll < 0.1 or args.overlap_seconds < 1:
        parser.error('poll must be >=0.1 seconds and overlap >=1 second')
    if sys.platform != 'win32':
        parser.error('MT5 integration must run on the Windows VM')
    import MetaTrader5 as mt5
    # No supplied credentials: uses terminal's existing session. May launch the
    # specified terminal if it is closed; user must choose the intended instance.
    if not mt5.initialize(args.terminal, timeout=10_000):
        raise SystemExit('Cannot connect to selected MT5 terminal. Open it and check login locally.')
    archive = None
    try:
        if args.list_symbols:
            symbols = mt5.symbols_get()
            if symbols is None:
                raise SystemExit('Symbol discovery failed.')
            for item in symbols:
                if 'EUR' in item.name.upper() and 'USD' in item.name.upper():
                    print(item.name)
            return
        if not mt5.symbol_select(args.symbol, True):
            raise SystemExit('Symbol not available; check its exact Market Watch name.')
        info = mt5.symbol_info(args.symbol)
        account = mt5.account_info()
        if info is None or account is None:
            raise SystemExit('Symbol/account metadata unavailable. Check terminal login locally.')
        # Persist server and account CLASS only, never login, balance or identity.
        identity = json.dumps([account.server, account.trade_mode, args.symbol])
        metadata = {
            'source': 'XM MT5 broker feed (user-reported; qualify before research)',
            'server': account.server, 'account_trade_mode': account.trade_mode,
            'terminal_version': mt5.version(), 'package_version': mt5.__version__,
            'symbol': args.symbol, 'tick_time_convention': 'MT5 documented UTC',
            'availability': 'batch return time; not individual terminal/network arrival',
            'overlap_seconds': args.overlap_seconds, 'poll_seconds': args.poll,
            'python_version': sys.version,
            'symbol_metadata': {k: getattr(info, k, None) for k in (
                'digits', 'point', 'trade_tick_size', 'trade_contract_size',
                'currency_base', 'currency_profit', 'currency_margin', 'trade_calc_mode')},
        }
        archive = Archive(args.db, args.symbol, args.start, identity)
        archive.start_run(metadata)
        print('Read-only capture active; local database:', args.db, flush=True)
        while True:
            current = mt5.account_info()
            if current is None:
                archive.event('account_metadata_unavailable')
                if args.once:
                    raise SystemExit('Account metadata unavailable; no batch captured.')
                time.sleep(max(args.poll, 5.0))
                continue
            if json.dumps([current.server, current.trade_mode, args.symbol]) != identity:
                archive.event('feed_identity_changed')
                raise SystemExit('Feed identity changed; stopped to avoid mixed-source data.')
            success = collect_once(mt5, archive, args.symbol, time.time_ns() // 1_000_000,
                                   args.overlap_seconds * 1000)
            if args.once:
                if not success:
                    raise SystemExit('No batch captured. Check terminal connectivity locally.')
                print('One raw batch stored; completeness remains unverified.', flush=True)
                break
            time.sleep(args.poll if success else max(args.poll, 5.0))
    except KeyboardInterrupt:
        if archive:
            archive.event('operator_stop')
        print('Capture stopped.')
    finally:
        if archive:
            archive.db.close()
        mt5.shutdown()


if __name__ == '__main__':
    main()
