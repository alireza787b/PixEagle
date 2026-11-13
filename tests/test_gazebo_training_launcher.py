"""Inert desktop preparation: no X11, Docker, flight or network dependencies."""
import configparser
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from tools import run_gazebo_training as training


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


@pytest.mark.parametrize('kind', [1, 19, 20, 21, None])
def test_undeclared_aircraft_families_are_not_implicitly_training_ready(kind):
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='declared MC or standard VTOL'):
        training.native_training_assets(SimpleNamespace(), 'gazebo', {'expected_parameters': {'MAV_TYPE': kind}})


@pytest.mark.parametrize('part', ['adapter_bundle', 'adapter_file_manifest'])
def test_incomplete_adapter_authority_refuses(part, tmp_path):
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='supplied together'):
        training.native_training_assets(SimpleNamespace(**{part: tmp_path}), 'gazebo',
                                        {'expected_parameters': {'MAV_TYPE': 22}})


def test_adapter_preflight_checks_bundle_and_source_before_image(tmp_path, monkeypatch):
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
    assert training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': 22}}) == assets
    bundle.assert_called_once_with(args.adapter_bundle, args.adapter_file_manifest, assets)
    image.assert_called_once_with(assets)
    image.reset_mock()
    source.write_text('changed status parser contract')
    with pytest.raises(ValueError, match='bootstrap source'):
        training.native_training_assets(args, 'gazebo', {'expected_parameters': {'MAV_TYPE': 22}})
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
