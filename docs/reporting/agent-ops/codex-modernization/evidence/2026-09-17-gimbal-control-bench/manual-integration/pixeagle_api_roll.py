import json,time,urllib.request, pathlib
root=pathlib.Path('/home/alireza/PixEagle/reports/gimbal-manual-integration')
log=(root/'resume-controls-api.jsonl').open('a')
def event(kind,**kw):
 r=dict(time=time.time(),kind=kind,**kw);log.write(json.dumps(r)+'\n');log.flush();print(json.dumps(r),flush=True)
def action(operation,**kw):
 payload=dict(operation=operation,confirm=True,idempotency_key='resume-'+str(time.time_ns()),source='dashboard',reason='standalone_integration_roll_check',**kw)
 req=urllib.request.Request('http://127.0.0.1:5077/api/v1/actions/gimbal-control',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=6) as r: result=json.load(r)
 event('action',request=payload,response=result)
 return result.get('result',{}).get('success') is True

def angles():
 with (root/'wire.jsonl').open('rb') as f:
  f.seek(0,2);f.seek(max(0,f.tell()-40000));lines=f.read().splitlines()
 for line in reversed(lines):
  r=json.loads(line);b=bytes.fromhex(r['hex'])
  if r['kind']=='rx' and b[7:10]==b'GAC' and len(b)==24 and time.time()-r['time']<1.2:
   vals=[int(b[i:i+4],16) for i in (10,14,18)]
   return [(v-65536 if v>32767 else v)/100 for v in vals]
 raise RuntimeError('No fresh GAC')
try:
 event('initial',angles=angles())
 for direction in (1,-1):
  if not action('roll',direction=direction):raise RuntimeError('Roll failed')
  time.sleep(.6);event('roll_observation',direction=direction,angles=angles())
finally:action('stop');event('end')
