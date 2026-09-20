"""Standalone camera ROT read/write probe; no motor or tracking commands."""
import argparse,datetime,hashlib,json,pathlib,select,socket,time
p=argparse.ArgumentParser();p.add_argument('--set',choices=['00','02']);a=p.parse_args();root=pathlib.Path('/home/alireza/PixEagle/reports/gimbal-bench');out=root/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-rotation-config');out.mkdir();(out/'bench_probe.py').write_bytes(pathlib.Path(__file__).read_bytes());log=(out/'events.jsonl').open('w');start=time.monotonic();sockets=[]
def event(kind,**kw):
 r=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed=time.monotonic()-start,kind=kind,**kw);log.write(json.dumps(r)+'\n');log.flush();print(json.dumps(r),flush=True)
def send(body):
 b=body+f'{sum(body)&255:02X}'.encode();sockets[0].sendto(b,('192.168.0.108',9003));event('tx',hex=b.hex(),ascii=b.decode())
def receive(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  ready,_,_=select.select(sockets,[],[],max(0,end-time.monotonic()))
  for s in ready:
   b,peer=s.recvfrom(65535)
   if peer[0]=='192.168.0.108':event('rx',peer=peer,local_port=s.getsockname()[1],hex=b.hex(),ascii=b.decode('ascii','backslashreplace'),checksum_valid=b[-2:]==f'{sum(b[:-2])&255:02X}'.encode())
event('start',phase='rotation-config',arguments=vars(a),script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
try:
 for port in (8080,9004):
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('0.0.0.0',port));sockets.append(s)
 send(b'#TPPD2rROT00');receive(.5)
 if a.set:
  send(b'#TPPD2wROT'+a.set.encode());receive(1)
 for _ in range(4):send(b'#TPPD2rROT00');receive(.5)
finally:
 for s in sockets:s.close()
 event('end',evidence=str(out));log.close()
