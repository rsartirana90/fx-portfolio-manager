"""Software-only archive checks; no genuine XM data is used."""
from datetime import timezone
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zlib

from collect_mt5 import Archive, collect_once, parse_start


def tick(ms=1100, bid=1.1):
    return dict(time=ms // 1000, bid=bid, ask=bid + .0001, last=0.,
                volume=0, time_msc=ms, flags=6, volume_real=0.)


class FakeMT5:
    COPY_TICKS_ALL = 0
    def __init__(self, rows, connected=True):
        self.rows, self.connected, self.requests = rows, connected, []
    def terminal_info(self):
        return SimpleNamespace(connected=self.connected)
    def copy_ticks_range(self, symbol, start, end, flags):
        self.requests.append((symbol, start, end, flags))
        return self.rows
    def last_error(self):
        return (-1, 'must not be recorded')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ticks.sqlite3'
        self.archive = Archive(self.path, 'EURUSD', 1000, 'test-feed')
        self.archive.start_run({'test': 'synthetic'})
    def tearDown(self):
        self.archive.db.close()
        self.tmp.cleanup()
    def test_preserves_same_millisecond_and_identical_rows(self):
        rows = [tick(), tick(), tick(bid=1.2)]
        collect_once(FakeMT5(rows), self.archive, 'EURUSD', 2000)
        count, digest, payload = self.archive.db.execute(
            'SELECT row_count,sha256,payload_zlib FROM batches').fetchone()
        raw = zlib.decompress(payload)
        self.assertEqual(json.loads(raw), rows)
        self.assertEqual(count, 3)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
    def test_overlap_is_archived_without_silent_deduplication(self):
        fake = FakeMT5([tick()])
        collect_once(fake, self.archive, 'EURUSD', 2000)
        collect_once(fake, self.archive, 'EURUSD', 3000)
        self.assertEqual(self.archive.db.execute('SELECT sum(row_count) FROM batches').fetchone()[0], 2)
        self.assertEqual(fake.requests[1][1].timestamp(), 1.)
        self.assertEqual(fake.requests[0][1].tzinfo, timezone.utc)
    def test_query_error_does_not_advance_checkpoint(self):
        self.assertFalse(collect_once(FakeMT5(None), self.archive, 'EURUSD', 2000))
        self.assertEqual(self.archive.cursor_ms, 1000)
        self.assertEqual(self.archive.db.execute('SELECT kind FROM events').fetchone()[0], 'query_error_code_-1')
    def test_disconnection_and_clock_regression_do_not_query(self):
        fake = FakeMT5([], False)
        self.assertFalse(collect_once(fake, self.archive, 'EURUSD', 2000))
        fake.connected = True
        self.assertFalse(collect_once(fake, self.archive, 'EURUSD', 500))
        self.assertEqual(fake.requests, [])
    def test_resume_restores_committed_bounds(self):
        collect_once(FakeMT5([]), self.archive, 'EURUSD', 2000)
        resumed = Archive(self.path, 'EURUSD', None, 'test-feed')
        self.addCleanup(resumed.db.close)
        self.assertEqual(resumed.cursor_ms, 2000)
        self.assertEqual(resumed.origin_ms, 1000)
    def test_failure_during_storage_rolls_back_batch_and_cursor(self):
        self.archive.db.execute("CREATE TRIGGER fail_cursor BEFORE UPDATE ON config BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(Exception):
            collect_once(FakeMT5([tick()]), self.archive, 'EURUSD', 2000)
        self.assertEqual(self.archive.cursor_ms, 1000)
        self.assertEqual(self.archive.db.execute('SELECT count(*) FROM batches').fetchone()[0], 0)
    def test_recovery_query_is_bounded(self):
        fake = FakeMT5([])
        collect_once(fake, self.archive, 'EURUSD', 1_000_000)
        self.assertEqual(self.archive.cursor_ms, 61_000)
        self.assertEqual(fake.requests[0][2].timestamp(), 61.)
    def test_rejects_naive_start_and_changed_feed(self):
        with self.assertRaises(Exception):
            parse_start('2026-10-13T08:00:00')
        self.assertEqual(parse_start('2026-10-13T08:00:00+01:00'), parse_start('2026-10-13T07:00:00Z'))
        with self.assertRaises(ValueError):
            Archive(self.path, 'EURUSD', None, 'different-feed')


if __name__ == '__main__':
    unittest.main()
