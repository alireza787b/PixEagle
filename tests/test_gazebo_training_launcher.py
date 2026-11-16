"""Desktop preparation: no X11, Docker, flight or external network dependencies."""
import configparser
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
from unittest.mock import Mock

import pytest

from tools import run_gazebo_training as training


def test_live_receiver_log_retains_stdout_and_stderr_before_launcher_shutdown(tmp_path, monkeypatch):
    docker = tmp_path / 'docker'
    docker.write_text(f'#!{sys.executable}\nimport sys\n'
        'assert sys.argv[1:]==["logs","--follow","--timestamps","owned-qgc"]\n'
        'print("receiver generation 1: decode")\nprint("presentation delayed",file=sys.stderr)\n')
    docker.chmod(0o700)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    log = tmp_path / 'qgc-live.log'
    child = training.record_container_log('owned-qgc', log)
    try:
        assert child.wait(timeout=5) == 0
        assert 'receiver generation 1: decode' in log.read_text()
        assert 'presentation delayed' in log.read_text()
        with pytest.raises(FileExistsError):
            training.record_container_log('owned-qgc', log)
    finally:
        training.stop_child_group(child)


def test_closed_owned_listener_can_restart_but_active_listener_is_never_reused():
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
        server.listen(1)
        with pytest.raises(OSError):
            training.require_free_loopback_port(port)
        with socket.create_connection(('127.0.0.1', port), timeout=1) as client:
            connection, _ = server.accept()
            connection.close()
            assert client.recv(1) == b''
    training.require_free_loopback_port(port)


def test_private_qgc_profile_disables_unrelated_autoconnect(tmp_path):
    identity = dict(application='Test GCS Daily', organization='Test organization', version='13')
    destination = training.qgc_settings(tmp_path, 'http://127.0.0.1:5077', identity=identity)
    config = configparser.ConfigParser()
    config.read(destination)
    assert set(config['AutoConnect'].values()) == {'false'}
    links = config['LinkConfigurations']
    assert links['count'] == '1' and links['link0\\port'] == '14560'
    assert links['link0\\type'] == '1' and links['link0\\auto'] == 'true'
    assert config['PixEagle']['companionendpoint'] == 'http://127.0.0.1:5077'
    assert not destination.stat().st_mode & 0o077
    with pytest.raises(FileExistsError):
        training.qgc_settings(tmp_path, 'http://127.0.0.1:5078', identity=identity)
    assert destination == tmp_path / 'Test organization/Test GCS Daily.ini'
    assert config['General']['settingsversion'] == '13'


@pytest.mark.parametrize('stable', [True, False])
def test_settings_channel_comes_from_the_actual_generated_build(tmp_path, stable):
    (tmp_path / 'Debug').mkdir()
    (tmp_path / 'qgc_version.h').write_text('#define QGC_APP_NAME "Test GCS"\n'
        '#define QGC_ORG_NAME "Test organization"\n#define QGC_SETTINGS_VERSION 13\n')
    (tmp_path / 'CMakeCache.txt').write_text('QGC_STABLE_BUILD:BOOL=' + ('ON' if stable else 'OFF') + '\n')
    identity = training.qgc_build_identity(tmp_path / 'Debug/TestGCS')
    assert identity == dict(application='Test GCS' + ('' if stable else ' Daily'),
                            organization='Test organization', version='13')


def test_container_plan_is_unprivileged_and_namespace_scoped(tmp_path):
    args = training.container_args('training', 'owner', 'original-cid',
        [(tmp_path, '/runtime', False)], {'HOME': '/runtime'}, 'pinned-image')
    assert args[args.index('--network') + 1] == 'container:original-cid'
    assert '--read-only' in args and '--cap-drop' in args
    assert not {'--privileged', '--device', '--publish'} & set(args)
    assert f'type=bind,src={tmp_path},dst=/runtime' in args
    with pytest.raises(ValueError, match='missing'):
        training.container_args('training', 'owner', 'original-cid',
            [(Path('/missing/training/dependency'), '/runtime', False)], {}, 'pinned-image')


def test_desktop_ipc_supports_mesa_without_exposing_the_aircraft_network(tmp_path, monkeypatch):
    authority = tmp_path / 'xauthority'
    authority.touch()
    monkeypatch.setenv('DISPLAY', ':9')
    monkeypatch.setenv('XAUTHORITY', str(authority))
    monkeypatch.setattr(Path, 'is_socket', lambda path: path == Path('/tmp/.X11-unix/X9'))
    args = training.container_args('display', 'owner', 'simulator', [], {}, 'image', display=True)
    assert '--ipc=host' in args
    assert args[args.index('--network') + 1] == 'container:simulator'
    assert '--read-only' in args and '--cap-drop' in args
    assert not {'--privileged', '--device', '--publish', '--network=host'} & set(args)
    headless = training.container_args('backend', 'owner', 'simulator', [], {}, 'image')
    assert '--ipc=host' not in headless


def test_relay_exit_during_escalation_does_not_skip_remaining_cleanup(monkeypatch):
    relay = Mock(pid=123)
    relay.wait.side_effect = [subprocess.TimeoutExpired('socat', 5), 0]
    kill = Mock(side_effect=[None, ProcessLookupError()])
    monkeypatch.setattr(training.os, 'killpg', kill)
    training.stop_child_group(relay)
    assert relay.wait.call_count == 2


def test_startup_authentication_uses_only_the_typed_login_fields(tmp_path, monkeypatch):
    (tmp_path / 'logs').mkdir()
    (tmp_path / 'profile-manifest.json').write_text(json.dumps({'instance_id': 'training'}))
    (tmp_path / 'credentials.json').write_text(json.dumps(dict(username='test-account', password='test-secret',
        endpoint='http://127.0.0.1:5077', purpose='Private training only')))
    client = Mock(headers={})
    client.get.side_effect = [Mock(json=lambda: dict(instance_id='training', video=dict(width=640, height=480))),
                             Mock(json=lambda: dict(active=True)), Mock(json=lambda: dict(following_active=False))]
    import requests
    session = Mock()
    session.return_value.__enter__ = Mock(return_value=client)
    session.return_value.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(requests, 'Session', session)
    training.wait_backend(tmp_path)
    client.post.assert_called_once_with('http://127.0.0.1:5077/api/v1/auth/login',
        json=dict(username='test-account', password='test-secret'), timeout=3)


def test_vtol_adapter_is_required_before_staging_or_launch(tmp_path, monkeypatch):
    from types import SimpleNamespace
    commands = Mock(side_effect=AssertionError('must not launch'))
    monkeypatch.setattr(training.host, 'command', commands)
    args = SimpleNamespace(adapter_bundle=None, adapter_file_manifest=None)
    assert training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': 2}}) is None
    with pytest.raises(ValueError, match='requires the verified native adapter'):
        training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': 22}})
    assert list(tmp_path.iterdir()) == []
    commands.assert_not_called()


def test_shared_dependency_recipe_does_not_enable_native_adapter_for_pure_mc(tmp_path,monkeypatch):
    from types import SimpleNamespace
    verify=Mock(side_effect=AssertionError('Pure MC has no native owner'))
    monkeypatch.setattr(training.native_runtime,'verify_adapter',verify)
    args=SimpleNamespace(adapter_bundle=tmp_path/'unused',adapter_file_manifest=tmp_path/'unused.json')
    assert training.native_training_assets(args,'gazebo',{'expected_parameters':{'MAV_TYPE':2}}) is None
    verify.assert_not_called()


@pytest.mark.parametrize('kind', [0, 999, None])
def test_undeclared_aircraft_families_are_not_implicitly_training_ready(kind):
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='declared MC, FW or VTOL'):
        training.native_training_assets(SimpleNamespace(), 'gazebo', {'expected_parameters': {'MAV_TYPE': kind}})


@pytest.mark.parametrize('part', ['adapter_bundle', 'adapter_file_manifest'])
def test_incomplete_adapter_authority_refuses(part, tmp_path):
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='supplied together'):
        training.native_training_assets(SimpleNamespace(**{part: tmp_path}), 'gazebo',
                                        {'expected_parameters': {'MAV_TYPE': 22}})


@pytest.mark.parametrize('kind', [1, 22])
def test_adapter_preflight_checks_bundle_and_source_before_image(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    args = SimpleNamespace(adapter_bundle=tmp_path / 'bundle', adapter_file_manifest=tmp_path / 'files',
                           build_manifest=tmp_path / 'build.json')
    source = tmp_path / 'context/source' / training.native_runtime.DDS_STATUS_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text('reviewed print_status source')
    assets = dict(bootstrap_files={training.native_runtime.DDS_STATUS_SOURCE: training.native_runtime.digest(source)})
    assets_path = tmp_path / 'assets.json'
    assets_path.write_text(json.dumps(assets))
    monkeypatch.setattr(training.native_runtime, 'ASSETS', assets_path)
    bundle, image = Mock(), Mock()
    monkeypatch.setattr(training.native_runtime, 'verify_adapter', bundle)
    monkeypatch.setattr(training.native_runtime, 'verify_adapter_image', image)
    assert training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': kind}}) == assets
    bundle.assert_called_once_with(args.adapter_bundle, args.adapter_file_manifest, assets)
    image.assert_called_once_with(assets)
    image.reset_mock()
    source.write_text('changed status parser contract')
    with pytest.raises(ValueError, match='bootstrap source'):
        training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': kind}})
    image.assert_not_called()


def desktop_adapter(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    output = tmp_path / 'run'
    (output / 'simulator').mkdir(parents=True)
    primary = dict(Image='image', State={'Running': True}, Config={'User': f'{os.getuid()}:{os.getgid()}',
        'WorkingDir': '/work/rootfs'}, HostConfig={'Privileged': False, 'Devices': []},
        NetworkSettings={'Ports': {}, 'Networks': {'owned-network': {}}},
        Mounts=[dict(Destination='/work', Source=str(output / 'simulator'), RW=True)])
    monkeypatch.setattr(training.host, 'owned_container_info', Mock(return_value=primary))
    monkeypatch.setattr(training.host, 'owned_internal_network_info', Mock(return_value={'Name': 'owned-network'}))
    adapter = training.TrainingAdapter(SimpleNamespace(adapter_bundle=tmp_path / 'bundle'), output,
        'token', 'original', 'network', {'image_id': 'image'}, {'adapter_image': 'adapter-image'}, [])
    return adapter, primary


@pytest.mark.parametrize('change', ['image', 'stopped', 'user', 'workdir', 'privileged', 'device', 'ports', 'network', 'mount'])
def test_desktop_bootstrap_rechecks_original_authority_before_readonly_status(tmp_path, monkeypatch, change):
    import copy
    adapter, primary = desktop_adapter(tmp_path, monkeypatch)
    primary = copy.deepcopy(primary)
    if change == 'image': primary['Image'] = 'replacement'
    elif change == 'stopped': primary['State']['Running'] = False
    elif change == 'user': primary['Config']['User'] = '0:0'
    elif change == 'workdir': primary['Config']['WorkingDir'] = '/other'
    elif change == 'privileged': primary['HostConfig']['Privileged'] = True
    elif change == 'device': primary['HostConfig']['Devices'] = ['/dev/ttyUSB0']
    elif change == 'ports': primary['NetworkSettings']['Ports'] = {'14550/udp': 'host'}
    elif change == 'network': primary['NetworkSettings']['Networks'] = {'other-network': {}}
    else: primary['Mounts'][0]['RW'] = False
    monkeypatch.setattr(training.host, 'owned_container_info', Mock(return_value=primary))
    adapter.command = Mock(side_effect=AssertionError('probe must not execute'))
    with pytest.raises(ValueError, match='identity or isolation'):
        adapter.bootstrap_status(timeout=1)
    adapter.command.assert_not_called()


def test_desktop_adapter_retains_original_cid_for_cleanup_on_bootstrap_failure(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    adapter, _ = desktop_adapter(tmp_path, monkeypatch)
    def launch(argv, name):
        assert '/work/ws' not in ' '.join(argv)  # Runtime scripts source ROS; host workspace is not mounted.
        assert argv[argv.index('--network') + 1] == 'container:original'
        adapter.created.append('adapter-original')
        return 'adapter-original'
    adapter.launch = launch
    adapter.bootstrap = AsyncMock(side_effect=TimeoutError('no DDS session'))
    with pytest.raises(TimeoutError):
        adapter.start()
    assert adapter.created == ['adapter-original']
    assert adapter.sidecar == 'adapter-original'
    assert not (adapter.output / 'native-adapter-ready.json').exists()
    script = (adapter.output / 'simulator/adapter.sh').read_text()
    assert '/runtime/private/guidance.sock' in script and '/work/ws/install/setup.bash' in script


def camera_source_fixture(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    (tmp_path / 'native').mkdir()
    source = tmp_path / 'context/source/gzbridge.cpp'
    source.parent.mkdir(parents=True)
    source.write_text('source-clock-proof')
    contract = dict(schema_version=1, clock_source='gzbridge.cpp', clock_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    (tmp_path / 'native/gazebo-camera-runtime.json').write_text(json.dumps(contract))
    relative = 'gazebo/models/mono_cam/model.sdf'
    camera = tmp_path / 'packaged' / relative
    camera.parent.mkdir(parents=True)
    camera.write_text('<sdf><model><pose>0 0 0 0 0 0</pose><link name="camera_link">'
        '<sensor name="camera"><pose>0 0 0 0 0 0</pose><camera><horizontal_fov>1.74</horizontal_fov>'
        '<image><width>1280</width><height>960</height></image></camera></sensor></link></model></sdf>')
    scenario = dict(expected_parameters={'MAV_TYPE': 22}, descriptor_sha256='scenario', added_resources={'server.config': {}}, descriptor=dict(
        server_config={'sha256': 'server'},
        camera={'model': 'mono_cam', 'link': 'camera_link', 'sensor': 'camera'}, world='courtyard', model='quadplane',
        camera_mount={'frame': 'base_link_flu', 'pose': [.12, .03, .242, 0, 0, 0]}, resources={relative: {'sha256': hashlib.sha256(camera.read_bytes()).hexdigest()}}))
    monkeypatch.setattr(training, 'ROOT', tmp_path)
    from classes import fixed_camera_calibration
    signature = Mock(return_value='sha256-v1:' + 'a' * 64)
    monkeypatch.setattr(fixed_camera_calibration, 'selected_source_signature', signature)
    return SimpleNamespace(build_manifest=tmp_path / 'build.json'), scenario, source, camera, signature


@pytest.mark.parametrize('kind', [1, 22])
def test_camera_config_uses_same_actual_source_and_fixed_body_mount(tmp_path, monkeypatch, kind):
    import math
    from classes.fixed_camera_calibration import FixedCameraCalibration
    args, scenario, _, _, signature = camera_source_fixture(tmp_path, monkeypatch)
    scenario['expected_parameters']['MAV_TYPE'] = kind
    value = training.camera_training_source(args, scenario, 'token')
    assert value['config'] == dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id='token:courtyard',
        world='courtyard', image_topic='/world/courtyard/model/quadplane_0/link/camera_link/sensor/camera/image',
        max_attitude_skew_s=.1)
    calibration = FixedCameraCalibration.from_mapping(value['calibration'])
    assert calibration.focal_length_px == (640 / math.tan(.87),) * 2
    assert calibration.principal_point_px == (640., 480.)
    assert calibration.optical_to_body.w == calibration.optical_to_body.x == calibration.optical_to_body.y == calibration.optical_to_body.z == .5
    assert signature.call_args.kwargs['options'] == {'world': 'courtyard', 'pixel_format': 'RGB_INT8'}
    assert value['actual_camera_info_confirmation'] is False


@pytest.mark.parametrize('skew', [0., -1., float('nan'), float('inf'), True])
def test_training_rejects_invalid_source_pairing_bound(tmp_path, monkeypatch, skew):
    args, scenario, *_ = camera_source_fixture(tmp_path, monkeypatch)
    args.max_attitude_skew_s = skew
    with pytest.raises(ValueError, match='finite positive'):
        training.camera_training_source(args, scenario, 'token')


def test_training_uses_one_explicit_camera_pairing_bound(tmp_path, monkeypatch):
    args, scenario, *_ = camera_source_fixture(tmp_path, monkeypatch)
    args.max_attitude_skew_s = .075
    assert training.camera_training_source(args, scenario, 'token')['config']['max_attitude_skew_s'] == .075


@pytest.mark.parametrize('changed', ['clock', 'resource', 'rotation'])
def test_camera_source_refuses_unverified_clock_resource_and_mount(tmp_path, monkeypatch, changed):
    args, scenario, source, camera, _ = camera_source_fixture(tmp_path, monkeypatch)
    if changed == 'clock': source.write_text('changed')
    elif changed == 'resource': camera.write_text('changed')
    else: scenario['descriptor']['camera_mount']['pose'][3] = float('nan')
    with pytest.raises(ValueError):
        training.camera_training_source(args, scenario, 'token')


def test_mc_training_keeps_existing_udp_source():
    assert training.camera_training_source(None, {'expected_parameters': {'MAV_TYPE': 2}}, 'token') is None


def test_provider_overrides_firmware_entrypoint_and_owns_original_cleanup(tmp_path, monkeypatch):
    import os
    import socket
    runtime = tmp_path / 'run'
    runtime.mkdir()
    config = dict(socket_path='/run/pixeagle-camera/camera.sock', source_clock_id='token:world',
                  world='world', image_topic='/world/world/model/quadplane_0/link/camera_link/sensor/camera/image')
    launches, created = [], []
    bound = []
    def launch(self, argv, name):
        launches.append(argv)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(runtime / 'camera/camera.sock'))
        bound.append(sock)
        (runtime / 'camera/camera-info.json').write_text(json.dumps(dict(actual_camera_info_confirmation=True,
            source_clock_id=config['source_clock_id'], image_topic=config['image_topic'])))
        self.created.append('original-camera-cid')
        return 'original-camera-cid'
    monkeypatch.setattr(training.OwnedContainerLaunch, 'launch', launch)
    monkeypatch.setattr(training.host, 'owned_container_info', lambda cid, token: dict(
        State={'Running': True}, Image='firmware-image', Config={'User': f'{os.getuid()}:{os.getgid()}'},
        HostConfig={'NetworkMode': 'container:original-primary', 'Privileged': False, 'Devices': []},
        NetworkSettings={'Ports': {}}))
    try:
        mounts = training.start_camera_provider(None, runtime, 'token', 'original-primary',
            {'image_id': 'firmware-image'}, {'config': config}, created)
        assert mounts == [(runtime / 'camera', Path('/run/pixeagle-camera'), False)]
        argv = launches[0]
        assert argv[argv.index('--entrypoint') + 1] == '/usr/bin/python3'
        assert argv.index('--entrypoint') < argv.index('firmware-image')
        assert 'GZ_PARTITION=token' in argv and 'GZ_IP=127.0.0.1' in argv
        assert '--read-only' in argv and '--privileged' not in argv and '--device' not in argv
        assert created == ['original-camera-cid']
        assert json.loads((runtime / 'camera-source.json').read_text())['renderer_or_following_qualified'] is False
    finally:
        for sock in bound:
            sock.close()


@pytest.mark.parametrize('clock', [None, 'a' * 32 + ':courtyard'])
def test_adapter_clock_parameter_is_only_the_current_declared_world(tmp_path, clock):
    from tools.native_adapter_runtime import adapter_launch_args
    adapter_launch_args(tmp_path, tmp_path / 'bundle', {'adapter_image': 'image'}, token='a' * 32,
        primary='original', label='owner', name='adapter', simulator_clock_id=clock)
    script = (tmp_path / 'adapter.sh').read_text()
    if clock is None:
        assert 'simulator_clock_id' not in script
    else:
        assert f'-p simulator_clock_id:={clock}' in script
    assert '-p socket_path:=/runtime/private/guidance.sock' in script


@pytest.mark.parametrize('clock', ['b' * 32 + ':courtyard', 'a' * 32 + ':world;exit', '', True])
def test_wrong_or_nonliteral_clock_parameter_refuses_before_adapter_scripts(tmp_path, clock):
    from tools.native_adapter_runtime import adapter_launch_args
    with pytest.raises(ValueError, match='Simulator clock'):
        adapter_launch_args(tmp_path, tmp_path / 'bundle', {'adapter_image': 'image'}, token='a' * 32,
            primary='original', label='owner', name='adapter', simulator_clock_id=clock)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('change', [None, 'source', 'writable', 'type', 'propagation', 'missing', 'duplicate'])
def test_desktop_mount_identity_ignores_only_list_order(tmp_path, monkeypatch, change):
    from copy import deepcopy
    adapter, primary = desktop_adapter(tmp_path, monkeypatch)
    original = [dict(Type='bind', Source=str(adapter.output/'simulator'), Destination='/work', RW=True, Propagation='rprivate'),
        dict(Type='bind', Source='/tmp/.X11-unix/X0', Destination='/tmp/.X11-unix/X0', RW=False, Propagation='rprivate'),
        dict(Type='bind', Source='/owned/auth', Destination='/run/training-xauthority', RW=False, Propagation='rprivate')]
    primary['Mounts'] = deepcopy(original)
    monkeypatch.setattr(training.host, 'owned_container_info', Mock(return_value=primary))
    adapter = training.TrainingAdapter(adapter.args, adapter.output, adapter.token, adapter.primary, adapter.network_id,
                                      adapter.baseline, adapter.assets, [])
    primary['Mounts'] = deepcopy(list(reversed(original)))
    if change == 'source': primary['Mounts'][0]['Source'] = '/replacement/auth'
    elif change == 'writable': primary['Mounts'][0]['RW'] = True
    elif change == 'type': primary['Mounts'][0]['Type'] = 'volume'
    elif change == 'propagation': primary['Mounts'][0]['Propagation'] = 'rshared'
    elif change == 'missing': primary['Mounts'].pop()
    elif change == 'duplicate': primary['Mounts'].append(deepcopy(primary['Mounts'][0]))
    if change is None:
        assert adapter.primary_info() is primary
    else:
        with pytest.raises(ValueError, match='identity or isolation'):
            adapter.primary_info()


@pytest.mark.parametrize('kind', [1, 19, 20, 21, 22, 23, 24, 47])
def test_declared_fw_and_vtol_types_require_the_existing_native_owner(kind):
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='requires the verified native adapter'):
        training.native_training_assets(SimpleNamespace(), 'gazebo', {'expected_parameters': {'MAV_TYPE': kind}})


@pytest.mark.parametrize('angles,expected', [
    ((0., 0., 0.), ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))),
    ((0., -1.5707963267948966, 0.), ((0., 0., -1.), (0., 1., 0.), (1., 0., 0.))),
    ((0., .5235987755982988, 0.), ((.8660254037844386, 0., .5), (0., 1., 0.), (-.5, 0., .8660254037844386))),
    ((0., 0., 1.5707963267948966), ((0., -1., 0.), (1., 0., 0.), (0., 0., 1.))),
    ((1.5707963267948966, 0., 0.), ((1., 0., 0.), (0., 0., 1.), (0., -1., 0.))),
])
def test_calibration_mount_rotation_preserves_independent_optical_axes(tmp_path, monkeypatch, angles, expected):
    from classes.aircraft_state import Vector3
    from classes.fixed_camera_calibration import FixedCameraCalibration
    args, scenario, _, _, _ = camera_source_fixture(tmp_path, monkeypatch)
    scenario['descriptor']['camera_mount']['pose'][3:] = list(angles)
    value = training.camera_training_source(args, scenario, 'token')
    rotation = FixedCameraCalibration.from_mapping(value['calibration']).optical_to_body
    for optical, body in zip((Vector3(0, 0, 1), Vector3(1, 0, 0), Vector3(0, 1, 0)), expected):
        actual = rotation.rotate(optical)
        assert (actual.x, actual.y, actual.z) == pytest.approx(body, abs=1e-12)


def test_nose_camera_points_up_in_mc_and_at_horizon_in_fw_without_phase_switch(tmp_path, monkeypatch):
    import math
    from classes.aircraft_state import Quaternion, Vector3
    from classes.fixed_camera_calibration import FixedCameraCalibration
    args, scenario, _, _, _ = camera_source_fixture(tmp_path, monkeypatch)
    scenario['expected_parameters']['MAV_TYPE'] = 20
    scenario['descriptor']['camera_mount']['pose'] = [0., 0., .34, 0., -math.pi / 2, 0.]
    rotation = FixedCameraCalibration.from_mapping(training.camera_training_source(args, scenario, 'token')['calibration']).optical_to_body
    ray = rotation.rotate(Vector3(0., 0., 1.))
    assert (ray.x, ray.y, ray.z) == pytest.approx((0., 0., -1.), abs=1e-12)
    fw_attitude = Quaternion.from_euler(0., -math.pi / 2, 0.)
    forward = fw_attitude.rotate(ray)
    right = fw_attitude.rotate(rotation.rotate(Vector3(1., 0., 0.)))
    down = fw_attitude.rotate(rotation.rotate(Vector3(0., 1., 0.)))
    for actual, expected in [(forward, (1., 0., 0.)), (right, (0., 1., 0.)), (down, (0., 0., 1.))]:
        assert (actual.x, actual.y, actual.z) == pytest.approx(expected, abs=1e-12)


def test_rendered_gimbal_source_has_intrinsics_without_false_fixed_mount_calibration(tmp_path, monkeypatch):
    args, scenario, _, _, _ = camera_source_fixture(tmp_path, monkeypatch)
    descriptor = scenario['descriptor']
    descriptor.pop('camera_mount')
    descriptor['articulated_camera'] = {'mechanics': 'ideal_joint_velocity'}
    value = training.camera_training_source(args, scenario, 'token')
    assert value['calibration'] is None
    assert value['intrinsics']['image_size_px'] == [1280, 960]
    assert value['config']['image_topic'] == f'/world/courtyard/model/{descriptor["model"]}_0/link/camera_link/sensor/camera/image'
