"""Synthetic resource/scene contracts. These tests never launch Gazebo or render pixels."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import Mock

import pytest

from tools import gazebo_scenario as scenario
from tools import sih_isolated_host as host
from tools import run_native_vector_sih as runner

NAME = "x500-mono-camera-aruco-v1"


@pytest.fixture
def package(tmp_path, monkeypatch):
    value = json.loads((scenario.SCENARIOS / (NAME + ".json")).read_text())
    resources = {
        value["airframe_chain"][0]: '. ${R}etc/init.d-posix/airframes/4001_gz_x500\n',
        value["airframe_chain"][1]: '. ${R}etc/init.d/rc.mc_defaults\nparam set-default CA_AIRFRAME 0\n'
            'param set-default CA_ROTOR_COUNT 4\nparam set-default SIM_GZ_EN 1\n',
        value["airframe_chain"][2]: 'param set-default MAV_TYPE 2\n',
        'gazebo/worlds/aruco.sdf': '<sdf><world name="aruco"><model name="ground_plane"/>'
            '<include><uri>model://arucotag</uri></include></world></sdf>',
        'gazebo/models/x500_mono_cam/model.sdf': '<sdf><model name="x500_mono_cam">'
            '<include><uri>x500</uri></include><include><uri>model://mono_cam</uri></include></model></sdf>',
        'gazebo/models/x500/model.sdf': '<sdf><model name="x500"><include><uri>model://x500_base</uri>'
            '</include></model></sdf>',
        'gazebo/models/x500_base/model.sdf': '<sdf><model name="x500_base"/></sdf>',
        'gazebo/models/mono_cam/model.sdf': '<sdf><model name="mono_cam"><link name="camera_link">'
            '<sensor name="camera" type="camera"/></link></model></sdf>',
        'gazebo/models/arucotag/model.sdf': '<sdf><model name="arucotag"/></sdf>',
        'gazebo/models/arucotag/arucotag.png': 'synthetic texture bytes',
        'gazebo/server.config': 'synthetic server config',
        'gazebo/plugins/libGstCameraSystem.so': 'synthetic camera plugin',
        'gazebo/plugins/libMotorFailurePlugin.so': 'synthetic motor plugin',
    }
    manifest = {'kind': 'pixeagle_gazebo_build', 'image_id': value['image_id'],
        'build': {'model': 'quadtailsitter', 'world': 'default', 'airframe_id': 4018, 'distribution': 'harmonic'},
        'artifacts': {'binary_sha256': value['binary_sha256'], 'etc': {}, 'gazebo': {}}}
    baseline = {'kind': 'verified_gazebo_source_build', 'manifest': str(tmp_path / 'build.json'),
        'manifest_sha256': value['build_manifest_sha256'], 'image_id': value['image_id'],
        'binary_sha256': value['binary_sha256']}
    value['resources'] = {}
    for name, raw in resources.items():
        path = tmp_path / 'packaged' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
        pin = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': False}
        value['resources'][name] = pin
        area, member = name.split('/', 1)
        manifest['artifacts'][area][member] = pin.copy()
    directory = tmp_path / 'scenarios'
    directory.mkdir()
    monkeypatch.setattr(scenario, 'SCENARIOS', directory)
    def save():
        (directory / (NAME + '.json')).write_text(json.dumps(value))
    save()
    return value, manifest, baseline, save


def test_explicit_scenario_preserves_build_identity_and_stages_no_control(tmp_path, package):
    value, manifest, baseline, _ = package
    before = deepcopy(manifest)
    checked = scenario.verified_scenario(NAME, baseline, manifest)
    assert checked['expected_parameters'] == {'SYS_AUTOSTART': 4010, 'MAV_TYPE': 2,
        'CA_AIRFRAME': 0, 'CA_ROTOR_COUNT': 4, 'SIM_GZ_EN': 1}
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
        token='owner', name='camera', gazebo_scenario=NAME)
    assert 'PX4_SIM_MODEL=gz_x500_mono_cam' in argv and 'PX4_GZ_WORLD=aruco' in argv
    assert 'PX4_GZ_MODEL_POSE=-6,0,0,0,0,0' in argv
    assert 'PX4_VIDEO_HOST_IP=127.0.0.1' in argv
    assert baseline['image_id'] in argv and argv[argv.index('--network') + 1] == 'none'
    assert not {'arm', 'takeoff', '--privileged', '-p', '--device'} & set(argv)
    assert manifest == before and manifest['build']['airframe_id'] == 4018


@pytest.mark.parametrize('change', ['model', 'world', 'airframe', 'image', 'elf', 'manifest', 'variant',
    'missing_texture', 'missing_plugin', 'missing_airframe', 'resource_pin', 'resource_bytes', 'symlink',
    'nan', 'inf', 'bool_pose', 'short_pose', 'unknown', 'camera', 'extra_scene', 'schema', 'include',
    'cycle', 'conditional', 'duplicate_parameter', 'computed_parameter', 'missing_parameter'])
def test_bad_scenario_refuses_before_staging(tmp_path, package, change):
    value, manifest, baseline, save = package
    if change == 'model': value['model'] = 'x500'
    if change == 'world': value['world'] = 'default'
    if change == 'airframe': value['airframe_id'] = 4014
    if change in ('image', 'elf', 'manifest'):
        baseline[{'image': 'image_id', 'elf': 'binary_sha256', 'manifest': 'manifest_sha256'}[change]] = 'wrong'
    if change == 'variant': manifest['build']['resource_variant'] = {'name': 'quadtailsitter-no-pitot-v1'}
    if change.startswith('missing_') and change != 'missing_parameter':
        name = {'missing_texture': 'gazebo/models/arucotag/arucotag.png',
            'missing_plugin': 'gazebo/plugins/libGstCameraSystem.so',
            'missing_airframe': value['airframe_chain'][1]}[change]
        del value['resources'][name]
    name = value['airframe_chain'][1]
    path = tmp_path / 'packaged' / name
    if change == 'resource_pin': value['resources'][name]['sha256'] = '0' * 64
    if change == 'resource_bytes': path.write_text('changed')
    if change == 'symlink':
        moved = path.with_suffix('.copy'); path.rename(moved); path.symlink_to(moved)
    if change in ('nan', 'inf', 'bool_pose'): value['spawn_pose'][0] = {'nan': float('nan'), 'inf': float('inf'), 'bool_pose': True}[change]
    if change == 'short_pose': value['spawn_pose'].pop()
    if change == 'camera': value['camera']['sensor'] = 'missing'
    if change == 'extra_scene': value['scene_models'].append('other_aircraft')
    if change == 'schema': value['schema_version'] = True
    if change in ('include', 'cycle', 'conditional', 'duplicate_parameter', 'computed_parameter', 'missing_parameter'):
        text = path.read_text()
        if change == 'include': text += '. ${R}etc/undeclared\n'
        if change == 'cycle': text += '. ${R}' + value['airframe_chain'][0] + '\n'
        if change == 'conditional': text = 'if true; then\n' + text + 'fi\n'
        if change == 'duplicate_parameter': text += 'param set-default CA_ROTOR_COUNT 4\n'
        if change == 'computed_parameter': text = text.replace('CA_ROTOR_COUNT 4', 'CA_ROTOR_COUNT $COUNT')
        if change == 'missing_parameter': text = text.replace('param set-default CA_ROTOR_COUNT 4\n', '')
        path.write_text(text)
        pin = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': False}
        value['resources'][name] = pin
        manifest['artifacts']['etc'][name.removeprefix('etc/')] = pin
    save()
    with pytest.raises(ValueError):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario='unknown-v1' if change == 'unknown' else NAME)
    assert not (tmp_path / 'run').exists()


@pytest.mark.parametrize('requested', ['sihsim_quadx', 'gz_quadtailsitter', 'gz_x500'])
def test_explicit_model_cannot_be_silently_replaced_by_camera_scenario(tmp_path, package, requested):
    _, manifest, baseline, _ = package
    with pytest.raises(ValueError, match='Requested simulator model differs'):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario=NAME, model=requested)
    assert not (tmp_path / 'run').exists()


def test_scenario_is_not_a_sih_or_unverified_build_escape(tmp_path):
    with pytest.raises(ValueError, match='verified Gazebo'):
        host.simulation_launch_args('sih', {}, None, runtime=tmp_path, token='x', name='x', gazebo_scenario=NAME)
    with pytest.raises(ValueError, match='verified Gazebo'):
        runner.verify_simulator('no-query', 0, tmp_path / 'absent', gazebo_scenario=NAME)


@pytest.mark.parametrize('parameter', ['SYS_AUTOSTART', 'MAV_TYPE', 'CA_ROTOR_COUNT'])
def test_startup_overlay_cannot_change_declared_aircraft_identity(tmp_path, package, parameter):
    _, manifest, baseline, _ = package
    with pytest.raises(ValueError, match='cannot override'):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario=NAME, startup_parameters={parameter: '1'})
    assert not (tmp_path / 'run').exists()


@pytest.mark.parametrize('change', [None, 'model', 'world', 'image', 'binary', 'spawn', 'camera_host',
    'runtime_resources', 'runtime_parent_airframe', 'extra_entity', 'missing_marker', 'extra_topic_model',
    'missing_image', 'extra_image', 'parameter', 'empty_partition'])
def test_runtime_requires_actual_scenario_and_keeps_original_build(tmp_path, package, monkeypatch, change):
    value, manifest, baseline, _ = package
    monkeypatch.setattr(runner, 'verified_simulation_build', lambda *a, **k: ('gazebo', baseline, manifest))
    environment = {'PX4_GZ_WORLD': 'aruco', 'PX4_GZ_MODELS': '/opt/px4/gazebo/models',
        'PX4_GZ_WORLDS': '/opt/px4/gazebo/worlds',
        'GZ_SIM_RESOURCE_PATH': '/opt/px4/gazebo/models:/opt/px4/gazebo/worlds',
        'GZ_SIM_SYSTEM_PLUGIN_PATH': '/opt/px4/gazebo/plugins',
        'GZ_SIM_SERVER_CONFIG_PATH': '/opt/px4/gazebo/server.config', 'GZ_PARTITION': 'owned',
        'PX4_GZ_MODEL_POSE': '-6,0,0,0,0,0', 'PX4_VIDEO_HOST_IP': '127.0.0.1'}
    if change in ('world', 'spawn', 'camera_host', 'empty_partition'):
        environment[{'world': 'PX4_GZ_WORLD', 'spawn': 'PX4_GZ_MODEL_POSE', 'camera_host': 'PX4_VIDEO_HOST_IP',
                     'empty_partition': 'GZ_PARTITION'}[change]] = ''
    def read(*args):
        if args[1] == 'inspect':
            return json.dumps([{'Id': 'original', 'Image': 'wrong' if change == 'image' else baseline['image_id'],
                'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'Devices': []},
                'NetworkSettings': {'Ports': {}}, 'Mounts': [{'Source': str(tmp_path), 'Destination': '/work'}]}])
        if args[-1] == 'verify':
            return json.dumps([{'args': ['/opt/px4/bin/px4', '-i', '0'], 'cwd': '/work/rootfs',
                'model': 'gz_quadtailsitter' if change == 'model' else 'gz_x500_mono_cam',
                'environment': environment, 'binary_sha256': 'bad' if change == 'binary' else baseline['binary_sha256']}])
        if 'python3' in args:
            chain = {name: value['resources'][name]['sha256'] for name in value['airframe_chain']}
            if change == 'runtime_parent_airframe': chain[value['airframe_chain'][1]] = 'bad'
            return json.dumps({'gazebo': {} if change == 'runtime_resources' else manifest['artifacts']['gazebo'],
                'airframe_sha256': value['resources'][value['airframe_chain'][0]]['sha256'], 'scenario_airframes': chain})
        if 'service' in args:
            names = ['ground_plane', 'arucotag', 'x500_mono_cam_0']
            if change == 'extra_entity': names.append('other')
            if change == 'missing_marker': names.remove('arucotag')
            return ''.join('model {\n  name: "' + name + '"\n}\n' for name in names)
        if 'topic' in args:
            topics = ['/world/aruco/pose/info', '/world/aruco/dynamic_pose/info',
                '/model/x500_mono_cam_0/odometry_with_covariance',
                '/world/aruco/model/x500_mono_cam_0/link/base_link/sensor/imu_sensor/imu',
                '/world/aruco/model/x500_mono_cam_0/link/camera_link/sensor/camera/image']
            if change == 'missing_image': topics.pop()
            if change == 'extra_image': topics.append('/world/aruco/model/x500_mono_cam_0/link/other/sensor/other/image')
            if change == 'extra_topic_model': topics.append('/model/other/odometry')
            return '\n'.join(topics)
        if '/opt/px4/bin/px4-param' in args:
            return '\n'.join(f'{k}: {v}' for k, v in {'SYS_AUTOSTART': 4010,
                'MAV_TYPE': 2, 'CA_AIRFRAME': 0, 'CA_ROTOR_COUNT': 6 if change == 'parameter' else 4, 'SIM_GZ_EN': 1}.items())
        assert '/opt/px4/bin/px4-listener' in args
        return 'autopilot_uid: 123456789\n'
    commands = Mock(side_effect=read)
    monkeypatch.setattr(runner, 'command', commands)
    socket_path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(socket_path))
        if change:
            with pytest.raises(ValueError):
                runner.verify_simulator('original', 0, socket_path,
                    simulation_build_manifest=Path(baseline['manifest']), gazebo_scenario=NAME)
        else:
            checked = runner.verify_simulator('original', 0, socket_path,
                simulation_build_manifest=Path(baseline['manifest']), gazebo_scenario=NAME)
            assert checked['firmware_build'] == baseline
            assert checked['gazebo']['runtime_scenario']['descriptor']['airframe_id'] == 4010
            assert checked['gazebo']['expected_parameters']['MAV_TYPE'] == 2
            assert checked['gazebo']['model'] == 'x500_mono_cam_0'
    assert not any(set(call.args) & {'arm', 'takeoff', 'set', '--pub', 'run', 'start'} for call in commands.call_args_list)
