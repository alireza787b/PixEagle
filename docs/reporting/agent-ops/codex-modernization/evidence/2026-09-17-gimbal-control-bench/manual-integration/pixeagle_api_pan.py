import json,time,urllib.request, pathlib
root=pathlib.Path('/home/alireza/PixEagle/reports/gimbal-manual-integration')
log=(root/'resume-pan-api.jsonl').open('a')
def event(kind,**kw):
 r=dict(time=time.time(),kind=kind,**kw);log.write(json.dumps(r)+'\n');log.flush();print(json.dumps(r),flush=True)
def action(operation,**kw):
 payload=dict(operation=operation,confirm=True,idempotency_key='resume-'+str(time.time_ns()),source='dashboard',reason='operator_requested_40_degree_left_pan',**kw)
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
 initial=angles();event('initial',angles=initial)
 for n in range(20):
  if not action('pan',direction=-1): raise RuntimeError('Pan failed')
  time.sleep(.35);current=angles();event('step',index=n,angles=current,yaw_change=current[0]-initial[0])
  if abs(current[0])>145 or current[0]-initial[0]<=-38:break
  if n>=2 and current[0]-initial[0]>2:raise RuntimeError('Unexpected yaw direction')
finally:action('stop');event('end')
