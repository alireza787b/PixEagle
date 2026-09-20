"""Bounded camera selection through the API with observational divergence abort."""
import json,math,sys,time
from session_actions import action,event,http,ROOT
x,y=map(float,sys.argv[1:3]);duration=float(sys.argv[3]) if len(sys.argv)>3 else 4
start=time.time();threshold=max(250,math.hypot(x*1920-960,y*1080-540)*1.7+80)
def latest_box():
 with (ROOT/'wire.jsonl').open('rb') as f:
  f.seek(0,2);f.seek(max(0,f.tell()-50000));lines=f.read().splitlines()
 for l in reversed(lines):
  try:r=json.loads(l)
  except ValueError:continue
  b=bytes.fromhex(r['hex'])
  if r['kind']=='rx' and b[7:10]==b'OFT' and r['time']>=start and time.time()-r['time']<.6:
   import struct
   a,c,w,h,s=struct.unpack('<hhhhB',b[10:19]);return dict(time=r['time'],box=[a,c,w,h],center=[a+w/2,c+h/2],state=s)
try:
 action('select',x=x,y=y);end=time.monotonic()+duration
 while time.monotonic()<end:
  time.sleep(.15);box=latest_box();status=http('/api/v1/gimbal/control');event('selection_observation',box=box,status=status)
  if status['tracking_state']=='target_lost':event('abort',reason='camera_reported_target_lost');break
  if box and box['box'][2] and math.hypot(box['center'][0]-960,box['center'][1]-540)>threshold:
   event('abort',reason='box_moving_farther_from_center',threshold=threshold);break
finally:
 try:action('cancel')
 finally:action('stop');event('selection_end')
