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
