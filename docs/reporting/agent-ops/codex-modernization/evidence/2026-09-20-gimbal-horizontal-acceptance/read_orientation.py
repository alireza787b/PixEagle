"""Read ROT through a temporary sender; existing PixEagle owns response port 9004."""
import datetime,json,pathlib,socket,time
root=pathlib.Path(__file__).resolve().parent
log=root/'orientation-query.jsonl'
body=b'#TPPD2rROT00'; frame=body+f'{sum(body)&255:02X}'.encode()
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
 for _ in range(3):
  sender.sendto(frame,('192.168.0.108',9003))
  record=dict(time=time.time(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),kind='tx',hex=frame.hex(),read_only=True)
  with log.open('a') as f:f.write(json.dumps(record)+'\n')
  time.sleep(.3)
print(log)
