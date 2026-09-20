"""Local camera integration runtime with isolated configuration and no following."""
import os
os.environ.setdefault('YOLO_AUTOINSTALL','False')
from classes.parameters import Parameters
Parameters.load_config('reports/gimbal-manual-integration/bench-config.yaml', strict_dependents=True)
assert Parameters.FOLLOWER_CIRCUIT_BREAKER is True
assert Parameters.FOLLOWER_EXECUTION_MODE == 'COMMAND_PREVIEW'
assert Parameters.MAVLINK_ENABLED is False
import json, threading, time
from pathlib import Path
from classes.gimbal_interface import GimbalInterface
output = Path('reports/gimbal-manual-integration/wire.jsonl').open('a')
wire_lock = threading.Lock()
def wire(kind, data, **extra):
    if isinstance(data, str): data=data.encode('ascii')
    with wire_lock:
        output.write(json.dumps(dict(time=time.time(),kind=kind,hex=data.hex(),**extra))+'\n');output.flush()
original_send=GimbalInterface._send_command
original_parse=GimbalInterface._parse_gimbal_packet
def send(self,data):
    result=original_send(self,data)
    wire('tx',data,sent=result)
    return result
def parse(self,data,**kwargs):
    result=original_parse(self,data,**kwargs)
    wire('rx',data,accepted=result is not None,**kwargs)
    return result
GimbalInterface._send_command=send
GimbalInterface._parse_gimbal_packet=parse
from main import main
raise SystemExit(main())
