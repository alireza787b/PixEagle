"""Deterministic transport faults; no ROS runtime, aircraft or network dependency."""
import pytest

from tools import native_owned_request_fault as fault


@pytest.mark.parametrize('count', [-1, 17, True, None, 1.5, '1'])
def test_drop_policy_rejects_invalid_fixture(count):
    with pytest.raises(ValueError):
        fault.ReleaseDropPolicy(count)


def test_drop_is_bounded_per_acquisition_and_never_affects_acquire():
    policy = fault.ReleaseDropPolicy(1)
    for token in ((1, 2), (3, 4)):
        assert not policy.drop(release=False, token=token)
        assert policy.drop(release=True, token=token)
        assert not policy.drop(release=True, token=token)
        assert not policy.drop(release=True, token=token)
    assert not fault.ReleaseDropPolicy(0).drop(release=True, token=(1, 2))


@pytest.mark.parametrize('token,interfaces,valid', [
    ('a'*32, [(1, 'lo')], True), ('', [(1, 'lo')], False),
    ('a'*32, [(1, 'lo'), (2, 'eth0')], False), ('invalid', [(1, 'lo')], False),
])
def test_relay_refuses_nonisolated_namespace(monkeypatch, token, interfaces, valid):
    monkeypatch.setenv('PIXEAGLE_SITL_OWNED_REQUEST_FAULT', token)
    monkeypatch.setattr(fault.socket, 'if_nameindex', lambda: interfaces)
    if valid:
        fault.require_isolation()
    else:
        with pytest.raises(RuntimeError, match='loopback-only'):
            fault.require_isolation()
