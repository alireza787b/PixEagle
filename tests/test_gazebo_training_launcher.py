"""Inert desktop preparation: no X11, Docker, flight or network dependencies."""
import configparser
from pathlib import Path

import pytest

from tools import run_gazebo_training as training


def test_private_qgc_profile_disables_unrelated_autoconnect(tmp_path):
    destination = training.qgc_settings(tmp_path, 'http://127.0.0.1:5077')
    config = configparser.ConfigParser()
    config.read(destination)
    assert set(config['AutoConnect'].values()) == {'false'}
    links = config['LinkConfigurations']
    assert links['count'] == '1' and links['link0\\port'] == '14560'
    assert links['link0\\type'] == '1' and links['link0\\auto'] == 'true'
    assert config['PixEagle']['companionendpoint'] == 'http://127.0.0.1:5077'
    assert not destination.stat().st_mode & 0o077
    with pytest.raises(FileExistsError):
        training.qgc_settings(tmp_path, 'http://127.0.0.1:5078')


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
