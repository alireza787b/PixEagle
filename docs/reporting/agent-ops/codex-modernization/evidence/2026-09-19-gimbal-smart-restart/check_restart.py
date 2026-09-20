import datetime,hashlib,json,os,pathlib,signal,subprocess,sys,time,urllib.request
root=pathlib.Path(__file__).resolve().parents[2];folder=root/'reports/gimbal-restart-offline';events=[]
def record(kind,**kw):
 r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind=kind,**kw);events.append(r);(folder/'result.json').write_text(json.dumps(events,indent=2)+'\n');print(json.dumps(r),flush=True)
def digest():return hashlib.sha256((root/'configs/config.yaml').read_bytes()).hexdigest()
def http(path,method='GET',body=None):
 req=urllib.request.Request('http://127.0.0.1:5079'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=3) as r:return json.load(r)
def child_pid():
 s=pathlib.Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().strip();return int(s.split()[0]) if s else None
before=digest();console=(folder/'runtime.log').open('w');process=subprocess.Popen([sys.executable,str(folder/'launcher.py')],cwd=root,stdout=console,stderr=subprocess.STDOUT);owned_pid=None
try:
 deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  try:
   state=http('/api/v1/gimbal/control');break
  except Exception:
   if process.poll() is not None:raise RuntimeError('Supervisor exited before API startup')
   time.sleep(.4)
 else:raise TimeoutError('Initial API startup')
 owned_pid=old_pid=child_pid();assert not state['enabled'];record('initial',supervisor_pid=process.pid,backend_pid=old_pid,camera_control=state,user_config_sha256=before)
 update=http('/api/config/VideoSource/FRAME_ROTATION_DEG','PUT',{'value':180});record('saved_rotation',response=update)
 record('pending_config',response=http('/api/v1/config/runtime-status'))
 response=http('/api/v1/actions/system-restart','POST',{'confirm':True,'idempotency_key':'offline-restart-'+str(time.time_ns()),'source':'dashboard','reason':'offline_gimbal_integration_restart_regression'});record('restart_requested',response=response);assert response['accepted']
 deadline=time.monotonic()+45
 while time.monotonic()<deadline:
  pid=child_pid()
  if pid and pid!=old_pid:
   owned_pid=pid
   try:
    state=http('/api/v1/gimbal/control');runtime=http('/api/v1/config/runtime-status');break
   except Exception:pass
  if process.poll() is not None:raise RuntimeError('Supervisor exited during restart')
  time.sleep(.4)
 else:raise TimeoutError('Replacement backend startup')
 record('restarted',backend_pid=owned_pid,camera_control=state,config_runtime=runtime)
 assert digest()==before,'User configuration changed'
 log=(folder/'runtime.log').read_text();assert 'shutdown exceeded' not in log
 loaded=[json.loads(line) for line in log.splitlines() if line.startswith('{"kind": "offline_config_loaded"')]
 assert [x['rotation'] for x in loaded]==[0,180],loaded
 assert (folder/'wire.jsonl').stat().st_size==0,'Unexpected camera traffic'
 record('passed',configuration_rotations=[x['rotation'] for x in loaded],user_config_unchanged=True,camera_packets=0)
except Exception as exc:record('error',error=str(exc));raise
finally:
 process.terminate()
 try:process.wait(timeout=12)
 except subprocess.TimeoutExpired:
  if owned_pid:
   try:os.killpg(owned_pid,signal.SIGKILL)
   except ProcessLookupError:pass
  process.wait(timeout=3)
 console.close();record('cleanup',supervisor_exit=process.returncode,user_config_unchanged=digest()==before)
