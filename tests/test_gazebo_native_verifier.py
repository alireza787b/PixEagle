"""Gazebo shares the simulator authority boundary, never SIH model assumptions."""
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import Mock

import pytest

from tools import run_native_vector_sih as runner
from tools import sih_baseline, sih_isolated_host as host


@pytest.mark.parametrize('kind,simulator', [('pixeagle_sih_build', 'sih'), ('pixeagle_gazebo_build', 'gazebo')])
def test_manifest_discriminant_selects_existing_strict_builder(tmp_path, monkeypatch, kind, simulator):
    path = tmp_path / 'build.json'
    path.write_text(json.dumps({'kind': kind}))
    checked = {'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    validate = Mock(return_value=checked)
    monkeypatch.setattr(sih_baseline, 'validate_build_manifest', validate)
    assert host.verified_simulation_build(path, repository=tmp_path) == (simulator, checked, {'kind': kind})
    validate.assert_called_once_with(path, repository=tmp_path, **({'simulator': 'gazebo'} if simulator == 'gazebo' else {}))


@pytest.mark.parametrize('kind', [None, 'gazebo', 'verified_gazebo_source_build', 'pixeagle_other_build'])
def test_unknown_manifest_kind_cannot_select_or_downgrade_builder(tmp_path, monkeypatch, kind):
    path = tmp_path / 'build.json'
    path.write_text(json.dumps({'kind': kind}))
    validate = Mock(side_effect=AssertionError('unknown kind must fail first'))
    monkeypatch.setattr(sih_baseline, 'validate_build_manifest', validate)
    with pytest.raises(ValueError, match='Unknown simulation'):
        host.verified_simulation_build(path)
    validate.assert_not_called()


def test_manifest_change_during_validation_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / 'build.json'
    path.write_text(json.dumps({'kind': 'pixeagle_gazebo_build'}))
    monkeypatch.setattr(sih_baseline, 'validate_build_manifest', lambda *a, **k: {'manifest_sha256': '0' * 64})
    with pytest.raises(ValueError, match='changed during'):
        host.verified_simulation_build(path)


def gazebo_fixture(tmp_path, monkeypatch, change=None, *, rotor_count=4):
    resources = {'models/quadtailsitter/model.sdf': {'sha256': 'c' * 64, 'executable': False}}
    relative = 'init.d-posix/airframes/4018_gz_quadtailsitter'
    airframe = tmp_path / 'packaged/etc' / relative
    airframe.parent.mkdir(parents=True)
    airframe.write_text(f'param set-default CA_ROTOR_COUNT {rotor_count}\n'
        'param set-default CA_SV_CS_COUNT 0\nparam set-default VT_TYPE 0\nparam set-default SIM_GZ_EN 1 # bridge\n')
    checksum = hashlib.sha256(airframe.read_bytes()).hexdigest()
    manifest = {'build': {'model': 'quadtailsitter', 'world': 'default', 'airframe_id': 4018},
                'artifacts': {'gazebo': resources, 'etc': {relative: {'sha256': checksum, 'executable': False}}}}
    baseline = {'image_id': 'sha256:pinned-runtime', 'binary_sha256': 'a' * 64,
                'manifest': str(tmp_path / 'gazebo-build-manifest.json')}
    environment = {'PX4_GZ_WORLD': 'default', 'PX4_GZ_MODELS': '/opt/px4/gazebo/models',
        'PX4_GZ_WORLDS': '/opt/px4/gazebo/worlds',
        'GZ_SIM_RESOURCE_PATH': '/opt/px4/gazebo/models:/opt/px4/gazebo/worlds',
        'GZ_SIM_SYSTEM_PLUGIN_PATH': '/opt/px4/gazebo/plugins',
        'GZ_SIM_SERVER_CONFIG_PATH': '/opt/px4/gazebo/server.config', 'GZ_PARTITION': 'owned-test'}
    if change == 'empty_partition':
        environment['GZ_PARTITION'] = ''
    if change == 'resource_path':
        environment['GZ_SIM_RESOURCE_PATH'] += ':/unreviewed/models'
    monkeypatch.setattr(runner, 'verified_simulation_build', lambda *a, **k: ('gazebo', baseline, manifest))
    calls = []
    def read(*args):
        calls.append(args)
        if args[1] == 'inspect':
            return json.dumps([{'Id': 'owned-container', 'Image': 'other' if change == 'image' else baseline['image_id'],
                'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'Devices': []},
                'NetworkSettings': {'Ports': {}}, 'Mounts': [{'Source': str(tmp_path), 'Destination': '/work'}]}])
        if args[-1] in ('verify', 'legacy'):
            return json.dumps([{'args': ['/opt/px4/bin/px4', '-i', '0'], 'cwd': '/work/rootfs',
                'model': 'gz_x500' if change == 'model' else 'gz_quadtailsitter', 'environment': environment,
                'binary_sha256': ('b' if change == 'binary' else 'a') * 64}])
        if 'python3' in args:
            return json.dumps({'gazebo': {} if change == 'resources' else resources,
                'airframe_sha256': '0' * 64 if change == 'airframe_bytes' else checksum})
        if 'service' in args:
            assert args[-8:] == ('--reqtype', 'gz.msgs.Empty', '--reptype', 'gz.msgs.Scene', '--timeout', '2000', '--req', '')
            model = 'x500_0' if change == 'scene_model' else 'quadtailsitter_0'
            scene = 'model {\n  name: "ground_plane"\n}\nmodel {\n  name: "' + model + '"\n}\n'
            return scene + ('model {\n  name: "other_aircraft"\n}\n' if change == 'extra_model' else '')
        if 'topic' in args:
            topics = ['/world/default/pose/info', '/world/default/dynamic_pose/info',
                      '/model/quadtailsitter_0/odometry_with_covariance',
                      '/world/default/model/quadtailsitter_0/link/base_link/sensor/imu_sensor/imu']
            if change == 'missing_topic': topics.pop()
            if change == 'other_world': topics.append('/world/unreviewed/pose/info')
            return '\n'.join(topics)
        if '/opt/px4/bin/px4-param' in args:
            values = {'SYS_AUTOSTART': 4018, 'CA_ROTOR_COUNT': rotor_count, 'CA_SV_CS_COUNT': 0, 'VT_TYPE': 0, 'SIM_GZ_EN': 1}
            field = {'airframe': 'SYS_AUTOSTART', 'rotors': 'CA_ROTOR_COUNT', 'surfaces': 'CA_SV_CS_COUNT'}.get(change)
            if field: values[field] += 1
            return '\n'.join(f'x +   {key} [1,2] : {value}' for key, value in values.items())
        assert '/opt/px4/bin/px4-listener' in args
        return 'autopilot_uid: 123456789\n'
    monkeypatch.setattr(runner, 'command', read)
    return baseline, calls


@pytest.mark.parametrize('change', [None, 'image', 'binary', 'model', 'resources', 'resource_path', 'scene_model',
    'extra_model', 'missing_topic', 'other_world', 'airframe', 'rotors', 'surfaces', 'no_manifest',
    'empty_partition', 'airframe_bytes'])
def test_gazebo_requires_consistent_runtime_resource_scene_and_airframe_identity(tmp_path, monkeypatch, change):
    baseline, calls = gazebo_fixture(tmp_path, monkeypatch, change)
    path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        if change:
            with pytest.raises(ValueError):
                runner.verify_simulator('sim', 0, path,
                    simulation_build_manifest=None if change == 'no_manifest' else Path(baseline['manifest']))
        else:
            checked = runner.verify_simulator('sim', 0, path, simulation_build_manifest=Path(baseline['manifest']))
            assert checked['simulator'] == 'gazebo'
            assert checked['firmware_build'] == baseline
            assert checked['gazebo']['model'] == 'quadtailsitter_0'
            assert checked['aircraft_uid'] == '123456789'
    assert not any(set(call) & {'arm', 'takeoff', 'set', '--pub', 'run', 'start'} for call in calls)


def test_transition_constants_reverify_gazebo_source_and_original_manifest(tmp_path, monkeypatch):
    message = tmp_path / 'context/source/msg/versioned/VehicleStatus.msg'
    message.parent.mkdir(parents=True)
    message.write_text('uint8 VEHICLE_TYPE_ROTARY_WING = 21\nuint8 VEHICLE_TYPE_FIXED_WING = 22\n')
    build = {'manifest': str(tmp_path / 'build.json'), 'manifest_sha256': 'a' * 64}
    select = Mock(return_value=('gazebo', build, {}))
    monkeypatch.setattr(runner, 'verified_simulation_build', select)
    verify = Mock()
    monkeypatch.setattr(sih_baseline, 'verify_source', verify)
    result = runner.transition_source_contract({'firmware_build': build}, build_repository=tmp_path)
    assert result['vehicle_types'] == {'multicopter': 21, 'fixed_wing': 22}
    assert verify.call_args.kwargs == {'simulator': 'gazebo'}
    assert verify.call_args.args[1] == tmp_path
    select.return_value = ('gazebo', build | {'manifest_sha256': 'b' * 64}, {})
    with pytest.raises(ValueError, match='build_changed'):
        runner.transition_source_contract({'firmware_build': build}, build_repository=tmp_path)


def test_host_cannot_request_gazebo_without_verified_build_before_staging(tmp_path):
    from argparse import Namespace
    args = Namespace(execute=True, backend_repo=tmp_path, output=tmp_path / 'evidence',
                     simulator_model='gz_quadtailsitter')
    with pytest.raises(ValueError, match='requires a verified Gazebo'):
        host.host(args, driver_path=tmp_path / 'driver.py')
    assert not args.output.exists()


@pytest.mark.parametrize('simulator', ['sih', 'gazebo'])
def test_shared_launch_plan_stages_literal_boot_parameters_before_primary_start(tmp_path, simulator):
    baseline = {'kind': 'verified_source_build' if simulator == 'sih' else 'verified_gazebo_source_build',
                'image_id': 'sha256:fixture'}
    manifest = {'build': {'model': 'quadtailsitter', 'world': 'default', 'distribution': 'harmonic'}}
    argv = host.simulation_launch_args(simulator, baseline, manifest, runtime=tmp_path, token='owner',
        name='sim', startup_parameters={'SDLOG_PROFILE': '131', 'MIS_DIST_1WP': '200.0'})
    assert argv[argv.index('--network') + 1] == 'none'
    assert argv[argv.index('sha256:fixture') + 1:] == ['-i', '0', '-w', '/work/rootfs', '/opt/px4/etc']
    assert 'PX4_PARAM_SDLOG_PROFILE=131' in argv and 'PX4_PARAM_MIS_DIST_1WP=200.0' in argv
    assert argv.index('PX4_PARAM_SDLOG_PROFILE=131') < argv.index('sha256:fixture')
    assert (tmp_path / 'simulator/rootfs').is_dir()
    assert '--user' in argv and '--privileged' not in argv


@pytest.mark.parametrize('parameters', [{'BAD=NAME': '1'}, {'VALID': 'nan'}, {'VALID': 'inf'},
    {'VALID': '1e999'}, {'VALID': '1; arm'}, {'VALID': True}, {'VALID': '1\n2'}])
def test_launch_plan_rejects_malformed_boot_parameters_before_staging(tmp_path, parameters):
    with pytest.raises(ValueError, match='literal name and finite'):
        host.simulation_launch_args('sih', {'kind': 'verified_source_build', 'image_id': 'sha256:fixture'},
            None, runtime=tmp_path, token='owner', name='sim', startup_parameters=parameters)
    assert not (tmp_path / 'simulator').exists()


def test_runtime_counts_come_from_verified_packaged_declarations(tmp_path, monkeypatch):
    baseline, _ = gazebo_fixture(tmp_path, monkeypatch, rotor_count=6)
    path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        result = runner.verify_simulator('sim', 0, path, simulation_build_manifest=Path(baseline['manifest']))
    assert result['gazebo']['expected_parameters']['CA_ROTOR_COUNT'] == 6


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'expression', 'conditional', 'wrong_hash', 'ambiguous_file'])
def test_identity_declarations_refuse_unknown_inherited_or_ambiguous_values(tmp_path, monkeypatch, change):
    baseline, _ = gazebo_fixture(tmp_path, monkeypatch)
    _, _, manifest = runner.verified_simulation_build(Path(baseline['manifest']))
    relative, entry = next(iter(manifest['artifacts']['etc'].items()))
    airframe = tmp_path / 'packaged/etc' / relative
    text = airframe.read_text()
    if change == 'missing': text = text.replace('param set-default CA_ROTOR_COUNT 4\n', '')
    if change == 'duplicate': text += 'param set CA_ROTOR_COUNT 6\n'
    if change == 'expression': text = text.replace('CA_ROTOR_COUNT 4', 'CA_ROTOR_COUNT $COUNT')
    if change == 'conditional': text = 'if false; then\n' + text + 'fi\n'
    airframe.write_text(text)
    entry['sha256'] = hashlib.sha256(airframe.read_bytes()).hexdigest()
    if change == 'wrong_hash': entry['sha256'] = '0' * 64
    if change == 'ambiguous_file': manifest['artifacts']['etc']['init.d-posix/airframes/4018_other'] = entry
    with pytest.raises(ValueError):
        runner.gazebo_airframe_identity(manifest, tmp_path / 'packaged')


@pytest.mark.parametrize('change', ['name', 'wrong_id', 'wrong_token', 'missing_token'])
def test_owned_stop_rejects_replacements_before_stopping(monkeypatch, change):
    identity = 'a' * 64
    info = {'Id': 'b' * 64 if change == 'wrong_id' else identity,
            'Config': {'Labels': {host.LABEL: 'other' if change == 'wrong_token' else 'owner'}},
            'State': {'Running': True}}
    command = Mock(return_value=json.dumps([info]))
    monkeypatch.setattr(host, 'command', command)
    with pytest.raises((ValueError, RuntimeError)):
        host.stop_owned_container('mutable-name' if change == 'name' else identity,
                                  '' if change == 'missing_token' else 'owner')
    assert not any('stop' in call.args for call in command.call_args_list)


@pytest.mark.parametrize('running', [True, False])
def test_owned_stop_rechecks_identity_and_returns_final_state(monkeypatch, running):
    identity = 'a' * 64
    info = {'Id': identity, 'Config': {'Labels': {host.LABEL: 'owner'}}, 'State': {'Running': running}}
    calls = []
    def command(*args, **kwargs):
        calls.append(args)
        if 'stop' in args:
            info['State']['Running'] = False
            return identity
        return json.dumps([info])
    monkeypatch.setattr(host, 'command', command)
    assert host.stop_owned_container(identity, 'owner')['State']['Running'] is False
    assert len([call for call in calls if 'inspect' in call]) == 2
    assert len([call for call in calls if 'stop' in call]) == int(running)


@pytest.mark.parametrize('requested', ['sihsim_quadx', 'gz_x500'])
def test_explicit_model_conflict_refuses_before_host_staging_or_launch(tmp_path, monkeypatch, requested):
    from argparse import Namespace
    baseline = {'kind': 'verified_gazebo_source_build', 'image_id': 'sha256:fixture'}
    manifest = {'build': {'model': 'quadtailsitter', 'world': 'default', 'distribution': 'harmonic'}}
    monkeypatch.setattr(host, 'verified_simulation_build', lambda _: ('gazebo', baseline, manifest))
    command = Mock(side_effect=AssertionError('No commands after incompatible model selection'))
    configure = Mock(side_effect=AssertionError('No configuration after incompatible model selection'))
    monkeypatch.setattr(host, 'command', command)
    output = tmp_path / 'evidence'
    args = Namespace(execute=True, backend_repo=tmp_path, output=output,
                     simulation_build_manifest=tmp_path / 'build.json', simulator_model=requested)
    with pytest.raises(ValueError, match='Requested simulator model differs'):
        host.host(args, driver_path=tmp_path / 'driver.py', configure=configure)
    with pytest.raises(ValueError, match='Requested simulator model differs'):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=output,
                                    token='owner', name='sim', model=requested)
    assert not output.exists()
    command.assert_not_called()
    configure.assert_not_called()


@pytest.mark.parametrize('requested', [None, 'gz_quadtailsitter'])
def test_gazebo_default_or_matching_explicit_model_uses_manifest(tmp_path, requested):
    argv = host.simulation_launch_args('gazebo',
        {'kind': 'verified_gazebo_source_build', 'image_id': 'sha256:fixture'},
        {'build': {'model': 'quadtailsitter', 'world': 'default', 'distribution': 'harmonic'}},
        runtime=tmp_path, token='owner', name='sim', model=requested)
    assert 'PX4_SIM_MODEL=gz_quadtailsitter' in argv


def test_compatibility_sih_model_default_and_launch_are_unchanged(tmp_path):
    argv = host.simulation_launch_args('sih', {'kind': 'compatibility_image', 'reference': host.PX4_IMAGE},
        None, runtime=tmp_path, token='owner', name='sim')
    assert argv == ['docker', 'run', '-d', '-i', '--name', 'sim', '--label', host.LABEL + '=owner',
                    '--network', 'none', '-e', 'PX4_SIM_MODEL=sihsim_quadx', host.PX4_IMAGE]
    assert not (tmp_path / 'simulator').exists()


def test_gazebo_launch_requires_manifest_before_model_derivation_or_staging(tmp_path):
    with pytest.raises(ValueError, match='verified Gazebo build manifest'):
        host.simulation_launch_args('gazebo', {'kind': 'compatibility_image'}, None,
                                    runtime=tmp_path, token='owner', name='sim')
    assert not (tmp_path / 'simulator').exists()
