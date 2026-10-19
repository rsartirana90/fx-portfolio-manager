"""Synthetic API demonstration only. No market feed, fills, P&L or orders."""
from datetime import datetime,timedelta,timezone
import json
import math
import random
try:
    from .signals import generate_signal
except ImportError:
    from signals import generate_signal


def main():
    rng=random.Random(703);state=0.0;bars=[]
    start=datetime(2026,1,5,tzinfo=timezone.utc)
    for i in range(160):
        state=.85*state+rng.gauss(0,.0001)
        close=1.1*math.exp(state+i*.00001)
        t=start+timedelta(seconds=300*i)
        bars.append(dict(symbol='SYNTHETIC',timestamp_utc=t.isoformat(),
            available_utc=(t+timedelta(seconds=300)).isoformat(),
            open=close,high=close,low=close,close=close,complete=True,price_basis='bid'))
    now=bars[-1]['available_utc'];bid=bars[-1]['close']
    result=generate_signal(bars,symbol='SYNTHETIC',decision_utc=now,
        quote=dict(symbol='SYNTHETIC',timestamp_utc=now,bid=bid,ask=bid+.00001),
        costs=dict(exit_spread_bps=.1,round_trip_fees_bps=0.0,slippage_bps_per_side=0.0))
    result['example_warning']='SYNTHETIC SOFTWARE DEMONSTRATION; cost estimates are fictional'
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
