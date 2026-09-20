"""Offline restart check: file input, no external tracker or flight publication."""
import importlib.util,json,pathlib,sys,os
root=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('bench',root/'reports/gimbal-manual-integration/restartable_bench.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
bench.BENCH=root/'reports/gimbal-restart-offline';bench.CONFIG=bench.BENCH/'bench-config.yaml'
original=bench.validate_config
def validate():
 c=original()
 assert c['VideoSource']['VIDEO_SOURCE_TYPE']=='VIDEO_FILE'
 assert c['GimbalTracker']['ENABLED'] is False
 assert c['GimbalTracker']['CONTROL_ENABLED'] is False
 assert c['Tracking']['DEFAULT_TRACKING_ALGORITHM']=='CSRT'
 return c
bench.validate_config=validate
configure=bench.configure_runtime
def configure_runtime():
 p,s=configure();print(json.dumps(dict(kind='offline_config_loaded',pid=os.getpid(),rotation=p.FRAME_ROTATION_DEG)),flush=True);return p,s
bench.configure_runtime=configure_runtime
if '--child' in sys.argv:raise SystemExit(bench.child())
raise SystemExit(bench.supervise([sys.executable,'-u',__file__,'--child']))
