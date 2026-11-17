"""Stable start contexts and connection-owned aircraft parameter derivation."""

from dataclasses import replace
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from classes.aircraft_state import AirframePhase
from classes.fixed_wing_mavlink_control import FIXED_WING_MAVLINK_PARAMETERS, resolve_mavlink_configuration
from classes.mavlink_guidance_source import MavlinkGuidanceSource
from classes.stock_mavlink_setpoints import PX4_OFFBOARD_MODE
from tests.unit.drone_interface.test_mavlink_command_transport import Bench


def parameters():
    return dict(zip(FIXED_WING_MAVLINK_PARAMETERS,
        [12., 18., 30., .1, .6, 1., -30., 30., 35., 4., 5., 2., 5.]))


def source_fixture():
    bench = Bench()
    def observe(*args, **kwargs):
        observation = bench.observe()
        return None if observation is None else replace(observation,
            state=replace(observation.state, fixed_wing_envelope=kwargs.get("envelope")))
    manager = SimpleNamespace(get_aircraft_state_source_epoch=lambda: bench.epoch, get_guidance_observation=observe)
    binding = bench.guidance.identity.binding
    envelope, tuning = resolve_mavlink_configuration(parameters(), revision="parameters-a", lookahead_m=50.)
    source = MavlinkGuidanceSource(manager, binding, bench.epoch,
        current_binding=lambda: binding if bench.current else None, envelope=envelope, tuning=tuning)
    return source, bench


def test_start_context_is_stable_across_pose_and_heartbeat_progress_not_a_per_poll_nonce():
    source, bench = source_fixture()
    original = source.start_context
    bench.now += .1
    bench.mode_time = bench.now
    current = source.start_context
    assert current == original and current.context_id == original.context_id
    assert not hasattr(current, "firmware_incarnation")
    assert not hasattr(current, "registration_id")
    assert current.runtime_id.startswith("stock-mavlink:")


@pytest.mark.parametrize("change", ["mode", "phase", "home"])
def test_start_context_invalidates_on_authority_or_geometry_reference_generation(change):
    source, bench = source_fixture()
    original = source.start_context
    observation = source.observation()
    if change == "mode":
        observation = replace(observation, mode_generation=1)
    elif change == "phase":
        observation = replace(observation, phase_generation=1)
    else:
        observation = replace(observation, state=replace(observation.state, altitude_reference_generation=1))
    source.manager.get_guidance_observation = lambda *args, **kwargs: observation
    assert source.start_context.context_id != original.context_id


@pytest.mark.parametrize("change", ["connection", "source", "transition", "offboard", "missing"])
def test_passive_context_cannot_grant_unknown_or_already_owned_control(change):
    source, bench = source_fixture()
    if change == "connection":
        bench.current = False
    elif change == "source":
        bench.epoch = ("aircraft-a", "rest-2")
    elif change == "transition":
        bench.phase = AirframePhase.VTOL_TRANSITION
    elif change == "offboard":
        bench.mode = PX4_OFFBOARD_MODE
    else:
        bench.fresh = False
    assert source.start_context is None


def test_same_aircraft_parameters_resolve_envelope_tuning_and_explicit_provenance_together():
    envelope, tuning = resolve_mavlink_configuration(parameters(), revision="parameters-a", lookahead_m=50.)
    assert envelope.minimum_eas_m_s == 12. and envelope.maximum_eas_m_s == 30.
    assert envelope.source == "stock_px4_parameter_snapshot"
    assert envelope.revision == "parameters-a"
    assert tuning.speed_gain_per_m_s == 1. / envelope.trim_eas_m_s
    assert tuning.pitch_min_rad == math.radians(-30)


@pytest.mark.parametrize("bad", [None, True, math.inf, math.nan, -1.])
def test_invalid_aircraft_speed_limits_are_not_replaced_by_a_configured_or_groundspeed_guess(bad):
    values = parameters() | {"FW_AIRSPD_MIN": bad}
    with pytest.raises(ValueError):
        resolve_mavlink_configuration(values, revision="parameters-a", lookahead_m=50.)


def test_missing_parameter_is_not_another_hidden_airframe_default():
    values = parameters()
    del values["FW_R_LIM"]
    with pytest.raises(ValueError, match="parameters_incomplete"):
        resolve_mavlink_configuration(values, revision="parameters-a", lookahead_m=50.)


@pytest.mark.asyncio
async def test_setup_reads_known_parameters_once_without_writing_or_creating_a_poller():
    source, _ = source_fixture()
    async def get(name):
        return parameters()[name]
    client = SimpleNamespace(get_param_float=AsyncMock(side_effect=get))
    prepared = await MavlinkGuidanceSource.prepare(source.manager, source.binding,
        current_binding=source.current_binding, parameter_client=client, lookahead_m=50., timeout_s=1.)
    assert client.get_param_float.await_count == len(FIXED_WING_MAVLINK_PARAMETERS)
    assert prepared.envelope.minimum_eas_m_s == 12.
    assert prepared.start_context.parameter_revision == prepared.envelope.revision
    prepared.observation()
    prepared.observation()
    assert client.get_param_float.await_count == len(FIXED_WING_MAVLINK_PARAMETERS)


@pytest.mark.asyncio
async def test_reconnect_during_read_only_parameter_collection_discards_the_whole_snapshot():
    source, bench = source_fixture()
    async def get(name):
        bench.current = False
        return parameters()[name]
    with pytest.raises(ValueError, match="source_changed"):
        await MavlinkGuidanceSource.prepare(source.manager, source.binding, current_binding=source.current_binding,
            parameter_client=SimpleNamespace(get_param_float=get), lookahead_m=50., timeout_s=1.)
