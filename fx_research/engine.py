"""Offline FX futures research. Standard library only; no broker/order API."""
import argparse, csv, hashlib, json, math, random, sqlite3
from contextlib import closing  # patch locale Bottana
from decimal import Decimal
from pathlib import Path

NS = 1_000_000_000
DEFAULT = dict(tick_size='0.00005', multiplier=125000, fee_per_side_usd=2.5,
               slippage_ticks=1, latency_ms=100, max_fill_wait_ms=1000,
               decision_seconds=1, forecast_seconds=30, max_hold_seconds=120,
               extra_edge_ticks=1, max_spread_ticks=2, session_loss_limit_usd=250,
               train_fraction=0.6, stale_seconds=2)

def config(path=None):
    c = DEFAULT.copy()
    if path:
        c.update(json.loads(Path(path).read_text()))
    for key in ('tick_size', 'multiplier', 'decision_seconds', 'forecast_seconds',
                'max_hold_seconds', 'session_loss_limit_usd', 'stale_seconds', 'max_fill_wait_ms'):
        if float(c[key]) <= 0:
            raise ValueError(f'{key} must be positive')
    for key in ('fee_per_side_usd', 'slippage_ticks', 'latency_ms', 'extra_edge_ticks', 'max_spread_ticks'):
        if c[key] < 0:
            raise ValueError(f'{key} must be nonnegative')
    if not 0 < c['train_fraction'] < 1:
        raise ValueError('train_fraction must be between zero and one')
    return c

def tick_value(c):
    return float(c['tick_size']) * c['multiplier']

def ticks(price, c):
    v = Decimal(str(price)) / Decimal(c['tick_size'])
    if not v.is_finite() or v <= 0 or v != v.to_integral_value():
        raise ValueError('Prices must be positive finite tick multiples')
    return int(v)

def ingest(path, db, contract, source, c):
    """One CSV = one explicit contract, chronological quote stream, one source."""
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    conn = sqlite3.connect(db)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, t INTEGER, event_ns INTEGER, recv_ns INTEGER, sequence INTEGER, bid INTEGER, ask INTEGER, bs INTEGER, ass INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)')
        if conn.execute('SELECT count(*) FROM quotes').fetchone()[0]:
            raise ValueError('Use a new database per dataset; existing quotes are protected')
        previous = -1
        previous_sequence = None
        n = 0
        with conn, open(path, newline='') as f:
            for row in csv.DictReader(f):
                event = int(row['ts_event_ns'])
                receive = int(row.get('ts_recv_ns') or event)
                t = receive
                sequence = int(row.get('sequence') or n)
                bid, ask = ticks(row['bid'], c), ticks(row['ask'], c)
                bs, ass = int(row['bid_size']), int(row['ask_size'])
                if t < previous or (t == previous and not row.get('sequence')) or bid > ask or min(bs, ass) < 1:
                    raise ValueError('Unordered/duplicate timestamps, crossed quote, or missing size')
                conn.execute('INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?)', (n, t, event, receive, sequence, bid, ask, bs, ass))
                previous, n = t, n + 1
                previous_sequence = sequence
            if n < 2:
                raise ValueError('Need at least two quotes')
            metadata = dict(contract=contract, source=source, sha256=digest,
                            tick_size=c['tick_size'], multiplier=str(c['multiplier']),
                            replay_clock='ts_recv_ns (or ts_event_ns for legacy CSV)',schema_version='2')
            conn.executemany('INSERT INTO metadata VALUES (?,?)', metadata.items())
        return dict(rows=n, sha256=digest, contract=contract, source=source)
    finally:
        conn.close()

def load(db, c):
    with closing(sqlite3.connect(db)) as conn, conn:  # patch locale Bottana: chiude il database
        meta = dict(conn.execute('SELECT key,value FROM metadata'))
        if meta.get('schema_version') != '2':
            raise ValueError('Re-import the source CSV into a fresh database for schema version 2')
        rows = list(conn.execute('SELECT t,bid,ask,bs,ass FROM quotes ORDER BY t,id'))
    if meta['tick_size'] != c['tick_size'] or float(meta['multiplier']) != c['multiplier']:
        raise ValueError('Contract configuration differs from ingest configuration')
    return rows, meta

def regular_samples(rows, c):
    """Previous-tick interpolation; stale intervals break calibration pairs."""
    step = int(c['decision_seconds'] * NS)
    t, end, i = rows[0][0], rows[-1][0], 0
    result = []
    while t <= end:
        while i + 1 < len(rows) and rows[i + 1][0] <= t:
            i += 1
        q = rows[i]
        if t - q[0] <= c['stale_seconds'] * NS:
            result.append((t, (q[1] + q[2]) / 2))
        t += step
    return result

def fit_ou(rows, c):
    samples = regular_samples(rows, c)
    pairs = [(a[1], b[1]) for a, b in zip(samples, samples[1:])
             if b[0] - a[0] == int(c['decision_seconds'] * NS)]
    if len(pairs) < 100:
        raise ValueError('Need at least 100 non-stale adjacent training pairs')
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    denom = sum((x - mx)**2 for x, _ in pairs)
    if denom == 0:
        raise ValueError('No price variation in training window')
    phi = sum((x-mx)*(y-my) for x,y in pairs) / denom
    if not 0 < phi < 1:
        raise ValueError('Stationary mean reversion rejected; OU benchmark must abstain')
    intercept = my - phi * mx
    variance = sum((y-intercept-phi*x)**2 for x,y in pairs) / (len(pairs)-2)
    return dict(phi=phi, mean_ticks=intercept/(1-phi), innovation_variance=variance,
                pairs=len(pairs), step_seconds=c['decision_seconds'])

def forecast(model, mid, horizon):
    power = horizon / model['step_seconds']
    decay = model['phi']**power
    mean = model['mean_ticks'] + decay*(mid-model['mean_ticks'])
    variance = model['innovation_variance']*(1-decay**2)/(1-model['phi']**2)
    return mean, math.sqrt(max(0, variance))

def forecast_scores(rows, predictions, c):
    """Score against latest quote at/before horizon; skip stale or truncated labels."""
    from bisect import bisect_right
    times = [q[0] for q in rows]
    errors, naive, covered = [], [], []
    for t, mid, expected, sd in predictions:
        target = t + int(c['forecast_seconds']*NS)
        if target > times[-1]:
            continue
        index = bisect_right(times, target)-1
        q = rows[index]
        if target-q[0] > c['stale_seconds']*NS:
            continue
        actual = (q[1]+q[2])/2
        errors.append((actual-expected)**2)
        naive.append((actual-mid)**2)
        covered.append(abs(actual-expected) <= 1.96*sd)
    return dict(scored_forecasts=len(errors),
                ou_rmse_ticks=math.sqrt(sum(errors)/len(errors)) if errors else None,
                random_walk_rmse_ticks=math.sqrt(sum(naive)/len(naive)) if naive else None,
                gaussian_95pct_coverage=sum(covered)/len(covered) if covered else None,
                note='Overlapping forecast labels are dependent; these are descriptive metrics, not significance tests.')

def replay(rows, model, c):
    """One contract. Market orders cross BBO after latency; no passive-fill claims."""
    pos, entry, entered, pending = 0, 0., 0, None
    realized, peak, dd, fees = 0., 0., 0., 0.
    halted, next_decision, cancelled = False, rows[0][0], 0
    trades, marks, predictions = [], [], []
    tv = tick_value(c)
    def close(q, reason):
        nonlocal pos, realized, fees
        exit_price = q[1] - c['slippage_ticks'] if pos > 0 else q[2] + c['slippage_ticks']
        gross = pos*(exit_price-entry)*tv
        cost = 2*c['fee_per_side_usd']
        realized += gross-c['fee_per_side_usd']
        fees += c['fee_per_side_usd']
        trades.append(dict(entry_ns=entered, exit_ns=q[0], direction=pos,
                           entry_ticks=entry, exit_ticks=exit_price,
                           gross_usd=gross, fees_usd=cost, net_usd=gross-cost, reason=reason))
        pos = 0
    for q in rows:
        t,bid,ask,bs,ass = q
        mid = (bid+ask)/2
        if pending is not None:
            ready, deadline, target, reason = pending
            if t > deadline:
                cancelled += 1
                pending = None
            elif t >= ready:
                if target == 0 and pos:
                    close(q, reason)
                elif target and not pos and not halted and ask-bid <= c['max_spread_ticks']:
                    pos = target
                    entry = ask+c['slippage_ticks'] if pos > 0 else bid-c['slippage_ticks']
                    entered = t
                    realized -= c['fee_per_side_usd']
                    fees += c['fee_per_side_usd']
                pending = None
        liquidation = bid-c['slippage_ticks'] if pos > 0 else ask+c['slippage_ticks']
        equity = realized + (pos*(liquidation-entry)*tv-c['fee_per_side_usd'] if pos else 0)
        peak = max(peak, equity)
        dd = max(dd, peak-equity)
        if equity <= -c['session_loss_limit_usd']:
            halted = True
            if pending and pending[2] != 0:
                pending = None
        marks.append((t,equity))
        if t < next_decision:
            continue
        next_decision = t + int(c['decision_seconds']*NS)
        expected, uncertainty = forecast(model, mid, c['forecast_seconds'])
        edge = expected-mid
        predictions.append((t,mid,expected,uncertainty))
        if pending:
            continue
        target, reason = None, ''
        if pos and (halted or t-entered >= c['max_hold_seconds']*NS or pos*edge <= 0):
            target, reason = 0, 'loss_limit' if halted else 'time_or_signal'
        elif not pos and not halted and ask-bid <= c['max_spread_ticks']:
            threshold = ask-bid + 2*c['slippage_ticks'] + 2*c['fee_per_side_usd']/tv + c['extra_edge_ticks']
            if abs(edge) > threshold:
                target, reason = (1 if edge > 0 else -1), 'entry'
        if target is not None:
            ready = t + int(c['latency_ms']*1_000_000)
            pending = (ready, ready+int(c['max_fill_wait_ms']*1_000_000), target, reason)
    # Explicit accounting convention, not a latency-valid fill or a live risk guarantee.
    if pos:
        close(rows[-1], 'terminal_liquidation')
        peak = max(peak, realized)
        dd = max(dd, peak-realized)
        marks.append((rows[-1][0],realized))
    nets = [x['net_usd'] for x in trades]
    summary = dict(trades=len(trades), net_pnl_usd=realized, fees_usd=fees,
                   max_drawdown_usd=dd, win_rate=sum(v>0 for v in nets)/len(nets) if nets else None,
                   mean_trade_usd=sum(nets)/len(nets) if nets else None,
                   halted=halted, expired_orders=cancelled,
                   capital_return=None, terminal_liquidations=sum(x['reason']=='terminal_liquidation' for x in trades))
    return summary, trades, marks, predictions

def demo(path, c):
    rng, state = random.Random(41), 22000.
    start = 1_700_000_000*NS
    with open(path,'w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['ts_event_ns','bid','ask','bid_size','ask_size'])
        for i in range(24000):
            state += .01*(22000-state)+rng.gauss(0,.7)
            bid = round(state)-1
            tick = Decimal(c['tick_size'])
            writer.writerow([start+i*250_000_000,str(bid*tick),str((bid+2)*tick),10,10])

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config')
    sub = p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('demo'); d.add_argument('--csv',default='demo.csv')
    i=sub.add_parser('ingest'); i.add_argument('--csv',required=True); i.add_argument('--db',required=True)
    i.add_argument('--contract',required=True); i.add_argument('--source',required=True)
    r=sub.add_parser('research'); r.add_argument('--db',required=True); r.add_argument('--out',required=True)
    a=p.parse_args(); c=config(a.config)
    if a.command=='demo':
        demo(a.csv,c); print('Synthetic fixture created; not market data'); return
    if a.command=='ingest':
        print(json.dumps(ingest(a.csv,a.db,a.contract,a.source,c),indent=2)); return
    rows,meta=load(a.db,c)
    # Time split, parameters fitted solely before the boundary.
    boundary=rows[0][0]+int((rows[-1][0]-rows[0][0])*c['train_fraction'])
    train=[q for q in rows if q[0]<boundary]; test=[q for q in rows if q[0]>=boundary]
    if len(test)<2: raise ValueError('Insufficient test quotes')
    model=fit_ou(train,c)
    summary,trades,marks,predictions=replay(test,model,c)
    summary['forecast_scores'] = forecast_scores(test,predictions,c)
    stress = c.copy()
    stress.update(fee_per_side_usd=2*c['fee_per_side_usd'],
                  slippage_ticks=2*c['slippage_ticks'],latency_ms=max(500,2*c['latency_ms']))
    stressed,_,_,_=replay(test,model,stress)
    summary['cost_stress'] = dict(config=stress, results=stressed)
    gaps=[(b[0]-a[0])/NS for a,b in zip(rows,rows[1:])]
    summary.update(dataset=meta, config=c, model=model, train_end_ns=train[-1][0],
                   test_start_ns=test[0][0], test_end_ns=test[-1][0],
                   max_gap_seconds=max(gaps), gaps_over_stale_limit=sum(x>c['stale_seconds'] for x in gaps),
                   evidence='SOFTWARE_FIXTURE_ONLY' if meta['source']=='synthetic' else 'UNVERIFIED_IMPORTED_DATA',
                   benchmark='No-trade P&L = USD 0; no capital return without defined capital')
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for name,records,header in [('trades',trades,None),('equity',marks,['ts_event_ns','liquidation_pnl_usd']),
                                ('forecasts',predictions,['ts_event_ns','mid_ticks','forecast_ticks','forecast_sd_ticks'])]:
        with (out/f'{name}.csv').open('w',newline='') as f:
            w=csv.writer(f)
            if header:
                w.writerow(header); w.writerows(records)
            elif records:
                w.writerow(records[0].keys()); w.writerows(x.values() for x in records)
            else:
                w.writerow(['no_completed_trades'])
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()
