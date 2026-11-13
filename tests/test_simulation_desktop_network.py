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
            name='training', desktop_network_id=NETWORK)
    assert not (tmp_path / 'run').exists()
    command.assert_called_once_with('docker', 'network', 'inspect', NETWORK)


def test_internal_network_does_not_publish_flight_or_api_ports(tmp_path, monkeypatch):
    monkeypatch.setattr(host, 'command', Mock(return_value=json.dumps([network()])))
    args = host.simulation_launch_args('sih', {'image_id': 'synthetic-image'}, None, runtime=tmp_path, token=TOKEN,
        name='training', desktop_network_id=NETWORK)
    assert args[args.index('--network') + 1] == NETWORK
    assert '--publish' not in args and '-p' not in args
    assert not any('/udp' in arg for arg in args)


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
