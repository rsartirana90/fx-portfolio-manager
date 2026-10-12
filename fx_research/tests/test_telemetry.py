import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from telemetry import Journal, Signal


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root / 'journal.sqlite3')
        self.run = dict(git_commit='a'*40, model_id='baseline', parameters={'window': 100},
                        account_currency='USD', instrument=dict(symbol='EURUSD', venue='broker_demo',
                        quantity_unit='lots', contract_size=100000, tick_size=0.00001, profit_currency='USD'))
        self.journal.start_run('r1', **self.run)
        self.signal = Signal('s1', 'baseline', 'EURUSD', '2026-10-12T12:05:01Z',
                             '2026-10-12T12:05:00Z', '2026-10-12T12:05:31Z',
                             'buy', 30, 0.0002, 0.0003, True, 'fixture', 1.1, 1.1001)

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_causal_and_abstention_contract(self):
        for bad in (replace(self.signal, data_cutoff_utc='2026-10-12T12:06:00Z'),
                    replace(self.signal, expires_utc=self.signal.timestamp_utc),
                    replace(self.signal, filter_passed=False),
                    replace(self.signal, forecast_sd_return=float('nan'))):
            with self.assertRaises(ValueError):
                bad.validate()
        replace(self.signal, direction='no_trade', filter_passed=False).validate()

    def test_restart_duplicate_protection(self):
        self.journal.signal('r1', self.signal)
        self.journal.close()
        self.journal = Journal(self.root / 'journal.sqlite3')
        self.journal.start_run('r1', **self.run)
        self.journal.signal('r1', self.signal)
        with self.assertRaises(ValueError):
            self.journal.signal('r1', replace(self.signal, expected_return=0.002))
        self.assertEqual(self.journal.db.execute('SELECT count(*) FROM records').fetchone()[0], 1)

    def test_config_and_symbol_protection(self):
        with self.assertRaises(ValueError):
            self.journal.start_run('r1', **dict(self.run, parameters={'window': 50}))
        with self.assertRaises(ValueError):
            self.journal.signal('r1', replace(self.signal, symbol='GBPUSD'))

    def test_closed_candles_only(self):
        candle = dict(symbol='EURUSD', timestamp_utc='2026-10-12T12:00:00Z',
                      available_utc='2026-10-12T12:05:00Z', open=1.1, high=1.2,
                      low=1.0, close=1.15, tick_volume=15, price_basis='bid', complete=True)
        for bad in (dict(candle, complete=False), dict(candle, available_utc='2026-10-12T12:04:59Z'),
                    dict(candle, low=1.16), dict(candle, timestamp_utc='2026-10-12T12:01:00Z')):
            with self.assertRaises(ValueError):
                self.journal.record('r1', 'candles', 'c1', bad)
        self.journal.record('r1', 'candles', 'c1', candle)

    def test_fills_require_signal_and_units(self):
        fill = dict(signal_id='s1', order_id='o1', status='partial_fill', symbol='EURUSD', side='buy',
                    quantity=0.01, quantity_unit='lots', timestamp_utc='2026-10-12T12:05:02Z',
                    fill_id='f1', fill_price=1.1002, commission=-0.1, swap=0, cost_currency='USD')
        with self.assertRaises(ValueError):
            self.journal.record('r1', 'executions', 'f1', fill)
        self.journal.signal('r1', self.signal)
        with self.assertRaises(ValueError):
            self.journal.record('r1', 'executions', 'f1', dict(fill, quantity_unit='contracts'))
        self.journal.record('r1', 'executions', 'f1', fill)
        self.journal.record('r1', 'executions', 'f2', dict(fill, fill_id='f2'))

    def test_export_hashes_links_and_no_overwrite(self):
        self.journal.signal('r1', self.signal)
        self.journal.record('r1', 'snapshots', 'a1', dict(timestamp_utc='2026-10-12T12:00:00Z',
                            account_currency='USD', balance=10000, equity=10000, margin=0, positions=[]))
        manifest = self.journal.export('r1', self.root / 'export')
        for name, info in manifest['files'].items():
            self.assertEqual(info['sha256'], hashlib.sha256((self.root / 'export' / name).read_bytes()).hexdigest())
        with (self.root / 'export' / 'signals.csv').open() as handle:
            self.assertEqual(list(csv.DictReader(handle))[0]['signal_id'], 's1')
        self.assertEqual(json.loads((self.root / 'export' / 'manifest.json').read_text())['git_commit'], 'a'*40)
        with self.assertRaises(FileExistsError):
            self.journal.export('r1', self.root / 'export')


if __name__ == '__main__':
    unittest.main()
