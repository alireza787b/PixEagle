"""Bounded standalone camera investigation; no PixEagle/PX4 imports."""
import argparse
import datetime
import hashlib
import json
import pathlib
import platform
import select
import socket
import time

HOST = '192.168.0.108'
ROOT = pathlib.Path('/home/alireza/PixEagle/reports/gimbal-bench')
QUERIES = [b'#TPPD2rTRC00', b'#TPPG2rGAC00', b'#TPPG2rGIC00']


def frame(body):
    return body + f'{sum(body) & 255:02X}'.encode('ascii')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['queries', 'routing', 'video', 'describe'])
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / f'{stamp}-{args.phase}'
    out.mkdir(parents=True, exist_ok=False)
    (out / 'bench_probe.py').write_bytes(pathlib.Path(__file__).read_bytes())
    log = (out / 'events.jsonl').open('w')
    start = time.monotonic()

    def event(kind, **fields):
        row = dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   elapsed=round(time.monotonic()-start, 6), kind=kind, **fields)
        log.write(json.dumps(row) + '\n')
        log.flush()
        if kind != 'rx':
            print(json.dumps(row), flush=True)

    event('start', phase=args.phase, host=HOST, python=platform.python_version(),
          script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
    sockets = []
    counts = {}
    try:
        if args.phase in ('queries', 'routing'):
            for port in (8080, 9004, 0):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                # No reuse: fail if another controller already owns this port.
                sock.bind(('0.0.0.0', port))
                sock.setblocking(False)
                sockets.append(sock)
                event('bind', port=sock.getsockname()[1])

            def receive(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    ready, _, _ = select.select(sockets, [], [], max(0, end-time.monotonic()))
                    for sock in ready:
                        data, peer = sock.recvfrom(65535)
                        if peer[0] != HOST:
                            event('ignored_peer', peer=peer)
                            continue
                        port = sock.getsockname()[1]
                        key = f'{peer[0]}:{peer[1]}->{port}'
                        counts[key] = counts.get(key, 0) + 1
                        valid = len(data) >= 2 and data[-2:] == f'{sum(data[:-2]) & 255:02X}'.encode()
                        event('rx', local_port=port, peer=peer, hex=data.hex(),
                              ascii=data.decode('ascii', 'backslashreplace'), checksum_valid=valid)

            event('passive_begin')
            receive(2)
            steps = [(sock, body) for sock in sockets for body in QUERIES]
            if args.phase == 'routing':
                steps = [(sockets[i], QUERIES[0]) for i in (2, 1, 0, 1, 2, 1)]
            for sock, body in steps:
                    data = frame(body)
                    sock.sendto(data, (HOST, 9003))
                    event('tx', local_port=sock.getsockname()[1], hex=data.hex(), ascii=data.decode())
                    receive(0.8)
            receive(1)
            event('summary', received=counts)
        elif args.phase == 'describe':
            for seq, method in enumerate(('OPTIONS', 'DESCRIBE'), 1):
                with socket.create_connection((HOST, 554), timeout=4) as sock:
                    req = (f'{method} rtsp://{HOST}:554/stream=0 RTSP/1.0\r\n'
                           f'CSeq: {seq}\r\nAccept: application/sdp\r\n\r\n').encode()
                    sock.sendall(req)
                    data = b''
                    while b'\r\n\r\n' not in data:
                        data += sock.recv(65536)
                        if len(data) > 65536:
                            raise ValueError('Oversized RTSP header')
                    header, body = data.split(b'\r\n\r\n', 1)
                    length = 0
                    for line in header.split(b'\r\n'):
                        if line.lower().startswith(b'content-length:'):
                            length = int(line.split(b':', 1)[1])
                    if length > 65536:
                        raise ValueError('Oversized RTSP description')
                    while len(body) < length:
                        chunk = sock.recv(65536)
                        if not chunk:
                            break
                        body += chunk
                    event('rtsp_response', method=method, headers=header.decode('ascii', 'replace'),
                          body=body.decode('ascii', 'replace'))
        else:
            import av
            event('decoder', av_version=av.__version__, libraries=av.library_versions)
            for transport in ('tcp', 'udp'):
                try:
                    with av.open(f'rtsp://{HOST}:554/stream=0',
                                 options={'rtsp_transport': transport}, timeout=(5, 5)) as video:
                        stream = video.streams.video[0]
                        event('stream', transport=transport, codec=stream.codec_context.name,
                              width=stream.width, height=stream.height, rate=str(stream.average_rate))
                        for i, decoded in enumerate(video.decode(stream)):
                            path = out / f'{transport}-{i}.png'
                            decoded.to_image().save(path)
                            event('decoded_frame', transport=transport, width=decoded.width,
                                  height=decoded.height, pts=decoded.pts, time_base=str(decoded.time_base),
                                  file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                            if i >= 1:
                                break
                except Exception as exc:
                    event('video_error', transport=transport, error=str(exc), error_type=type(exc).__name__)
    except Exception as exc:
        event('error', error=str(exc), error_type=type(exc).__name__)
        raise
    finally:
        for sock in sockets:
            sock.close()
        event('end', evidence=str(out))
        log.close()


if __name__ == '__main__':
    main()
