"""One operator-authorized camera-axis pulse through PixEagle; no follower start.

Run one axis/direction at a time and inspect video before the next invocation.
The API owns the 250 ms pulse and best-effort stop; this is not a hardware watchdog.
"""
import argparse
import datetime
import json
from pathlib import Path
import time
import urllib.request

BASE = 'http://127.0.0.1:5077'
ROOT = Path(__file__).resolve().parent


def run(axis, direction):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = ROOT / f'{stamp}-{axis}-{direction:+d}.jsonl'
    with path.open('w') as log:
        def record(kind, **values):
            row = dict(time=time.time(), kind=kind, **values)
            log.write(json.dumps(row) + '\n')
            log.flush()

        def http(endpoint, body=None):
            request = urllib.request.Request(
                BASE + endpoint, data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=8) as response:
                result = json.load(response)
            record('api', endpoint=endpoint, request=body, response=result)
            return result

        def action(operation, **kwargs):
            return http('/api/v1/actions/gimbal-control', dict(
                operation=operation, confirm=True, source='dashboard',
                reason='standalone_vertical_mount_axis_characterization',
                idempotency_key='vertical-axis-' + str(time.time_ns()), **kwargs))

        def samples(count):
            for _ in range(count):
                result = http('/api/v1/tracking/telemetry')
                print(json.dumps({'time':time.time(),'angular':result.get('fields',{}).get('angular')}), flush=True)
                time.sleep(.2)

        record('start', axis=axis, direction=direction, aircraft_commands=False)
        status = http('/api/v1/gimbal/control')
        if not (status['available'] and status['connected'] and
                status['following_active'] is False and status['tracking_state']=='disabled'):
            raise RuntimeError('Requires connected camera, tracking disabled and following off')
        samples(5)
        try:
            result = action(axis, direction=direction)
            if result.get('status') != 'success':
                raise RuntimeError(str(result))
            samples(8)
        finally:
            action('stop')
            record('end')
    print(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('axis', choices=['pan','tilt','roll'])
    parser.add_argument('direction', type=int, choices=[-1,1])
    args = parser.parse_args()
    run(args.axis, args.direction)
