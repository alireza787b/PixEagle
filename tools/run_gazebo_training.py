#!/usr/bin/env python3
"""Run one isolated Gazebo camera/full-PixEagle/QGC training session.

The ordinary application owns tracking and following. This launcher starts
disarmed and command-blocked; closing it stops only its own simulation stack.
"""
from __future__ import annotations

import argparse
import configparser
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from tools import sih_isolated_host as host  # noqa: E402
from tools.gazebo_scenario import verified_scenario  # noqa: E402
from tools.prepare_simulation_profile import prepare  # noqa: E402
from tools.run_native_vector_sih import inspect_simulator_process, verify_gazebo_runtime  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def qgc_settings(directory: Path, endpoint: str) -> Path:
    """Private QSettings: a single simulation UDP link, no physical auto-connect."""
    destination = directory / 'PixEagle/PixEagle-QGroundControl.ini'
    destination.parent.mkdir(parents=True)
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config['General'] = {'SettingsVersion': '9'}
    config['AutoConnect'] = {name: 'false' for name in (
        'autoConnectUDP', 'autoConnectPixhawk', 'autoConnectSiKRadio', 'autoConnectLibrePilot', 'autoConnectZeroConf')}
    config['LinkConfigurations'] = {'count': '1', 'Link0\\name': 'PixEagle simulated aircraft',
        'Link0\\type': '1', 'Link0\\auto': 'true', 'Link0\\high_latency': 'false',
        'Link0\\port': '14560', 'Link0\\hostCount': '0'}
    config['PixEagle'] = {'integrationEnabled': 'true', 'videoEnabled': 'true',
        'CompanionEndpoint': endpoint}
    with destination.open('x', encoding='utf-8') as output:
        config.write(output, space_around_delimiters=False)
    destination.chmod(0o600)
    return destination


def display_mounts() -> list[str]:
    display = os.environ.get('DISPLAY', '')
    authority = Path(os.environ.get('XAUTHORITY', ''))
    if not display.startswith(':') or not authority.is_file():
        raise ValueError('Use this launcher from the signed-in Ubuntu X11 desktop session')
    number = display[1:].split('.')[0]
    if not number.isdigit() or not Path(f'/tmp/.X11-unix/X{number}').is_socket():
        raise ValueError('The current desktop display socket is unavailable')
    return ['--mount', f'type=bind,src=/tmp/.X11-unix/X{number},dst=/tmp/.X11-unix/X{number},readonly',
        '--mount', f'type=bind,src={authority},dst=/run/training-xauthority,readonly',
        '-e', f'DISPLAY={display}', '-e', 'XAUTHORITY=/run/training-xauthority',
        '-e', 'LIBGL_ALWAYS_SOFTWARE=1', '-e', 'QT_X11_NO_MITSHM=1']


def container_args(name, token, primary, mounts, environment, image, *, display=False, workdir=None):
    args = ['docker', 'run', '-d', '--name', name, '--label', f'{host.LABEL}={token}',
        '--network', 'container:' + primary, '--user', f'{os.getuid()}:{os.getgid()}',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--read-only',
        '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m']
    if workdir:
        args += ['--workdir', str(workdir)]
    for source, destination, readonly in mounts:
        if not Path(source).exists():
            raise ValueError(f'Training dependency is missing: {source}')
        args += ['--mount', f'type=bind,src={source},dst={destination}' + (',readonly' if readonly else '')]
    for key, value in environment.items():
        args += ['-e', f'{key}={value}']
    if display:
        args += display_mounts()
    return [*args, image]


def wait_backend(runtime, *, timeout=75):
    import requests

    manifest = json.loads((runtime / 'profile-manifest.json').read_text())
    credentials = json.loads((runtime / 'credentials.json').read_text())
    endpoint = credentials.pop('endpoint')
    deadline = time.monotonic() + timeout
    last = 'Waiting for the normal supervised backend'
    with requests.Session() as client:
        client.headers['Origin'] = endpoint
        authenticated = False
        while time.monotonic() < deadline:
            try:
                if not authenticated:
                    client.post(endpoint + '/api/v1/auth/login', json=credentials, timeout=3).raise_for_status()
                    authenticated = True
                context = client.get(endpoint + '/api/v1/integration/context', timeout=3).json()
                safety = client.get(endpoint + '/api/v1/integration/safety', timeout=3).json()
                status = client.get(endpoint + '/status', timeout=3).json()
                if context.get('instance_id') != manifest['instance_id']:
                    raise RuntimeError('Unexpected backend instance')
                if safety.get('active') is not True or status.get('following_active') is not False:
                    raise RuntimeError('Training startup must remain command-blocked and not following')
                video = context.get('video', {})
                if video.get('width') and video.get('height'):
                    write(runtime / 'logs/backend-ready.json', dict(instance_id=manifest['instance_id'],
                        commands_blocked=True, following_active=False, video=video,
                        telemetry=context.get('telemetry', {})))
                    return context
                last = 'Backend started; waiting for camera frames'
            except (requests.RequestException, ValueError) as error:
                last = type(error).__name__
            time.sleep(.5)
    raise TimeoutError(last)


def stop_relay(relay):
    """Reap the owned relay even if it exits during signal escalation."""
    try:
        os.killpg(relay.pid, signal.SIGTERM)
        relay.wait(timeout=5)
    except ProcessLookupError:
        relay.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(relay.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        relay.wait(timeout=5)


def run(args):
    runtime = args.runtime.absolute()
    if runtime.exists():
        raise ValueError('Choose a fresh runtime directory; existing evidence is never overwritten')
    display_mounts()
    for dependency in (args.python, args.router, args.qgc, args.bin_dir / 'mavlink2rest',
                       args.bin_dir / 'mavsdk_server_bin', args.qgc.parent / 'qt.conf', args.tcp_relay):
        if not dependency.is_file():
            raise ValueError(f'Training dependency is unavailable: {dependency}')
    for port in (args.port,):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    simulator, baseline, manifest = host.verified_simulation_build(args.build_manifest, repository=ROOT)
    scenario = verified_scenario(args.scenario, baseline, manifest)
    if simulator != 'gazebo' or scenario['expected_parameters'].get('MAV_TYPE') != 2:
        raise ValueError('The first training checkpoint requires a declared pure multicopter')
    runtime.mkdir(parents=True, mode=0o700)
    profile = runtime / 'backend'
    prepare(profile, udp_url=f'udp://127.0.0.1:{scenario["descriptor"]["camera"]["udp_port"]}',
        follower_mode='mc_velocity_chase', tracking_engine='local', backend_port=args.port,
        enable_altitude_control=True, username='admin', password='admin')
    qgc_settings(runtime / 'qgc/config', f'http://127.0.0.1:{args.port}')
    for part in ('home', 'cache', 'data', 'runtime'):
        (runtime / 'qgc' / part).mkdir(parents=True, mode=0o700)
    token = uuid.uuid4().hex
    network_id = None
    relay = None
    containers = []
    receipt = dict(kind='isolated-gazebo-training-v1', source_commit=host.command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
        scenario=scenario, firmware_build=baseline, commands_blocked_at_start=True,
        token=token, containers=containers, started_at=time.time())
    write(runtime / 'run.json', receipt)
    try:
        network_id = host.create_owned_internal_network('pixeagle-training-' + token[:12], token)
        receipt['network_id'] = network_id
        launch = host.simulation_launch_args(simulator, baseline, manifest, runtime=runtime, token=token,
            name='pixeagle-training-px4-' + token[:12], gazebo_scenario=args.scenario,
            desktop_network_id=network_id)
        image_index = launch.index(baseline['image_id'])
        launch[image_index:image_index] = display_mounts()
        primary = host.command(*launch)
        containers.append(primary)
        write(runtime / 'run.json', receipt)
        deadline = time.monotonic() + 90
        last = None
        while time.monotonic() < deadline:
            try:
                info = host.owned_container_info(primary, token)
                if (info['Image'] != baseline['image_id'] or not info['State']['Running']
                        or info['HostConfig']['Privileged'] or info['HostConfig']['Devices']
                        or set(info['NetworkSettings']['Networks']) != {host.owned_internal_network_info(network_id, token)['Name']}):
                    raise RuntimeError('Training simulator identity or isolation changed')
                process = inspect_simulator_process(primary, 0, os.getuid(), simulator=simulator,
                    baseline=baseline, manifest=manifest, scenario=scenario)
                checked = verify_gazebo_runtime(primary, 0, os.getuid(), process, manifest,
                    packaged=args.build_manifest.parent / 'packaged', scenario=scenario)
                write(runtime / 'simulator-ready.json', dict(process=process, gazebo=checked, container=info))
                break
            except (subprocess.SubprocessError, ValueError) as error:
                last = str(error)
                time.sleep(1)
        else:
            raise TimeoutError('Gazebo startup: ' + str(last))
        shared = [(args.python.parent.parent, args.python.parent.parent, True),
            (args.bin_dir, args.bin_dir, True), (args.router, args.router, True),
            ('/usr/lib/x86_64-linux-gnu', '/mnt/hostlibs', True)]
        worker = host.command(*container_args('pixeagle-training-backend-' + token[:12], token, primary,
            [*shared, (profile, profile, False), (ROOT / 'tools/simulation_stack_entry.sh', '/entry.sh', True)],
            dict(PIXEAGLE_SIM_RUNTIME=profile, PIXEAGLE_SIM_PYTHON=args.python,
                PIXEAGLE_SIM_BIN_DIR=args.bin_dir, PIXEAGLE_SIM_ROUTER=args.router,
                LD_LIBRARY_PATH='/mnt/hostlibs', PYTHONDONTWRITEBYTECODE='1',
                HOME=profile, GST_PLUGIN_SYSTEM_PATH_1_0='/mnt/hostlibs/gstreamer-1.0',
                GST_PLUGIN_SCANNER='/mnt/hostlibs/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner'),
            host.WORKER_IMAGE, workdir=profile), 'bash', '/entry.sh')
        containers.append(worker)
        write(runtime / 'run.json', receipt)
        network = host.owned_internal_network_info(network_id, token)
        info = host.owned_container_info(primary, token)
        address = ipaddress.ip_address(info['NetworkSettings']['Networks'][network['Name']]['IPAddress'])
        if not address.is_private or address.is_loopback or address.version != 4:
            raise RuntimeError('Owned internal IPv4 address is unavailable')
        relay_log = (runtime / 'api-relay.log').open('xb')
        try:
            relay = subprocess.Popen([str(args.tcp_relay),
                f'TCP4-LISTEN:{args.port},bind=127.0.0.1,reuseaddr,fork',
                f'TCP4:{address}:{args.port}'], stdout=relay_log, stderr=subprocess.STDOUT,
                start_new_session=True)
        finally:
            relay_log.close()
        receipt['api_relay'] = dict(pid=relay.pid, address=str(address), port=args.port,
                                   executable=str(args.tcp_relay))
        write(runtime / 'run.json', receipt)
        wait_backend(profile)
        qt = args.qt.absolute()
        gst = args.gstreamer_lib.absolute()
        qgc_environment = dict(HOME=runtime / 'qgc/home', XDG_CONFIG_HOME=runtime / 'qgc/config',
            XDG_CACHE_HOME=runtime / 'qgc/cache', XDG_DATA_HOME=runtime / 'qgc/data',
            XDG_RUNTIME_DIR=runtime / 'qgc/runtime', QT_QPA_PLATFORM='xcb',
            LD_LIBRARY_PATH=f'{qt}/lib:{gst}:/mnt/hostlibs',
            GST_PLUGIN_PATH=f'{gst}/gstreamer-1.0:/mnt/hostlibs/gstreamer-1.0',
            GST_PLUGIN_SCANNER='/mnt/hostlibs/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner')
        qgc = host.command(*container_args('pixeagle-training-qgc-' + token[:12], token, primary,
            [(runtime / 'qgc', runtime / 'qgc', False), (args.qgc.parent, args.qgc.parent, True),
             (args.qgc.parent.parent / 'qml', args.qgc.parent.parent / 'qml', True),
             (qt, qt, True), (gst, gst, True),
             ('/usr/lib/x86_64-linux-gnu', '/mnt/hostlibs', True)],
            qgc_environment, host.WORKER_IMAGE, display=True), str(args.qgc), '--logging', 'PixEagleLog.debug=true')
        containers.append(qgc)
        write(runtime / 'run.json', receipt)
        host.command('docker', 'exec', '--detach', '--user', str(os.getuid()), primary,
                     'gz', 'sim', '-g')
        print(f'QGC opened. Backend: http://127.0.0.1:{args.port} · isolated simulation only', flush=True)
        print(f'Credentials and logs: {profile} · Ctrl-C closes this owned stack', flush=True)
        while relay.poll() is None and all(host.owned_container_info(cid, token)['State']['Running'] for cid in containers):
            time.sleep(1)
        raise RuntimeError('A training component stopped; inspect retained logs')
    finally:
        closed = []
        if relay is not None:
            stop_relay(relay)
        for cid in reversed(containers):
            try:
                info = host.stop_owned_container(cid, token)
                log = subprocess.run(['docker', 'logs', '--timestamps', cid], capture_output=True, text=True, check=False)
                (runtime / f'{cid[:12]}.log').write_text(log.stdout + log.stderr)
                closed.append(dict(id=cid, exit_code=info['State']['ExitCode']))
                host.command('docker', 'rm', cid)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                closed.append(dict(id=cid, cleanup_error=str(error)))
        receipt.update(closed=closed, ended_at=time.time())
        if network_id:
            try:
                host.remove_owned_internal_network(network_id, token)
                receipt['network_removed'] = True
            except (RuntimeError, subprocess.SubprocessError) as error:
                receipt['network_cleanup_error'] = str(error)
        write(runtime / 'run.json', receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--scenario', default='x500-mono-camera-aruco-v1')
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--router', type=Path, required=True)
    parser.add_argument('--qgc', type=Path, required=True)
    parser.add_argument('--qt', type=Path, required=True)
    parser.add_argument('--gstreamer-lib', type=Path, required=True)
    parser.add_argument('--tcp-relay', type=Path, required=True, help='Installed socat executable')
    parser.add_argument('--port', type=int, default=5077)
    args = parser.parse_args()
    if not args.execute:
        parser.error('Use --execute for this isolated simulation; it never connects physical devices')
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        run(args)
    except KeyboardInterrupt:
        return


if __name__ == '__main__':
    main()
