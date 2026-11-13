"""Desktop access cannot turn a simulator into a route to the aircraft network."""
from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from tools import sih_isolated_host as host


NETWORK = 'a' * 64
TOKEN = 'isolated-owner'


def network():
    return dict(Id=NETWORK, Labels={host.LABEL: TOKEN}, Driver='bridge', Internal=True,
                EnableIPv6=False, Containers={})


@pytest.mark.parametrize('change', ['token', 'external', 'host', 'id', 'ipv6', 'multiple'])
def test_unowned_or_external_network_is_rejected_before_staging(tmp_path, monkeypatch, change):
    info = network()
    if change == 'token': info['Labels'][host.LABEL] = 'another-owner'
    if change == 'external': info['Internal'] = False
    if change == 'host': info['Driver'] = 'host'
    if change == 'id': info['Id'] = 'b' * 64
    if change == 'ipv6': info['EnableIPv6'] = True
    reply = [info, deepcopy(info)] if change == 'multiple' else [info]
    command = Mock(return_value=json.dumps(reply))
    monkeypatch.setattr(host, 'command', command)
    with pytest.raises(RuntimeError):
        host.simulation_launch_args('sih', {}, None, runtime=tmp_path / 'run', token=TOKEN,
            name='training', desktop_network_id=NETWORK, published_tcp_ports=(5077,))
    assert not (tmp_path / 'run').exists()
    command.assert_called_once_with('docker', 'network', 'inspect', NETWORK)


def test_loopback_tcp_access_does_not_expose_mavlink_or_video_udp(tmp_path, monkeypatch):
    monkeypatch.setattr(host, 'command', Mock(return_value=json.dumps([network()])))
    args = host.simulation_launch_args('sih', {'image_id': 'synthetic-image'}, None, runtime=tmp_path, token=TOKEN,
        name='training', desktop_network_id=NETWORK, published_tcp_ports=(5077, 3040))
    assert args[args.index('--network') + 1] == NETWORK
    assert [args[i + 1] for i, arg in enumerate(args) if arg == '--publish'] == [
        '127.0.0.1:5077:5077/tcp', '127.0.0.1:3040:3040/tcp']
    assert not any('/udp' in arg for arg in args)


@pytest.mark.parametrize('ports', [(True,), (80,), (65536,), (5077, 5077), ('5077',)])
def test_invalid_publication_refuses(tmp_path, monkeypatch, ports):
    monkeypatch.setattr(host, 'command', Mock(return_value=json.dumps([network()])))
    with pytest.raises(ValueError):
        host.simulation_launch_args('sih', {}, None, runtime=tmp_path, token=TOKEN,
            name='training', desktop_network_id=NETWORK, published_tcp_ports=ports)


def test_network_cleanup_requires_no_attached_containers(monkeypatch):
    info = network()
    info['Containers'] = {'foreign-id': {}}
    command = Mock(return_value=json.dumps([info]))
    monkeypatch.setattr(host, 'command', command)
    with pytest.raises(RuntimeError, match='attached'):
        host.remove_owned_internal_network(NETWORK, TOKEN)
    command.assert_called_once_with('docker', 'network', 'inspect', NETWORK)


def test_network_none_remains_the_default(tmp_path):
    args = host.simulation_launch_args('sih', {}, None, runtime=tmp_path, token=TOKEN, name='training')
    assert args[args.index('--network') + 1] == 'none'
    with pytest.raises(ValueError):
        host.simulation_launch_args('sih', {}, None, runtime=tmp_path, token=TOKEN,
                                    name='training', published_tcp_ports=(5077,))
