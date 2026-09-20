"""Passive native-video capture during operator-controlled camera tracking."""
import datetime,hashlib,json,pathlib,time,platform,sys
import av
root=pathlib.Path('/home/alireza/PixEagle/reports/gimbal-bench')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=root/(stamp+'-user-manual-observe');out.mkdir();(out/'bench_probe.py').write_bytes(pathlib.Path(__file__).read_bytes());log=(out/'events.jsonl').open('w');start=time.monotonic()
def event(kind,**kw):
 r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed=time.monotonic()-start,kind=kind,**kw);log.write(json.dumps(r)+'\n');log.flush()
 if kind!='decoded_frame':print(json.dumps(r),flush=True)
event('start',phase='user-manual-observe',host='192.168.0.108',python=platform.python_version(),arguments={'duration_seconds':180,'saved_fps':5,'actuation':False},script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
try:
 event('decoder',av_version=av.__version__,libraries=av.library_versions)
 with av.open('rtsp://192.168.0.108:554/stream=0',options={'rtsp_transport':'tcp'},timeout=(5,5)) as video:
  stream=video.streams.video[0];event('stream',width=stream.width,height=stream.height,rate=str(stream.average_rate));last=0
  for i,f in enumerate(video.decode(stream)):
   received=time.time();now=time.monotonic()
   if now-start>=180:break
   if now-last<.2:continue
   last=now;im=f.to_image();im.thumbnail((960,540));p=out/f'frame-{i:06}.jpg';im.save(p,quality=90)
   event('decoded_frame',received_wall_time=received,file=p.name,width=f.width,height=f.height,saved_width=im.width,saved_height=im.height,pts=f.pts,time_base=str(f.time_base),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
except Exception as exc:event('error',error=str(exc));raise
finally:event('end',evidence=str(out));log.close()
