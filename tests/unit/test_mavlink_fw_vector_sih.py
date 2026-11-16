"""Stock FW component fixture/measurement contracts; never launches an aircraft."""

import copy
import math

import pytest
import yaml

from tools.run_mavlink_fw_vector_sih import AirspeedProgress, ROOT, configure_component
from tools import run_mavlink_fw_vector_sih as runner


def packet(counter, value=15.):
    return {"status": {"time": {"counter": counter}}, "message": {"airspeed": value}}


def test_initial_cache_read_is_not_a_fresh_speed_measurement():
    source = AirspeedProgress()
    assert not source.observe(packet(1), 10.).valid
    sample = source.observe(packet(2), 10.1)
    assert sample.fresh(10.2, .5)
    assert sample.source == "sensor"
    assert source.observe(packet(2), 11.) is sample
    assert not sample.fresh(11., .5)


@pytest.mark.parametrize("bad", [None, {}, packet(True), packet(-1), packet(3, math.nan),
                                 packet(3, math.inf), packet(3, -1), packet(3, True)])
def test_missing_invalid_speed_degrades_without_manufacturing_airspeed(bad):
    source = AirspeedProgress()
    source.observe(packet(1), 10.)
    assert source.observe(packet(2), 10.1).valid
    sample = source.observe(bad, 10.2)
    assert not sample.valid
    assert sample.source == "unavailable"
    assert sample.equivalent_m_s is None


def test_reordered_or_mutated_packet_does_not_become_a_new_speed_epoch():
    source = AirspeedProgress()
    source.observe(packet(10), 10.)
    source.observe(packet(11), 10.1)
    assert not source.observe(packet(9), 10.2).valid
    assert not source.observe(packet(10), 10.3).valid
    assert not source.observe(packet(11), 10.4).valid
    assert source.observe(packet(12), 10.5).valid
    assert not source.observe(packet(12, 16.), 10.6).valid
    assert not source.observe(packet(12), 10.7).valid
    assert source.observe(packet(13), 10.8).valid


@pytest.mark.parametrize("unconstrained", [False, True])
def test_fixture_uses_single_canonical_envelope_without_altering_factory_file(unconstrained):
    path = ROOT / "configs/config_default.yaml"
    original = path.read_bytes()
    config = yaml.safe_load(original)
    before = copy.deepcopy(config)
    configure_component(config, unconstrained=unconstrained)
    assert path.read_bytes() == original
    assert config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["ENABLE_ALTITUDE_CONTROL"] is unconstrained
    assert config["Safety"]["GlobalLimits"]["ALTITUDE_SAFETY_ENABLED"]
    if unconstrained:
        assert config["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] == 3.
        assert config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"] is None
        assert "MAX_ALTITUDE" not in config["Safety"]["FollowerOverrides"].get("GM_VELOCITY_VECTOR", {})
    else:
        assert config["Safety"] == before["Safety"]


@pytest.mark.parametrize("arguments", [[], ["--target-forward-m", "nan"], ["--target-down-m", "inf"],
                                       ["--takeoff-altitude-m", "3"], ["--follower", "mc_velocity_ground"]])
def test_missing_authorization_or_invalid_fixture_never_starts_a_simulator(arguments, monkeypatch):
    from tools import sih_isolated_host

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid/dry component invocation started a simulator")

    monkeypatch.setattr(sih_isolated_host, "host", forbidden)
    monkeypatch.setattr("sys.argv", ["runner", *arguments])
    with pytest.raises(SystemExit):
        runner.main()
