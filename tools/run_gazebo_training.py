#!/usr/bin/env python3
"""Run one isolated Gazebo camera/full-PixEagle/QGC training session.

The ordinary application owns tracking and following. This launcher starts
disarmed and command-blocked; closing it stops only its own simulation stack.
"""
from __future__ import annotations

import argparse
import asyncio
import configparser
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from tools import sih_isolated_host as host  # noqa: E402
from tools import run_native_transition_baseline as native_runtime  # noqa: E402
from tools.native_adapter_runtime import adapter_launch_args, OwnedContainerLaunch  # noqa: E402
from tools.gazebo_scenario import fixed_camera_optical_to_body, verified_scenario  # noqa: E402
from tools.prepare_simulation_profile import prepare  # noqa: E402
from tools.run_native_vector_sih import inspect_simulator_process, verify_gazebo_runtime  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def qgc_build_identity(binary: Path) -> dict:
    """Use this build's generated identity, including its separate Daily settings."""
    build = binary.parent.parent
    header = (build / 'qgc_version.h').read_text(encoding='utf-8')
    cache = (build / 'CMakeCache.txt').read_text(encoding='utf-8')
    values = {}
    for name in ('QGC_APP_NAME', 'QGC_ORG_NAME'):
        matches = re.findall(rf'^#define {name} "([^"/\\]+)"$', header, re.M)
        if len(matches) != 1:
            raise ValueError('QGC generated application identity is unavailable')
        values[name] = matches[0]
    version = re.findall(r'^#define QGC_SETTINGS_VERSION ([0-9]+)$', header, re.M)
    stable = re.findall(r'^QGC_STABLE_BUILD:BOOL=(ON|OFF)$', cache, re.M)
    if len(version) != 1 or len(stable) != 1:
        raise ValueError('QGC generated settings version/build channel is unavailable')
    return dict(application=values['QGC_APP_NAME'] + (' Daily' if stable[0] == 'OFF' else ''),
                organization=values['QGC_ORG_NAME'], version=version[0])


def qgc_settings(directory: Path, endpoint: str, *, identity: dict) -> Path:
    """Private QSettings: a single simulation UDP link, no physical auto-connect."""
    destination = directory / identity['organization'] / (identity['application'] + '.ini')
    destination.parent.mkdir(parents=True)
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config['General'] = {'SettingsVersion': identity['version']}
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
    # Mesa's X11 software renderer must attach to the desktop's shared-memory segments.
    return ['--ipc=host', '--mount', f'type=bind,src=/tmp/.X11-unix/X{number},dst=/tmp/.X11-unix/X{number},readonly',
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
                    client.post(endpoint + '/api/v1/auth/login',
                        json={key: credentials[key] for key in ('username', 'password')}, timeout=3).raise_for_status()
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


def stop_child_group(relay):
    """Reap an owned child group even if it exits during signal escalation."""
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


def record_container_log(container, destination):
    """Retain receiver diagnostics while running, including an interrupted run."""
    with destination.open('xb') as stream:
        return subprocess.Popen(['docker', 'logs', '--follow', '--timestamps', container],
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)


def native_training_assets(args, simulator, scenario, *, firmware_policy="experimental"):
    """Runtime availability never grants profile or phase admission."""
    from classes.aircraft_state import AircraftKind, aircraft_kind_from_mavlink

    kind = aircraft_kind_from_mavlink(scenario['expected_parameters'].get('MAV_TYPE'))
    if simulator != 'gazebo' or kind not in (AircraftKind.MULTICOPTER, AircraftKind.FIXED_WING, AircraftKind.VTOL):
        raise ValueError('Training requires a declared MC, FW or VTOL Gazebo scenario')
    if firmware_policy == 'stock':
        return None
    if firmware_policy != 'experimental':
        raise ValueError('Unknown training firmware policy')
    if kind is AircraftKind.MULTICOPTER:
        # Ordinary MC uses MAVSDK. Shared machine dependency paths must not
        # opt it into native FW/VTOL registration or bootstrap requirements.
        return None
    bundle, manifest = getattr(args, 'adapter_bundle', None), getattr(args, 'adapter_file_manifest', None)
    if bool(bundle) != bool(manifest):
        raise ValueError('Native adapter bundle and file manifest must be supplied together')
    if not bundle:
        raise ValueError('Declared FW/VTOL training requires the verified native adapter')
    assets = json.loads(native_runtime.ASSETS.read_text())
    native_runtime.verify_adapter(bundle.resolve(), manifest, assets)
    source = args.build_manifest.resolve().parent / 'context/source'
    dds_source = native_runtime.DDS_STATUS_SOURCE
    if native_runtime.digest(source / dds_source) != assets['bootstrap_files'][dds_source]:
        raise ValueError('Native DDS bootstrap source differs from the reviewed status contract')
    native_runtime.verify_adapter_image(assets)
    return assets


def camera_training_source(args, scenario, token):
    """Bind original image time to the verified simulator, never to an RTP receipt."""
    from classes.aircraft_state import AircraftKind, aircraft_kind_from_mavlink

    if aircraft_kind_from_mavlink(scenario['expected_parameters']['MAV_TYPE']) not in (AircraftKind.FIXED_WING, AircraftKind.VTOL):
        return None
    max_skew = getattr(args, 'max_attitude_skew_s', .1)
    if type(max_skew) not in (int, float) or not math.isfinite(max_skew) or max_skew <= 0:
        raise ValueError('Training attitude skew must be a finite positive duration')
    descriptor = scenario['descriptor']
    if 'server_config' not in descriptor or 'server.config' not in scenario.get('added_resources', {}):
        raise ValueError('Raw camera training requires its explicit encoder-free server configuration')
    contract_path = ROOT / 'native/gazebo-camera-runtime.json'
    contract = json.loads(contract_path.read_text())
    source = args.build_manifest.resolve().parent / 'context/source' / contract['clock_source']
    if contract['schema_version'] != 1 or native_runtime.digest(source) != contract['clock_source_sha256']:
        raise ValueError('Gazebo image clock source contract differs from the verified firmware')
    camera = descriptor['camera']
    relative = f'gazebo/models/{camera["model"]}/model.sdf'
    added_camera = relative.removeprefix('gazebo/') in scenario.get('added_resources', {})
    sdf = (ROOT / 'native' / relative if added_camera else args.build_manifest.resolve().parent / 'packaged' / relative)
    camera_pin = (scenario['added_resources'][relative.removeprefix('gazebo/')] if added_camera
                  else descriptor['resources'][relative])
    if native_runtime.digest(sdf) != camera_pin['sha256']:
        raise ValueError('Gazebo calibration camera resource changed')
    camera_tree = ET.fromstring(sdf.read_bytes())
    sensor = camera_tree.find(
        f'./model/link[@name="{camera["link"]}"]/sensor[@name="{camera["sensor"]}"]')
    optics = sensor.find('camera')
    instrumentation = descriptor.get('articulated_camera')
    rotation = None if instrumentation is not None else fixed_camera_optical_to_body(descriptor.get('camera_mount'))
    if ((instrumentation is None and sensor.findtext('pose') != '0 0 0 0 0 0')
            or camera_tree.findtext('./model/pose', '0 0 0 0 0 0') != '0 0 0 0 0 0'
            or camera_tree.findtext('./model/link/pose', '0 0 0 0 0 0') != '0 0 0 0 0 0'
            or optics.find('distortion') is not None
            or optics.find('lens') is not None):
        raise ValueError('Training calibration requires the declared fixed pinhole sensor frames')
    width, height = int(optics.findtext('image/width')), int(optics.findtext('image/height'))
    hfov = float(optics.findtext('horizontal_fov'))
    if min(width, height) <= 0 or not math.isfinite(hfov) or not 0 < hfov < math.pi:
        raise ValueError('Training camera geometry is invalid')
    camera_model = descriptor['model'] + '_0'
    topic = f'/world/{descriptor["world"]}/model/{camera_model}/link/{camera["link"]}/sensor/{camera["sensor"]}/image'
    source_config = dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id=token + ':' + descriptor['world'],
        world=descriptor['world'], image_topic=topic,
        max_attitude_skew_s=max_skew)
    from classes.fixed_camera_calibration import selected_source_signature
    signature = selected_source_signature(source_type='GAZEBO_CAMERA', backend='gazebo_transport', locator=topic,
        options={'world': descriptor['world'], 'pixel_format': 'RGB_INT8'})
    focal = width / (2 * math.tan(hfov / 2))
    intrinsics = dict(image_size_px=[width, height], focal_length_px=[focal, focal],
                      principal_point_px=[width / 2, height / 2])
    calibration = None if rotation is None else dict(source_signature=signature, revision='gazebo-pinhole-' + camera_pin['sha256'][:16],
        pixel_grid='decoder_pre_orientation', image_size_px=[width, height], focal_length_px=[focal, focal],
        principal_point_px=[width / 2, height / 2],
        optical_to_body_frd_wxyz=[rotation.w, rotation.x, rotation.y, rotation.z],
        distortion_model='none', mount_kind='fixed')
    return dict(config=source_config, calibration=calibration, intrinsics=intrinsics, clock_contract=contract,
        clock_contract_sha256=native_runtime.digest(contract_path), camera_resource_sha256=native_runtime.digest(sdf),
        scenario_sha256=scenario['descriptor_sha256'], actual_camera_info_confirmation=False,
        declared_stock_rtp_encoder_disabled=True, server_config_sha256=descriptor['server_config']['sha256'])


def start_camera_provider(args, runtime, token, primary, baseline, source, containers):
    """One source process; original CID cleanup is shared with the full stack."""
    private = runtime / 'camera'
    private.mkdir(mode=0o700)
    config = source['config']
    source_path = runtime / 'camera-source-input.json'
    write(source_path, source)
    provider = ROOT / 'tools/gazebo_camera_provider.py'
    protocol = ROOT / 'src/classes/gazebo_camera_protocol.py'
    argv = container_args('pixeagle-training-camera-' + token[:12], token, primary,
        [(private, '/run/pixeagle-camera', False), (source_path, '/app/camera-source.json', True), (provider, '/app/tools/gazebo_camera_provider.py', True),
         (protocol, '/app/src/classes/gazebo_camera_protocol.py', True)],
        dict(GZ_IP='127.0.0.1', GZ_PARTITION=token, HOME='/tmp', PYTHONDONTWRITEBYTECODE='1'), baseline['image_id'])
    argv[-1:-1] = ['--entrypoint', '/usr/bin/python3']
    argv += ['/app/tools/gazebo_camera_provider.py', '--socket', config['socket_path'],
        '--world', config['world'], '--image-topic', config['image_topic'], '--source-clock-id', config['source_clock_id'],
        '--intrinsics-file', '/app/camera-source.json']
    # Reuse original-CID recovery for a lost Docker launch reply, without another lifecycle owner.
    owner = OwnedContainerLaunch(runtime, token, containers, host.owned_container_info)
    cid = owner.launch(argv, 'pixeagle-training-camera-' + token[:12])
    write(runtime / 'camera-source.json', source | dict(container_id=cid, image_id=baseline['image_id'],
        provider_sha256=native_runtime.digest(provider), protocol_sha256=native_runtime.digest(protocol),
        renderer_or_following_qualified=False))
    deadline = time.monotonic() + 10.
    while time.monotonic() < deadline:
        info = host.owned_container_info(cid, token)
        if (not info['State']['Running'] or info['Image'] != baseline['image_id']
                or info['HostConfig']['NetworkMode'] != 'container:' + primary
                or info['Config']['User'] != f'{os.getuid()}:{os.getgid()}'
                or info['HostConfig']['Privileged'] or info['HostConfig'].get('Devices')
                or info['NetworkSettings']['Ports']):
            raise ValueError('Original camera provider identity or isolation changed')
        if (private / 'camera.sock').is_socket() and (private / 'camera-info.json').is_file():
            confirmation = json.loads((private / 'camera-info.json').read_text())
            if (confirmation.get('actual_camera_info_confirmation') is not True
                    or confirmation.get('source_clock_id') != config['source_clock_id']
                    or confirmation.get('image_topic') != config['image_topic']):
                raise ValueError('Camera info receipt source binding changed')
            return [(private, Path('/run/pixeagle-camera'), False)]
        time.sleep(.05)
    raise TimeoutError('Camera provider did not create its private endpoint')


def start_gimbal_provider(runtime, profile, token, primary, baseline, scenario, camera_source, containers):
    """One ideal instrumentation owner; no aircraft publisher is added."""
    import yaml

    config = yaml.safe_load((profile / 'configs/config.yaml').read_text())['GimbalTracker']
    private = runtime / 'gimbal-source'
    private.mkdir(mode=0o700)
    camera_private = runtime / 'camera'
    camera_private.mkdir(mode=0o700)
    from classes.frame_publisher import FramePublisher
    source = dict(world=camera_source['config']['world'], source_clock_id=camera_source['config']['source_clock_id'],
        aircraft_model=scenario['descriptor']['model'] + '_0',
        articulated_geometry=scenario['articulated_geometry'],
        camera_mount=scenario['descriptor']['camera_mount'], gimbal_config=config,
        camera=camera_source, selection_max_age_s=FramePublisher.SELECTION_MAX_AGE_MS / 1000)
    source_path = runtime / 'gimbal-source.json'
    write(source_path, source)
    argv = container_args('pixeagle-training-gimbal-' + token[:12], token, primary,
        [(ROOT, '/app', True), (private, '/run/pixeagle-gimbal', False),
         (camera_private, '/run/pixeagle-camera', False),
         (source_path, '/run/gimbal-source.json', True)],
        dict(GZ_IP='127.0.0.1', GZ_PARTITION=token, HOME='/tmp', PYTHONDONTWRITEBYTECODE='1'), baseline['image_id'])
    argv[-1:-1] = ['--entrypoint', '/usr/bin/python3']
    argv += ['/app/tools/gazebo_gimbal_provider.py', '--source', '/run/gimbal-source.json', '--private', '/run/pixeagle-gimbal']
    owner = OwnedContainerLaunch(runtime, token, containers, host.owned_container_info)
    cid = owner.launch(argv, 'pixeagle-training-gimbal-' + token[:12])
    deadline = time.monotonic() + 10.
    while time.monotonic() < deadline:
        info = host.owned_container_info(cid, token)
        if (not info['State']['Running'] or info['Image'] != baseline['image_id']
                or info['HostConfig']['NetworkMode'] != 'container:' + primary
                or info['Config']['User'] != f'{os.getuid()}:{os.getgid()}'
                or info['HostConfig']['Privileged'] or info['HostConfig'].get('Devices')
                or info['NetworkSettings']['Ports']):
            raise ValueError('Gimbal instrumentation identity or isolation changed')
        if ((private / 'gimbal.sock').is_socket() and (private / 'operator-state.json').is_file()
                and (private / 'control.sock').is_socket() and (camera_private / 'camera.sock').is_socket()
                and (camera_private / 'camera-info.json').is_file()):
            confirmation = json.loads((camera_private / 'camera-info.json').read_text())
            if (confirmation.get('actual_camera_info_confirmation') is not True
                    or confirmation.get('source_clock_id') != camera_source['config']['source_clock_id']
                    or confirmation.get('image_topic') != camera_source['config']['image_topic']):
                raise ValueError('Rendered camera intrinsics/source confirmation changed')
            write(runtime / 'gimbal-source-receipt.json', dict(container_id=cid, source=source,
                mechanics_qualified=False, aircraft_commands_sent=False,
                source_files={name: native_runtime.digest(ROOT / name) for name in (
                    'tools/gazebo_gimbal_provider.py', 'tools/gazebo_gimbal_model.py',
                    'tools/gazebo_gimbal_gui.py', 'tools/gazebo_camera_provider.py', 'tools/gazebo_rendered_control.py',
                    'tools/gazebo_scene_selection.py', 'src/classes/gazebo_camera_control.py',
                    'tools/gazebo_joint_gimbal.py', 'tools/gazebo_geometry.py',
                    'src/classes/gazebo_gimbal_source.py', 'src/classes/gimbal_geometry.py')}))
            write(runtime / 'camera-source.json', camera_source | dict(container_id=cid,
                image_id=baseline['image_id'], renderer_or_following_qualified=False))
            return [(private, Path('/run/pixeagle-gimbal'), False), (camera_private, Path('/run/pixeagle-camera'), False)]
        time.sleep(.05)
    raise TimeoutError('Gimbal instrumentation did not supply observed camera feedback')


def start_native_wire_recorder(args, runtime, profile, token, primary, containers):
    """Retain ordinary App traffic without changing the adapter or admission policy."""
    private = runtime / 'native-wire'
    private.mkdir(mode=0o700)
    front, logs = private / 'front', private / 'logs'
    front.mkdir(mode=0o700)
    logs.mkdir(mode=0o700)
    helpers = {}
    for name in ('native_sih_wire.py', 'run_native_guidance_wire.py'):
        source = ROOT / 'tools' / name
        data = source.read_bytes()
        (private / name).write_bytes(data)
        helpers[name] = native_runtime.digest(source)
    mounts = [(args.python.parent.parent, args.python.parent.parent, True),
        (profile / 'src', Path('/app/src'), True),
        ('/usr/lib/x86_64-linux-gnu', '/mnt/hostlibs', True),
        (front, Path('/run/pixeagle'), False),
        (runtime / 'simulator/private', Path('/run/native-backend'), True),
        (logs, Path('/wire'), False),
        *[(private / name, Path('/app/tools') / name, True) for name in helpers]]
    name = 'pixeagle-training-wire-' + token[:12]
    argv = container_args(name, token, primary, mounts,
        dict(LD_LIBRARY_PATH='/mnt/hostlibs', HOME='/tmp', PYTHONDONTWRITEBYTECODE='1'), host.WORKER_IMAGE)
    argv[-1:-1] = ['--entrypoint', str(args.python)]
    argv += ['/app/tools/run_native_guidance_wire.py', '--frontend', '/run/pixeagle/guidance.sock',
        '--backend', '/run/native-backend/guidance.sock', '--output', '/wire']
    owner = OwnedContainerLaunch(runtime, token, containers, host.owned_container_info)
    cid = owner.launch(argv, name)
    expected_mounts = {str(destination): (str(Path(source).resolve()), not readonly)
                       for source, destination, readonly in mounts}
    deadline = time.monotonic() + 10.
    while time.monotonic() < deadline:
        info = host.owned_container_info(cid, token)
        actual_mounts = {item['Destination']: (str(Path(item['Source']).resolve()), item['RW'])
                         for item in info['Mounts'] if item['Type'] == 'bind'}
        if (not info['State']['Running'] or info['Image'] != host.WORKER_IMAGE
                or info['HostConfig']['NetworkMode'] != 'container:' + primary
                or info['Config']['User'] != f'{os.getuid()}:{os.getgid()}'
                or info['HostConfig']['Privileged'] or info['HostConfig'].get('Devices')
                or not info['HostConfig']['ReadonlyRootfs'] or info['NetworkSettings']['Ports']
                or actual_mounts != expected_mounts
                or any(item['Type'] != 'bind' and not (item['Type'] == 'tmpfs' and item['Destination'] == '/tmp')
                       for item in info['Mounts'])):
            raise ValueError('Original native recorder identity or isolation changed')
        if (front / 'guidance.sock').is_socket():
            write(private / 'manifest.json', dict(kind='training_native_wire', container_id=cid,
                primary=primary, owner_token=token, image_id=host.WORKER_IMAGE, helpers=helpers,
                frontend='/run/pixeagle/guidance.sock', backend='/run/native-backend/guidance.sock',
                wire_path='logs/wire.jsonl', canonical_runtime_qualified=False, following_qualified=False))
            return [(front, Path('/run/pixeagle'), False)]
        time.sleep(.05)
    raise TimeoutError('Native wire recorder did not create its private endpoint')


class TrainingAdapter:
    """Desktop caller of the canonical adapter bootstrap, with its own network authority."""
    @staticmethod
    def owned_container_info(cid, token):
        return host.owned_container_info(cid, token)

    command = native_runtime.Runtime.command
    launch = native_runtime.Runtime.launch
    sidecar_info = native_runtime.Runtime.sidecar_info
    bootstrap = native_runtime.Runtime.bootstrap

    def __init__(self, args, output, token, primary, network_id, baseline, assets, containers, *, source_clock_id=None):
        self.args, self.output, self.token = args, output, token
        self.source_clock_id = source_clock_id
        self.primary, self.network_id, self.baseline, self.assets = primary, network_id, baseline, assets
        self.created, self.sidecar, self.adapter_requested = containers, None, False
        self.socket = output / 'simulator/private/guidance.sock'
        self.original_mounts = sorted(host.owned_container_info(primary, token)['Mounts'],
                                      key=lambda mount: mount['Destination'])

    def primary_info(self):
        info = host.owned_container_info(self.primary, self.token)
        network = host.owned_internal_network_info(self.network_id, self.token)
        config, host_config = info['Config'], info['HostConfig']
        if (info['Image'] != self.baseline['image_id'] or info['State']['Running'] is not True
                or config['User'] != f'{os.getuid()}:{os.getgid()}' or config['WorkingDir'] != '/work/rootfs'
                or host_config['Privileged'] or host_config.get('Devices') or info['NetworkSettings']['Ports']
                or set(info['NetworkSettings']['Networks']) != {network['Name']}
                or sorted(info['Mounts'], key=lambda mount: mount['Destination']) != self.original_mounts):
            raise ValueError('Original desktop simulator identity or isolation changed')
        mounts = {item['Destination']: (Path(item['Source']).resolve(), item['RW']) for item in info['Mounts']}
        if mounts.get('/work') != (self.output / 'simulator', True):
            raise ValueError('DDS bootstrap requires the original private primary workdir')
        return info

    def bootstrap_status(self, *, timeout):
        self.primary_info()
        self.sidecar_info()
        return self.command(['docker', 'exec', '--user', f'{os.getuid()}:{os.getgid()}', self.primary,
            '/opt/px4/bin/px4-uxrce_dds_client', '--instance', '0', 'status'], check=False, timeout=timeout)

    def start(self):
        self.primary_info()
        work = self.output / 'simulator'
        (work / 'private').mkdir(mode=0o700)
        name = 'pixeagle-training-adapter-' + self.token[:12]
        argv = adapter_launch_args(work, self.args.adapter_bundle, self.assets,
            token=self.token, primary=self.primary, label=host.LABEL, name=name, simulator_clock_id=self.source_clock_id)
        self.sidecar = self.launch(argv, name)
        asyncio.run(self.bootstrap(time.monotonic() + 45.))
        self.sidecar_info()
        write(self.output / 'native-adapter-ready.json', dict(primary=self.primary, sidecar=self.sidecar,
            adapter_image=self.assets['adapter_image'], adapter_sha256=self.assets['adapter_sha256'],
            file_manifest_sha256=self.assets['file_manifest_sha256'], socket='/run/pixeagle/guidance.sock',
            assets_sha256=native_runtime.digest(native_runtime.ASSETS),
            source_clock_id=self.source_clock_id, following_qualification=False, scope='DDS and private socket startup only'))


def require_free_loopback_port(port):
    with socket.socket() as probe:
        # Match the listener's reuse policy after closing an owned prior run.
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', port))


def run(args):
    runtime = args.runtime.absolute()
    operator_ui = not getattr(args, 'no_operator_ui', False)
    qgc_log = None
    qgc = None
    if runtime.exists():
        raise ValueError('Choose a fresh runtime directory; existing evidence is never overwritten')
    if bool(args.dashboard_build) != bool(args.dashboard_server):
        raise ValueError('Dashboard build and installed serve executable must be supplied together')
    display_mounts()
    for dependency in (args.python, args.router, args.qgc, args.bin_dir / 'mavlink2rest',
                       args.bin_dir / 'mavsdk_server_bin', args.qgc.parent / 'qt.conf', args.tcp_relay):
        if not dependency.is_file():
            raise ValueError(f'Training dependency is unavailable: {dependency}')
    for port in ((args.port, args.dashboard_port) if args.dashboard_build else (args.port,)):
        require_free_loopback_port(port)
    simulator, baseline, manifest = host.verified_simulation_build(args.build_manifest, repository=ROOT)
    scenario = verified_scenario(args.scenario, baseline, manifest, bind_to_build=True)
    assets = native_training_assets(args, simulator, scenario,
        firmware_policy=baseline['firmware'].get('policy', 'experimental'))
    token = uuid.uuid4().hex
    camera_source = camera_training_source(args, scenario, token)
    rendered_gimbal = scenario['descriptor'].get('articulated_camera')
    if rendered_gimbal is not None and operator_ui:
        subprocess.run([str(args.python), '-c', 'import tkinter'], check=True, capture_output=True)
    runtime.mkdir(parents=True, mode=0o700)
    profile = runtime / 'backend'
    video = dict(gazebo_camera=camera_source['config'], fixed_camera_calibration=camera_source['calibration']) if camera_source else dict(
        udp_url=f'udp://127.0.0.1:{scenario["descriptor"]["camera"]["udp_port"]}')
    gimbal = None if rendered_gimbal is None else dict(socket_path='/run/pixeagle-gimbal/gimbal.sock',
        source_clock_id=camera_source['config']['source_clock_id'], world=camera_source['config']['world'],
        max_attitude_skew_s=camera_source['config']['max_attitude_skew_s'], control_contract='rendered_scene_v1')
    prepare(profile, **video, gazebo_gimbal=gimbal, mount_type=getattr(args, 'mount_type', 'HORIZONTAL'),
        follower_mode=args.follower_mode, tracking_engine='camera' if rendered_gimbal is not None else 'local', backend_port=args.port,
        continuity_mode=getattr(args, 'continuity_mode', 'immediate_handoff'),
        dashboard_port=args.dashboard_port if args.dashboard_build else None,
        enable_altitude_control=getattr(args, 'altitude_control', 'on') == 'on',
        frame_rotation_deg=getattr(args, 'frame_rotation_deg', 0),
        username='admin', password='admin')
    qgc_identity = qgc_build_identity(args.qgc)
    qgc_settings(runtime / 'qgc/config', f'http://127.0.0.1:{args.port}', identity=qgc_identity)
    for part in ('home', 'cache', 'data', 'runtime'):
        (runtime / 'qgc' / part).mkdir(parents=True, mode=0o700)
    network_id = None
    relay = None
    frontend = None
    gimbal_gui = None
    containers = []
    receipt = dict(kind='isolated-gazebo-training-v1', source_commit=host.command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
        scenario=scenario, firmware_build=baseline, commands_blocked_at_start=True,
        firmware_policy=baseline['firmware'].get('policy', 'experimental'),
        native_adapter_prepared=assets is not None,
        token=token, containers=containers, qgc_identity=qgc_identity, operator_ui_enabled=operator_ui, started_at=time.time())
    write(runtime / 'run.json', receipt)
    try:
        network_id = host.create_owned_internal_network('pixeagle-training-' + token[:12], token)
        receipt['network_id'] = network_id
        launch = host.simulation_launch_args(simulator, baseline, manifest, runtime=runtime, token=token,
            name='pixeagle-training-px4-' + token[:12], gazebo_scenario=args.scenario,
            desktop_network_id=network_id, bind_gazebo_template=True)
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
        native_mounts = []
        if assets is not None:
            adapter = TrainingAdapter(args, runtime, token, primary, network_id, baseline, assets, containers,
                source_clock_id=camera_source['config']['source_clock_id'] if camera_source else None)
            adapter.start()
            native_mounts = start_native_wire_recorder(args, runtime, profile, token, primary, containers)
            write(runtime / 'run.json', receipt)
        if camera_source is not None and rendered_gimbal is None:
            native_mounts += start_camera_provider(args, runtime, token, primary, baseline, camera_source, containers)
            write(runtime / 'run.json', receipt)
        if rendered_gimbal is not None:
            native_mounts += start_gimbal_provider(runtime, profile, token, primary, baseline, scenario, camera_source, containers)
            write(runtime / 'run.json', receipt)
        shared = [(args.python.parent.parent, args.python.parent.parent, True),
            (args.bin_dir, args.bin_dir, True), (args.router, args.router, True),
            ('/usr/lib/x86_64-linux-gnu', '/mnt/hostlibs', True)]
        worker = host.command(*container_args('pixeagle-training-backend-' + token[:12], token, primary,
            [*shared, *native_mounts, (profile, profile, False), (ROOT / 'tools/simulation_stack_entry.sh', '/entry.sh', True)],
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
        if rendered_gimbal is not None and operator_ui:
            with (runtime / 'gimbal-gui.log').open('xb') as log:
                gimbal_gui = subprocess.Popen([str(args.python), str(ROOT / 'tools/gazebo_gimbal_gui.py'),
                    '--private', str(runtime / 'gimbal-source')], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            receipt['gimbal_gui'] = dict(pid=gimbal_gui.pid, private=str(runtime / 'gimbal-source'))
        if args.dashboard_build:
            if (not (args.dashboard_build / 'index.html').is_file() or not args.dashboard_server.is_file()):
                raise ValueError('Built Dashboard or installed production serve executable is missing')
            with (runtime / 'dashboard.log').open('xb') as log:
                frontend = subprocess.Popen([str(args.dashboard_server), '-s', str(args.dashboard_build),
                    '-l', f'tcp://127.0.0.1:{args.dashboard_port}', '--no-clipboard'],
                    env=os.environ | {'NO_UPDATE_NOTIFIER': '1'}, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True)
            receipt['dashboard'] = dict(pid=frontend.pid, build=str(args.dashboard_build), port=args.dashboard_port)
        if operator_ui:
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
                qgc_environment, host.WORKER_IMAGE, display=True), str(args.qgc), '--logging', 'Custom.PixEagle*.debug=true')
            containers.append(qgc)
            qgc_log = record_container_log(qgc, runtime / 'qgc-live.log')
            receipt['qgc_live_log'] = dict(pid=qgc_log.pid, path=str(runtime / 'qgc-live.log'))
            write(runtime / 'run.json', receipt)
            host.command('docker', 'exec', '--detach', '--user', str(os.getuid()), primary,
                         'gz', 'sim', '-g')
            print(f'QGC opened. Backend: http://127.0.0.1:{args.port} · isolated simulation only', flush=True)
        else:
            print(f'Validation backend ready: http://127.0.0.1:{args.port} · operator windows disabled', flush=True)
        print(f'Credentials and logs: {profile} · Ctrl-C closes this owned stack', flush=True)
        while (relay.poll() is None and (frontend is None or frontend.poll() is None)
                and (gimbal_gui is None or gimbal_gui.poll() is None)
                and all(host.owned_container_info(cid, token)['State']['Running'] for cid in containers)):
            time.sleep(1)
        if qgc is not None:
            state = host.owned_container_info(qgc, token)['State']
            if not state['Running'] and state['ExitCode'] == 0:
                receipt['closure_reason'] = 'qgc_closed'
                print('QGC closed. Closing this owned simulation.', flush=True)
                return
        raise RuntimeError('A training component stopped; inspect retained logs')
    finally:
        closed = []
        for child in (gimbal_gui, frontend, relay, qgc_log):
            if child is not None:
                try:
                    stop_child_group(child)
                except (OSError, subprocess.SubprocessError) as error:
                    receipt.setdefault('child_cleanup_errors', []).append(str(error))
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
    parser.add_argument('--no-operator-ui', action='store_true',
                        help='Software validation only: start no QGC, gimbal GUI or Gazebo GUI window')
    parser.add_argument('--max-attitude-skew-s', type=float, default=.1,
                        help='Maximum measured simulator camera/PX4 source-time mismatch (default: 0.1 s)')
    parser.add_argument('--frame-rotation-deg', type=int, choices=(0, 90, 180, 270), default=0,
                        help='Decoder image orientation only; never changes the physical mount or angle geometry')
    parser.add_argument('--altitude-control', choices=('on', 'off'), default='on',
                        help='Target-directed vertical guidance in this disposable qualification profile')
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--adapter-bundle', type=Path,
                        help='Reviewed native runtime bundle; only for an explicitly selected experimental firmware build')
    parser.add_argument('--adapter-file-manifest', type=Path)
    parser.add_argument('--scenario', default='x500-mono-camera-aruco-v1')
    parser.add_argument('--follower-mode', default='mc_velocity_chase',
                        help='Initial follower compatible with the selected input; actual aircraft phase still gates Start')
    parser.add_argument('--mount-type', choices=('HORIZONTAL', 'VERTICAL'), default='HORIZONTAL',
                        help='Canonical gimbal installation preset, independent of aircraft phase')
    parser.add_argument('--continuity-mode', choices=('immediate_handoff', 'bounded_decay'), default='immediate_handoff',
                        help='Explicit disposable-profile recovery policy; factory and saved configurations are unchanged')
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--bin-dir', type=Path, required=True)
    parser.add_argument('--router', type=Path, required=True)
    parser.add_argument('--qgc', type=Path, required=True)
    parser.add_argument('--qt', type=Path, required=True)
    parser.add_argument('--gstreamer-lib', type=Path, required=True)
    parser.add_argument('--tcp-relay', type=Path, required=True, help='Installed socat executable')
    parser.add_argument('--dashboard-build', type=Path)
    parser.add_argument('--dashboard-server', type=Path, help='Installed Dashboard serve executable')
    parser.add_argument('--dashboard-port', type=int, default=3040)
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
