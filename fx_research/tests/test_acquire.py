import json, tempfile, unittest
from pathlib import Path
import acquire, engine

PLAN=json.loads((Path(__file__).resolve().parents[1]/'data_request.json').read_text())

class FakeAPI:
    def __init__(self,cost=1): self.cost=cost; self.calls=[]; self.captures=[]
    def json(self,method,params,post=False):
        self.calls.append((method,params,post))
        if method=='symbology.resolve': return dict(result={PLAN['symbol']:[dict(d0=PLAN['dates'][0],d1='2026-10-10',s='999')]},not_found=[],partial=[])
        return self.cost
    def capture(self,params,path):
        self.captures.append(params); path.write_text('FAKE_FIXTURE')
        return dict(path=str(path),sha256=acquire.file_hash(path),bytes=path.stat().st_size)

class Checks(unittest.TestCase):
    def test_request_scope(self):
        jobs=acquire.requests(PLAN)
        self.assertEqual(len(jobs),16)
        self.assertEqual(jobs[0]['schema'],'definition')
        self.assertEqual(jobs[1]['start'],'2026-09-21T06:00:00Z')
        self.assertTrue(all(j['symbols']=='6EZ6' for j in jobs))

    def test_estimate_does_not_download(self):
        api=FakeAPI(); result=acquire.estimate(api,PLAN)
        self.assertEqual(result['total_estimated_usd'],16)
        self.assertFalse(api.captures)

    def test_budget_blocks_all_downloads(self):
        api=FakeAPI()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): acquire.download(api,PLAN,Path(d),10)
        self.assertFalse(api.captures)

    def test_existing_files_not_rebilled(self):
        api=FakeAPI()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'mbp-1_2026-09-21.csv').write_text('fixture')
            with self.assertRaises(ValueError): acquire.download(api,PLAN,root,100)
        self.assertFalse(api.calls)

    def test_partial_symbol_blocks_estimate(self):
        class Bad(FakeAPI):
            def json(self,*args,**kwargs): return dict(result={},partial=['6EZ6'])
        with self.assertRaises(ValueError): acquire.estimate(Bad(),PLAN)

    def test_same_timestamp_updates_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); raw=root/'raw.csv'; normalized=root/'quotes.csv'
            raw.write_text('ts_event,ts_recv,sequence,symbol,action,bid_px_00,ask_px_00,bid_sz_00,ask_sz_00\n'
                '1,10,1,6EZ6,A,1.10000,1.10005,10,10\n'
                '1,10,1,6EZ6,T,1.10000,1.10005,11,10\n'
                '0,11,2,6EZ6,A,1.10005,1.10010,10,10\n')
            report=acquire.normalize(raw,normalized,'6EZ6')
            self.assertEqual(report['quotes'],3); self.assertEqual(report['trades'],1)
            engine.ingest(normalized,root/'data.sqlite','6EZ6','fixture',engine.config())
            rows,_=engine.load(root/'data.sqlite',engine.config())
            self.assertEqual([q[0] for q in rows],[10,10,11])

    def test_missing_quote_blocks_normalization(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); raw=root/'raw.csv'; out=root/'q.csv'
            raw.write_text('ts_event,ts_recv,sequence,symbol,bid_px_00,ask_px_00,bid_sz_00,ask_sz_00\n1,2,1,6EZ6,,1.1,0,1\n')
            with self.assertRaises(ValueError): acquire.normalize(raw,out,'6EZ6')
            self.assertFalse(out.exists()); self.assertTrue(out.with_suffix('.quality.json').exists())

if __name__=='__main__': unittest.main()
