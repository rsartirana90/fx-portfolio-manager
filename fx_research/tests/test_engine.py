import math, tempfile, unittest
from pathlib import Path
import engine

class Checks(unittest.TestCase):
    def test_tick_precision(self):
        c=engine.config()
        self.assertEqual(engine.ticks('1.10005',c),22001)
        for value in ['nan','-1','1.100001']:
            with self.assertRaises(ValueError): engine.ticks(value,c)

    def test_ingest_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); file=root/'q.csv'; db=root/'q.sqlite'
            file.write_text('ts_event_ns,bid,ask,bid_size,ask_size\n1,1.1,1.10005,1,1\n2,1.1001,1.1,1,1\n')
            with self.assertRaises(ValueError): engine.ingest(file,db,'EXPLICIT','test',engine.config())
            import sqlite3
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM quotes').fetchone()[0],0)

    def test_no_future_interpolation(self):
        c=engine.config(); c['stale_seconds']=10
        rows=[(0,10,12,1,1),(2*engine.NS,20,22,1,1)]
        self.assertEqual(engine.regular_samples(rows,c),[(0,11),(engine.NS,11),(2*engine.NS,21)])

    def test_latency_and_spread_accounting(self):
        c=engine.config(); c.update(fee_per_side_usd=0,slippage_ticks=0,extra_edge_ticks=0,forecast_seconds=1)
        model=dict(phi=.5,mean_ticks=200,innovation_variance=1,step_seconds=1)
        rows=[(0,100,102,1,1),(50_000_000,101,103,1,1),(100_000_000,102,104,1,1),
              (200_000_000,103,105,1,1)]
        result,trades,_,_=engine.replay(rows,model,c)
        self.assertEqual(trades[0]['entry_ns'],100_000_000)
        self.assertEqual(trades[0]['entry_ticks'],104)
        self.assertEqual(trades[0]['exit_ticks'],103)
        self.assertAlmostEqual(result['net_pnl_usd'],-engine.tick_value(c))

    def test_expired_entry_not_filled(self):
        c=engine.config(); c.update(max_fill_wait_ms=100)
        model=dict(phi=.5,mean_ticks=200,innovation_variance=1,step_seconds=1)
        rows=[(0,100,102,1,1),(2*engine.NS,100,102,1,1)]
        result,trades,_,_=engine.replay(rows,model,c)
        self.assertFalse(trades); self.assertEqual(result['expired_orders'],1)

    def test_fees_reconcile(self):
        c=engine.config()
        model=dict(phi=.5,mean_ticks=200,innovation_variance=1,step_seconds=1)
        rows=[(0,100,102,1,1),(100_000_000,100,102,1,1),(200_000_000,101,103,1,1)]
        result,trades,_,_=engine.replay(rows,model,c)
        self.assertAlmostEqual(result['net_pnl_usd'],sum(t['net_usd'] for t in trades))
        self.assertEqual(result['fees_usd'],2*c['fee_per_side_usd'])

    def test_zero_variation_abstention(self):
        with self.assertRaises(ValueError):
            engine.fit_ou([(i*engine.NS,10,12,1,1) for i in range(200)],engine.config())

    def test_loss_halt_closes_and_blocks_entries(self):
        c=engine.config(); c.update(session_loss_limit_usd=10,decision_seconds=.1)
        model=dict(phi=.5,mean_ticks=200,innovation_variance=1,step_seconds=1)
        rows=[(i*100_000_000,100,102,1,1) for i in range(10)]
        result,trades,_,_=engine.replay(rows,model,c)
        self.assertTrue(result['halted'])
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]['reason'],'loss_limit')

    def test_forecast_labels_do_not_use_future_quotes(self):
        c=engine.config(); c.update(forecast_seconds=1)
        rows=[(0,10,12,1,1),(500_000_000,12,14,1,1),(2*engine.NS,100,102,1,1)]
        scores=engine.forecast_scores(rows,[(0,11,13,1)],c)
        self.assertEqual(scores['ou_rmse_ticks'],0)

    def test_demo_fit_and_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); c=engine.config()
            engine.demo(root/'q.csv',c)
            engine.ingest(root/'q.csv',root/'q.sqlite','SYNTHETIC_6E','synthetic',c)
            rows,_=engine.load(root/'q.sqlite',c)
            boundary=int(len(rows)*c['train_fraction'])
            model=engine.fit_ou(rows[:boundary],c)
            self.assertTrue(0<model['phi']<1)
            result,trades,_,_=engine.replay(rows[boundary:],model,c)
            self.assertTrue(math.isfinite(result['net_pnl_usd']))
            self.assertTrue(all(t['entry_ns']>=rows[boundary][0] for t in trades))

if __name__=='__main__': unittest.main()
