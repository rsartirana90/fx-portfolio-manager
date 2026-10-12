"""Model output contract and private, append-only demo-research journal.

No MT5 connection or order calls. The existing VM runner invokes this module.
"""
import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def positive(value, name, zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (value < 0 if zero else value <= 0):
        raise ValueError(f'Invalid {name}')


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError('Timestamp must explicitly use UTC')
    return parsed


@dataclass(frozen=True)
class Signal:
    signal_id: str
    model_id: str
    symbol: str
    timestamp_utc: str
    data_cutoff_utc: str
    expires_utc: str
    direction: str  # buy, sell, no_trade; a model intent, NOT an order
    horizon_seconds: float
    expected_return: float  # decimal simple return over horizon
    forecast_sd_return: float  # SD of decimal return over the SAME horizon
    filter_passed: bool
    reason: str
    bid: float
    ask: float

    def validate(self):
        for key in ('signal_id', 'model_id', 'symbol', 'reason'):
            if not isinstance(getattr(self, key), str) or not getattr(self, key):
                raise ValueError(f'Missing {key}')
        t, cutoff, expiry = map(utc, (self.timestamp_utc, self.data_cutoff_utc, self.expires_utc))
        if cutoff > t or expiry <= t:
            raise ValueError('Future input or already expired signal')
        if self.direction not in ('buy', 'sell', 'no_trade') or type(self.filter_passed) is not bool:
            raise ValueError('Invalid direction/filter')
        if not self.filter_passed and self.direction != 'no_trade':
            raise ValueError('Filtered signals must abstain')
        positive(self.horizon_seconds, 'horizon_seconds')
        positive(self.forecast_sd_return, 'forecast_sd_return', zero=True)
        positive(self.bid, 'bid'); positive(self.ask, 'ask')
        if self.ask < self.bid or not math.isfinite(self.expected_return):
            raise ValueError('Invalid quote/forecast')
        encoded(asdict(self))
        return self


REQUIRED = {
    'candles': {'symbol', 'timestamp_utc', 'available_utc', 'open', 'high', 'low', 'close', 'tick_volume', 'price_basis', 'complete'},
    'executions': {'signal_id', 'order_id', 'status', 'symbol', 'side', 'quantity', 'quantity_unit', 'timestamp_utc'},
    'snapshots': {'timestamp_utc', 'account_currency', 'balance', 'equity', 'margin', 'positions'},
    'operational': {'timestamp_utc', 'kind', 'message'},
}


class Journal:
    def __init__(self, db):
        Path(db).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records(run_id TEXT, kind TEXT, event_id TEXT,
                payload TEXT NOT NULL, PRIMARY KEY(run_id,kind,event_id));
        ''')

    def close(self):
        self.db.close()

    def start_run(self, run_id, *, git_commit, model_id, parameters, instrument, account_currency):
        """One run per code/config version. Never include credentials/account IDs."""
        if not run_id or not model_id or not account_currency:
            raise ValueError('Missing run identity')
        if len(git_commit) != 40 or any(c not in '0123456789abcdef' for c in git_commit):
            raise ValueError('Supply full Git commit SHA')
        fields = {'symbol', 'venue', 'quantity_unit', 'contract_size', 'tick_size', 'profit_currency'}
        if not fields <= instrument.keys():
            raise ValueError('Instrument metadata missing')
        positive(instrument['contract_size'], 'contract_size')
        positive(instrument['tick_size'], 'tick_size')
        payload = encoded(dict(schema_version=1, execution_mode='demo', git_commit=git_commit,
                               model_id=model_id, parameters=parameters, instrument=instrument,
                               account_currency=account_currency))
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO runs VALUES (?,?)', (run_id, payload))
            stored = self.db.execute('SELECT payload FROM runs WHERE run_id=?', (run_id,)).fetchone()[0]
            if stored != payload:
                raise ValueError('Run configuration changed; use a new run_id')

    def record(self, run_id, kind, event_id, payload):
        run = self.db.execute('SELECT payload FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not run or not event_id:
            raise ValueError('Unknown run or missing event_id')
        metadata = json.loads(run[0])
        if kind == 'signals':
            Signal(**payload).validate()
            if payload['signal_id'] != event_id or payload['model_id'] != metadata['model_id']:
                raise ValueError('Signal identity mismatch')
        elif kind in REQUIRED:
            if not REQUIRED[kind] <= payload.keys():
                raise ValueError(f'Missing {kind} fields: {REQUIRED[kind] - payload.keys()}')
            utc(payload['timestamp_utc'])
        else:
            raise ValueError('Unknown record kind')
        if 'symbol' in payload and payload['symbol'] != metadata['instrument']['symbol']:
            raise ValueError('Instrument mismatch')
        if kind == 'candles':
            opened, available = utc(payload['timestamp_utc']), utc(payload['available_utc'])
            if type(payload['complete']) is not bool or not payload['complete'] or (available-opened).total_seconds() < 300:
                raise ValueError('Only completed M5 candles with availability time')
            if opened.minute % 5 or opened.second or opened.microsecond or payload['price_basis'] not in ('bid', 'ask', 'mid'):
                raise ValueError('Invalid M5 convention')
            for field in ('open', 'high', 'low', 'close'):
                positive(payload[field], field)
            positive(payload['tick_volume'], 'tick_volume', zero=True)
            if not payload['low'] <= min(payload['open'], payload['close']) <= max(payload['open'], payload['close']) <= payload['high']:
                raise ValueError('Invalid OHLC')
        if kind == 'executions':
            if payload['status'] not in ('submitted', 'filled', 'partial_fill', 'rejected', 'cancelled') or payload['side'] not in ('buy', 'sell'):
                raise ValueError('Invalid execution status/side')
            positive(payload['quantity'], 'quantity')
            if payload['quantity_unit'] != metadata['instrument']['quantity_unit']:
                raise ValueError('Quantity unit mismatch')
            if not self.db.execute("SELECT 1 FROM records WHERE run_id=? AND kind='signals' AND event_id=?", (run_id, payload['signal_id'])).fetchone():
                raise ValueError('Execution requires a recorded signal')
            if payload['status'] in ('filled', 'partial_fill'):
                if not {'fill_id', 'fill_price', 'commission', 'swap', 'cost_currency'} <= payload.keys():
                    raise ValueError('Fill metadata missing; record each fill separately')
                positive(payload['fill_price'], 'fill_price')
        raw = encoded(payload)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO records VALUES (?,?,?,?)', (run_id, kind, event_id, raw))
            stored = self.db.execute('SELECT payload FROM records WHERE run_id=? AND kind=? AND event_id=?', (run_id, kind, event_id)).fetchone()[0]
            if stored != raw:
                raise ValueError('Conflicting duplicate event; existing record protected')

    def signal(self, run_id, signal):
        self.record(run_id, 'signals', signal.signal_id, asdict(signal))

    def export(self, run_id, out):
        """Consistent full-run snapshot: includes earlier signals linked to late fills.

        No P&L inference or slicing away carry-in positions. Export each relevant
        run weekly; overlapping snapshots retain stable IDs for reconciliation.
        """
        self.db.execute('BEGIN')
        try:
            run = self.db.execute('SELECT payload FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if not run:
                raise ValueError('Unknown run')
            rows = list(self.db.execute('SELECT kind,event_id,payload FROM records WHERE run_id=? ORDER BY kind,event_id', (run_id,)))
        finally:
            self.db.rollback()
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        files = {}
        for kind in ('signals', *REQUIRED):
            records = [dict(run_id=run_id, event_id=eid, **json.loads(raw)) for k,eid,raw in rows if k == kind]
            header = sorted(set().union(*(r.keys() for r in records))) if records else ['run_id', 'event_id']
            path = out / f'{kind}.csv'
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                for row in records:
                    writer.writerow({k: encoded(v) if isinstance(v, (dict,list)) else v for k,v in row.items()})
            files[path.name] = dict(rows=len(records), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        manifest = dict(run_id=run_id, **json.loads(run[0]), exported_utc=datetime.now(timezone.utc).isoformat(),
                        scope='full_run_snapshot', files=files,
                        evidence='market observations and demo executions supplied by VM; not live fill evidence')
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export a private demo journal. No orders.')
    parser.add_argument('--db', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    journal = Journal(args.db)
    try:
        journal.export(args.run_id, args.out)
    finally:
        journal.close()
