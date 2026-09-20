"""Operator-authorized acceptance actions through PixEagle's normal API."""
import datetime,json,pathlib,sys,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parent
LOG=ROOT/'corrected-orientation-actions.jsonl'
def event(kind,**kw):
 r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),time=time.time(),kind=kind,**kw)
 with LOG.open('a') as f:f.write(json.dumps(r)+'\n')
 return r
def http(path,method='GET',body=None):
 req=urllib.request.Request('http://127.0.0.1:5077'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=8) as r:out=json.load(r)
 event('api',path=path,request=body,response=out)
 return out
def action(op,**kw):
 r=http('/api/v1/actions/gimbal-control','POST',dict(operation=op,confirm=True,idempotency_key='camera-check-'+str(time.time_ns()),source='dashboard',reason='corrected_camera_orientation_acceptance',**kw))
 if r.get('status')!='success' or not r.get('result',{}).get('success'):raise RuntimeError(str(r))
 return r
if __name__=='__main__':
 r=action(sys.argv[1],**(json.loads(sys.argv[2]) if len(sys.argv)>2 else {}))
 print(json.dumps(r['result']))
