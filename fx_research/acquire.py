"""Databento cost estimate and historical CSV capture. Standard library only."""
import argparse, base64, csv, getpass, hashlib, json, math, os, shutil, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from decimal import Decimal

BASE='https://hist.databento.com/v0/'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('API redirect refused to keep credentials on the intended host')

class API:
    def __init__(self):
        key=os.environ.get('DATABENTO_API_KEY')
        if not key and sys.stdin.isatty():
            key=getpass.getpass('Databento API key (hidden; kept in memory): ')
        if not key:
            raise ValueError('DATABENTO_API_KEY is missing. Set it locally; do not paste it into chat.')
        self.auth='Basic '+base64.b64encode((key+':').encode()).decode()
        self.opener=build_opener(NoRedirect())
    def request(self, method, params, post=False):
        payload=urlencode(params).encode()
        url=BASE+method
        if not post: url+='?'+payload.decode()
        request=Request(url,data=payload if post else None,
                        headers={'Authorization':self.auth,'Content-Type':'application/x-www-form-urlencoded'},
                        method='POST' if post else 'GET')
        try:
            return self.opener.open(request,timeout=60)
        except HTTPError as error:
            # Never echo request headers or a raw response that might contain credentials.
            raise RuntimeError(f'Provider HTTP {error.code}; inspect your account, entitlement and request parameters') from None
    def json(self,method,params,post=False):
        with self.request(method,params,post) as response:
            return json.load(response)
    def capture(self,params,path):
        partial=path.with_suffix(path.suffix+'.partial')
        if path.exists() or partial.exists():
            raise ValueError('Existing capture or partial capture protected; resolve it before another billed request')
        args=dict(params,encoding='csv',compression='none',pretty_px='true',pretty_ts='false',map_symbols='true')
        with self.request('timeseries.get_range',args,True) as response, partial.open('xb') as output:
            shutil.copyfileobj(response,output,1024*1024)
        partial.rename(path)
        return dict(path=str(path),sha256=file_hash(path),bytes=path.stat().st_size)

def file_hash(path):
    digest=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()

def requests(plan):
    if plan['dataset']!='GLBX.MDP3' or plan['stype_in']!='raw_symbol':
        raise ValueError('This pilot supports one raw CME contract only')
    if set(plan['schemas'])!={'mbp-1','definition'}:
        raise ValueError('This pilot expects MBP-1 and definitions; no duplicated trade download')
    if not plan['dates'] or plan['dates'] != sorted(set(plan['dates'])):
        raise ValueError('Dates must be unique and ascending')
    if not plan['symbol'] or any(x in plan['symbol'] for x in (',','.', '/')):
        raise ValueError('Use one explicit expiry symbol, not parent/continuous symbology')
    result=[]
    for day in plan['dates']:
        date.fromisoformat(day)
        start=day+'T'+plan['quote_start_utc']; end=day+'T'+plan['quote_end_utc']
        if datetime.fromisoformat(start)>=datetime.fromisoformat(end):
            raise ValueError('Start must be before end within each session')
        result.append(dict(dataset=plan['dataset'],symbols=plan['symbol'],stype_in='raw_symbol',
                           schema='mbp-1',start=start,end=end))
    # Definitions use a full UTC day so the documented estimate granularity is respected.
    result.insert(0,dict(dataset=plan['dataset'],symbols=plan['symbol'],stype_in='raw_symbol',
                        schema='definition',start=plan['dates'][0]+'T00:00:00Z',
                        end=str(date.fromisoformat(plan['dates'][0])+timedelta(days=1))+'T00:00:00Z'))
    return result

def estimate(api,plan):
    end=str(date.fromisoformat(plan['dates'][-1])+timedelta(days=1))
    resolution=api.json('symbology.resolve',dict(dataset=plan['dataset'],symbols=plan['symbol'],
                        stype_in='raw_symbol',stype_out='instrument_id',start_date=plan['dates'][0],end_date=end),True)
    if resolution.get('not_found') or resolution.get('partial') or not resolution.get('result',{}).get(plan['symbol']):
        raise ValueError('Symbol not resolved for the whole requested date range; no data request made')
    entries=[]
    for req in requests(plan):
        cost=float(api.json('metadata.get_cost',req))
        if not math.isfinite(cost) or cost<0: raise ValueError('Invalid provider estimate')
        entries.append(dict(request=req,estimated_usd=cost))
    return dict(created_utc=datetime.now(timezone.utc).isoformat(),plan=plan,resolution=resolution,
                entries=entries,total_estimated_usd=sum(x['estimated_usd'] for x in entries),
                status='ESTIMATE_ONLY',notes='Estimated data usage only; taxes, licensing, FX and credit eligibility are excluded. Actual billed bytes govern the charge.')

def download(api,plan,out,max_usd):
    if not math.isfinite(max_usd) or max_usd<=0: raise ValueError('Specify a positive finite USD cap')
    jobs=requests(plan)
    paths=[out/(r['schema']+'_'+r['start'][:10]+'.csv') for r in jobs]
    if any(p.exists() or p.with_suffix(p.suffix+'.partial').exists() for p in paths):
        raise ValueError('Capture files already exist; downloads are not silently repeated')
    quote=estimate(api,plan)
    # Conservative headroom, not a billing guarantee; provider-side account limits remain authoritative.
    if quote['total_estimated_usd']*1.1>max_usd:
        raise ValueError('Estimate plus 10% headroom exceeds the requested USD cap; no download made')
    out.mkdir(parents=True,exist_ok=True)
    manifest=dict(quote, status='CAPTURE_IN_PROGRESS',max_usd=max_usd,captures=[])
    manifest_path=out/'capture_manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    for entry,path in zip(quote['entries'],paths):
        result=api.capture(entry['request'],path)
        manifest['captures'].append(dict(result,request=entry['request']))
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    manifest['status']='CAPTURE_COMPLETE_NOT_YET_VALIDATED'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest

def normalize(path,out,symbol,tick_size='0.00005'):
    """Preserve event/receive timestamps, sequences and file order. No manufactured ticks."""
    if out.exists(): raise ValueError('Existing normalized output protected')
    partial=out.with_suffix(out.suffix+'.partial')
    if partial.exists(): raise ValueError('Existing partial normalization protected')
    report=dict(raw_sha256=file_hash(path),rows=0,quotes=0,trades=0,invalid_quotes=0,
                symbol=symbol,clock='ts_recv_ns',max_spread_ticks=0,equal_receive_timestamps=0)
    previous=-1
    try:
        with open(path,newline='') as raw, partial.open('x',newline='') as output:
            reader=csv.DictReader(raw)
            required={'ts_event','ts_recv','sequence','symbol','bid_px_00','ask_px_00','bid_sz_00','ask_sz_00'}
            if not required.issubset(reader.fieldnames or []): raise ValueError('Unexpected vendor CSV schema')
            writer=csv.writer(output)
            writer.writerow(['ts_event_ns','ts_recv_ns','sequence','bid','ask','bid_size','ask_size'])
            for row in reader:
                report['rows']+=1
                if row['symbol']!=symbol: raise ValueError('Unexpected contract in vendor capture')
                received=int(row['ts_recv']); event=int(row['ts_event']); seq=int(row['sequence'])
                if received<previous: raise ValueError('Receive timestamps out of order; inspect source, do not sort blindly')
                if received==previous: report['equal_receive_timestamps']+=1
                previous=received
                if row.get('action')=='T': report['trades']+=1
                try:
                    bid=Decimal(row['bid_px_00']); ask=Decimal(row['ask_px_00'])
                    bs=int(row['bid_sz_00']); ass=int(row['ask_sz_00']); tick=Decimal(tick_size)
                    valid=bid.is_finite() and ask.is_finite() and 0<bid<=ask and min(bs,ass)>0
                    valid=valid and bid/tick==(bid/tick).to_integral_value() and ask/tick==(ask/tick).to_integral_value()
                except (ArithmeticError,ValueError): valid=False
                if not valid:
                    report['invalid_quotes']+=1
                    continue
                report['max_spread_ticks']=max(report['max_spread_ticks'],int((ask-bid)/tick))
                report['quotes']+=1
                writer.writerow([event,received,seq,str(bid),str(ask),bs,ass])
        if report['invalid_quotes'] or report['quotes']<2:
            raise ValueError('Invalid/missing quotes found; quality report written, research import blocked pending explicit handling')
        partial.rename(out)
        report['normalized_sha256']=file_hash(out)
        report['status']='NORMALIZED; contract definitions and quality flags still require review'
        return report
    finally:
        if partial.exists(): partial.unlink()
        out.with_suffix('.quality.json').write_text(json.dumps(report,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',default='data_request.json')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('plan')
    e=sub.add_parser('estimate'); e.add_argument('--out',default='cost_estimate.json')
    d=sub.add_parser('download'); d.add_argument('--out',default='captures'); d.add_argument('--max-usd',type=float,required=True)
    n=sub.add_parser('normalize'); n.add_argument('--csv',required=True); n.add_argument('--out',required=True)
    a=p.parse_args(); plan=json.loads(Path(a.plan).read_text())
    if a.command=='plan':
        print(json.dumps(requests(plan),indent=2)); return
    if a.command=='normalize':
        print(json.dumps(normalize(a.csv,Path(a.out),plan['symbol']),indent=2)); return
    api=API()
    if a.command=='estimate':
        result=estimate(api,plan)
        Path(a.out).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2)); return
    result=download(api,plan,Path(a.out),a.max_usd)
    print(json.dumps(dict(status=result['status'],captures=len(result['captures']),estimated_usd=result['total_estimated_usd']),indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,RuntimeError) as error:
        raise SystemExit(str(error)) from None
