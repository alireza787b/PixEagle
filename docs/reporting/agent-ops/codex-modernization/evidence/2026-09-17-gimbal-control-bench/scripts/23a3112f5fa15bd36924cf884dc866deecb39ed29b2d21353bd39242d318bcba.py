"""Bounded standalone camera investigation; no PixEagle/PX4 imports."""
import argparse
import datetime
import hashlib
import json
import pathlib
import platform
import select
import socket
import struct
import threading
import time

HOST = '192.168.0.108'
ROOT = pathlib.Path('/home/alireza/PixEagle/reports/gimbal-bench')
QUERIES = [b'#TPPD2rTRC00', b'#TPPG2rGAC00', b'#TPPG2rGIC00']


def frame(body):
    return body + f'{sum(body) & 255:02X}'.encode('ascii')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['queries', 'routing', 'video', 'observe', 'describe',
                        'ai-observe', 'ai-select', 'stops', 'tracking-ready', 'pan', 'tilt', 'pan-step', 'tilt-step', 'zoom', 'home', 'point', 'box'])
    parser.add_argument('--execute-standalone-bench', action='store_true')
    parser.add_argument('--pulse-ms', type=int, choices=[150, 250, 500, 1000], default=150)
    parser.add_argument('--speed', type=int, choices=[5, 10, 20, 50], default=5)
    parser.add_argument('--direction', type=int, choices=[-1, 1], default=1)
    parser.add_argument('--x', type=float, choices=[0.4, 0.5, 0.6], default=0.5)
    parser.add_argument('--y', type=float, choices=[0.4, 0.5, 0.6], default=0.5)
    args = parser.parse_args()
    control = args.phase in ('ai-observe', 'ai-select', 'stops', 'tracking-ready', 'pan', 'tilt', 'pan-step', 'tilt-step', 'zoom', 'home', 'point', 'box')
    if control and not args.execute_standalone_bench:
        parser.error('Actuation requires --execute-standalone-bench and operator-confirmed clearance')
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

    event('start', phase=args.phase, host=HOST, python=platform.python_version(), arguments=vars(args),
          script_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
    sockets = []
    counts = {}
    cleanup = []
    watchdog = None
    stop_event = threading.Event()
    try:
        if args.phase in ('queries', 'routing') or control:
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
                        if valid and data[:3] == b'#tP' and data[7:10] == b'ODR':
                            n = data[10] if len(data) >= 13 else 0
                            if n and len(data) == 13 + 12*n:
                                boxes = [struct.unpack_from('<hhhhhh', data, 11 + j*12) for j in range(n)]
                                usable = [b for b in boxes if 0 <= b[0] < 1920 and 0 <= b[1] < 1080 and 16 <= b[2] <= 1920 and 16 <= b[3] <= 1080 and b[0]+b[2] <= 1920 and b[1]+b[3] <= 1080]
                                candidates[0] = (time.monotonic(), usable, data.hex())
                        if valid and data[7:10] == b'TRC':
                            last_status[0] = data[10:12].decode('ascii')

            last_status = [None]
            candidates = [None]

            def send(body, label):
                data = frame(body)
                sockets[0].sendto(data, (HOST, 9003))
                event('tx', label=label, local_port=sockets[0].getsockname()[1],
                      hex=data.hex(), ascii=data.decode('ascii', 'backslashreplace'))

            def poll(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    send(QUERIES[0], 'query_tracking')
                    receive(0.12)
                    send(QUERIES[1], 'query_body_angles')
                    receive(0.28)

            if control:
                poll(0.8)
                if last_status[0] != '00':
                    raise RuntimeError(f'Expected disabled general tracking baseline, got {last_status[0]}')
                event('operator_clearance', standalone=True, phase=args.phase)
                movement_stop = b'#TPPG2wPTZ00'
                zoom_stop = b'#TPPM2wZMC00'
                disable = b'#TPPD2wTRC00'
                cleanup = [movement_stop, zoom_stop, disable]
                if args.phase in ('ai-observe', 'ai-select'):
                    cleanup.append(b'#TPPD2wFED20')

                def independent_stop():
                    # Separate socket/thread is a second best-effort stop sender,
                    # NOT a hardware watchdog or process/network-loss guarantee.
                    if stop_event.wait(18 if args.phase in ('ai-observe', 'ai-select') else 8):
                        return
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as guard:
                        for _ in range(3):
                            for body in cleanup:
                                guard.sendto(frame(body), (HOST, 9003))
                            time.sleep(0.03)

                watchdog = threading.Thread(target=independent_stop, daemon=True)
                watchdog.start()
                for body in (movement_stop, zoom_stop):
                    send(body, 'pre_stop')
                    receive(0.03)
                    send(body, 'pre_stop_repeat')
                poll(0.8)
                if args.phase in ('ai-observe', 'ai-select'):
                    send(b'#TPPD2wFED10', 'enable_detection_output')
                    send(b'#TPPD2wTRC02', 'prepare_detection')
                    for _ in range(3):
                        poll(1.2)
                    if args.phase == 'ai-select':
                        sample = candidates[0]
                        if last_status[0] != '01' or sample is None or time.monotonic()-sample[0] > 0.6 or not sample[1]:
                            raise RuntimeError('No fresh bounded detection in ready state; no selection sent')
                        box = min(sample[1], key=lambda b: ((b[0]+b[2]/2)/1920-.5)**2+((b[1]+b[3]/2)/1080-.5)**2)
                        x,y,w,h,label,confidence = box
                        cx,cy = round(((x+w/2)/1920-.5)*2000), round(((y+h/2)/1080-.5)*2000)
                        event('detection_selection', source_packet=sample[2], source_age=time.monotonic()-sample[0], bbox=list(box), wire_center=[cx,cy], descriptor_hex='0008', note='Bench coordinate interpretation; class mapping unknown')
                        send(b'#tpPDAwLOC' + struct.pack('>hhhhH', cx,cy,67,119,8), 'select_documented_fuzzy_detection')
                    poll(3.2)
                    send(b'#TPPD2wTRC01', 'cancel_to_ready')
                    poll(0.8)
                    send(b'#TPPD2wFED20', 'disable_detection_output')
                    poll(1.2)
                    send(disable, 'disable')
                    poll(0.8)
                elif args.phase in ('tracking-ready', 'point', 'box'):
                    send(b'#TPPD2wTRC02', 'prepare')
                    poll(0.8)
                    if last_status[0] != '01':
                        raise RuntimeError(f'Prepare did not produce ready state: {last_status[0]}')
                    if args.phase in ('point', 'box'):
                        width, height, flag = (62, 111, 9) if args.phase == 'point' else (200, 200, 1)
                        cx, cy = round((args.x - 0.5)*2000), round((args.y - 0.5)*2000)
                        payload = b'#tpPDAwLOC' + struct.pack('>hhhhBB', cx, cy, width, height, 0, flag)
                        event('selection_geometry', normalized_center=[args.x, args.y],
                              wire_center=[cx, cy], wire_size=[width, height], selection_flag=flag)
                        send(payload, 'select_' + args.phase)
                        poll(1.2)
                    send(b'#TPPD2wTRC01', 'cancel_to_ready')
                    poll(0.8)
                    send(disable, 'disable')
                    poll(0.8)
                elif args.phase in ('pan', 'tilt', 'pan-step', 'tilt-step', 'zoom'):
                    commands = {
                        'pan': (f'#TPUG2wGSY{args.speed:02X}'.encode(), f'#TPUG2wGSY{(-args.speed)&255:02X}'.encode(), movement_stop),
                        'tilt': (f'#TPUG2wGSP{args.speed:02X}'.encode(), f'#TPUG2wGSP{(-args.speed)&255:02X}'.encode(), movement_stop),
                        'zoom': (b'#TPPM2wZMC02', b'#TPPM2wZMC01', zoom_stop),
                    }
                    axis = args.phase.removesuffix('-step')
                    positive, negative, halt = commands[axis]
                    bodies = (positive, negative)
                    if args.phase.endswith('-step'):
                        bodies = (positive if args.direction == 1 else negative,)
                    for body in bodies:
                        send(body, args.phase + f'_pulse_{args.pulse_ms}ms')
                        receive(args.pulse_ms / 1000)
                        send(halt, 'pulse_stop')
                        receive(0.03)
                        send(halt, 'pulse_stop_repeat')
                        poll(1.2)
                elif args.phase == 'home':
                    send(b'#TPPG2wPTZ05', 'home')
                    poll(2)
                else:
                    poll(0.8)
                event('summary', received=counts, final_observed_tracking=last_status[0])
                return

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
            for transport in (('tcp',) if args.phase == 'observe' else ('tcp', 'udp')):
                try:
                    with av.open(f'rtsp://{HOST}:554/stream=0',
                                 options={'rtsp_transport': transport}, timeout=(5, 5)) as video:
                        stream = video.streams.video[0]
                        event('stream', transport=transport, codec=stream.codec_context.name,
                              width=stream.width, height=stream.height, rate=str(stream.average_rate))
                        last_saved = 0
                        observed_start = time.monotonic()
                        for i, decoded in enumerate(video.decode(stream)):
                            now = time.monotonic()
                            if args.phase == 'observe' and now - last_saved < 0.5:
                                continue
                            last_saved = now
                            path = out / f'{transport}-{i}.png'
                            decoded.to_image().save(path)
                            event('decoded_frame', transport=transport, width=decoded.width,
                                  height=decoded.height, pts=decoded.pts, time_base=str(decoded.time_base),
                                  file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                            if (args.phase != 'observe' and i >= 1) or (args.phase == 'observe' and now-observed_start >= 10):
                                break
                except Exception as exc:
                    event('video_error', transport=transport, error=str(exc), error_type=type(exc).__name__)
    except Exception as exc:
        event('error', error=str(exc), error_type=type(exc).__name__)
        raise
    finally:
        if cleanup and sockets:
            for _ in range(3):
                for body in cleanup:
                    try:
                        sockets[0].sendto(frame(body), (HOST, 9003))
                        event('cleanup_tx', hex=frame(body).hex())
                    except OSError as exc:
                        event('cleanup_error', error=str(exc))
                time.sleep(0.03)
        stop_event.set()
        if watchdog:
            watchdog.join(timeout=0.2)
        for sock in sockets:
            sock.close()
        event('end', evidence=str(out))
        log.close()


if __name__ == '__main__':
    main()
