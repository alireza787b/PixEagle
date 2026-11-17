"""No SDK resend, stale authority, overlapping release or fabricated receipt."""

from dataclasses import replace
import asyncio
import json

import pytest

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Vector3
from classes.airframe_session_controls import AirframeSessionControls
from classes.command_dispatch_guard import DispatchRefused
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy
from classes.fixed_wing_mavlink_control import FixedWingMavlinkVectorControl
from classes.gimbal_guidance import GimbalGuidancePolicy
from classes.mavlink_aircraft_state import MavlinkGuidanceObservation
from classes.mavlink_command_transport import MavlinkCommandTransport
from classes.mavlink_vector_guidance_session import MavlinkGuidanceCapabilities, MavlinkVectorGuidanceSession
from classes.safety_types import AltitudeLimits
from classes.stock_mavlink_setpoints import PX4_HOLD_MODE, PX4_OFFBOARD_MODE
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_fixed_wing_mavlink_control import tuning


class Bench:
    def __init__(self, *, mc=False):
        self.now, self.sequence = 100., 0
        self.mode = PX4_HOLD_MODE
        self.phase = AirframePhase.MULTICOPTER if mc else AirframePhase.FIXED_WING
        self.current, self.breaker, self.fresh, self.armed, self.target = True, False, True, True, True
        self.epoch = ("aircraft-a", "rest-1")
        self.route = (1, 1)
        self.mode_time = self.now
        self.mode_response = True
        self.after_send = None
        self.sent = []
        state = aircraft_state(phase=self.phase)
        identity = GuidanceSessionIdentity("session-a", state.binding, 0)
        policy = FixedWingGuidancePolicy()
        geometry = GimbalGuidancePolicy().geometry
        self.guidance = MavlinkVectorGuidanceSession(identity,
            MavlinkGuidanceCapabilities("stock-a", True, True, True, False),
            projection=FixedWingMavlinkVectorControl(tuning=tuning(), geometry=geometry,
                policy=policy, enable_altitude_control=not mc),
            profile_name="gm_velocity_vector",
            controls=AirframeSessionControls(identity, multicopter_startup_m_s=0., multicopter_ceiling_m_s=6., step_m_s=.5),
            supported_phases=frozenset({AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING}),
            geometry_policy=geometry, altitude_control=not mc, altitude_limits=AltitudeLimits(3., 120., 2.),
            confirmation_s=.1, observation_timeout_s=.5, clock=lambda: self.now,
            fixed_wing_policy=policy, initial_phase=self.phase)
        self.transport = MavlinkCommandTransport(self.guidance, observe=self.observe, send=self.send,
            owns_session=lambda: self.current, target_confirmed=lambda: self.target, circuit_breaker=lambda: self.breaker,
            command_period_s=.05, prime_duration_s=.1, command_timeout_s=.3, clock=lambda: self.now, sleep=self.sleep)

    def observe(self):
        if not self.fresh:
            return None
        self.sequence += 1
        return MavlinkGuidanceObservation(aircraft_state(sequence=self.sequence,
            observed_at_monotonic_s=self.now, phase=self.phase, is_vtol=self.phase is AirframePhase.VTOL_TRANSITION), self.epoch, *self.route,
            self.armed, self.mode, self.mode_time, Vector3(0., 0., -50.))

    async def send(self, packet):
        self.sent.append(packet)
        if packet.message_name == "COMMAND_LONG" and self.mode_response:
            self.mode = PX4_OFFBOARD_MODE if json.loads(packet.fields_json)["param2"] == 6. else PX4_HOLD_MODE
            self.mode_time = self.now
        if self.after_send is not None:
            await self.after_send(packet)

    async def sleep(self, delay):
        self.now += delay
        self.mode_time = self.now

    async def engage(self):
        await self.transport.engage(before_dispatch=lambda: None)
        await self.sleep(.15)
        self.transport.ready()

    def intent(self):
        return self.guidance.calculate_ned(Vector3(1., 0., 0.), frame="ned")

    def mode_packets(self):
        return [json.loads(packet.fields_json) for packet in self.sent if packet.message_name == "COMMAND_LONG"]


@pytest.mark.asyncio
async def test_start_requires_observed_mode_and_only_the_existing_scheduler_refreshes_commands():
    bench = Bench()
    await bench.engage()
    assert bench.transport.ready()
    assert bench.guidance.controls.current_control.value == 20.  # Engagement airspeed, not MC zero or trim.
    assert len(bench.mode_packets()) == 1
    count = len(bench.sent)
    for _ in range(10):
        await bench.sleep(.05)
    assert len(bench.sent) == count  # No detached SDK/background sender.
    intent = bench.transport.accept_intent(bench.intent())
    assert await bench.transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert bench.transport.published_intent(ttl_s=.5) == intent
    assert bench.transport.observed_publications is None


@pytest.mark.asyncio
async def test_stop_and_duplicate_stop_send_one_hold_and_confirm_fresh_telemetry():
    bench = Bench()
    await bench.engage()
    result = await bench.transport.stop("operator_stop")
    assert result["executed"] and result["local_sender_quiesced"]
    assert bench.guidance.controls.current_control is None
    assert await bench.transport.stop("operator_stop") == result
    assert [item["param2"] for item in bench.mode_packets()] == [6., 4.]
    assert not bench.transport.ready()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pilot", "transition", "disarm"])
async def test_takeover_transition_or_disarm_cannot_be_replaced_by_a_delayed_hold(change):
    bench = Bench()
    await bench.engage()
    if change == "pilot":
        bench.mode = 5 << 16  # Position is owned by the pilot.
    elif change == "transition":
        bench.phase = AirframePhase.VTOL_TRANSITION
    else:
        bench.armed = False
    assert not bench.transport.ready()
    result = await bench.transport.stop("cleanup")
    assert not result["executed"]
    assert result["authority_released"] is (change != "transition")
    assert len(bench.mode_packets()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["replacement", "reconnect", "route", "stale", "unknown_arm"])
async def test_uncertain_or_replaced_authority_sends_no_cleanup_mode_request(change):
    bench = Bench()
    await bench.engage()
    if change == "replacement":
        bench.current = False
    elif change == "reconnect":
        bench.epoch = ("aircraft-a", "rest-2")
    elif change == "route":
        bench.route = (42, 1)
    elif change == "unknown_arm":
        bench.armed = None
    else:
        bench.fresh = False
    with pytest.raises((DispatchRefused, ValueError)):
        await bench.transport.stop("cleanup")
    assert len(bench.mode_packets()) == 1


@pytest.mark.asyncio
async def test_missing_mode_confirmation_sends_one_request_and_never_retries_after_timeout():
    bench = Bench()
    bench.mode_response = False
    with pytest.raises(DispatchRefused, match="confirmation_timeout"):
        await bench.engage()
    assert len(bench.mode_packets()) == 1
    assert not bench.transport.ready()
    # Original Hold is still authoritative, so failed acquisition cleanup is read-only.
    assert not (await bench.transport.stop("start_failed"))["executed"]
    assert len(bench.mode_packets()) == 1


@pytest.mark.asyncio
async def test_hold_timeout_cannot_later_retry_into_a_new_flight_mode():
    bench = Bench()
    await bench.engage()
    bench.mode_response = False
    with pytest.raises(ValueError, match="hold_confirmation_timeout"):
        await bench.transport.stop("operator_stop")
    bench.mode = 5 << 16
    with pytest.raises(ValueError, match="already_attempted"):
        await bench.transport.stop("late_cleanup")
    assert len(bench.mode_packets()) == 2


@pytest.mark.asyncio
async def test_session_change_during_priming_rpc_cannot_dispatch_an_offboard_request():
    bench = Bench()
    async def replace_owner(_):
        bench.current = False
    bench.after_send = replace_owner
    with pytest.raises(DispatchRefused):
        await bench.engage()
    assert not bench.mode_packets()


@pytest.mark.asyncio
async def test_superseded_or_expired_intents_never_reach_the_wire():
    bench = Bench()
    await bench.engage()
    intent = bench.intent()
    count = len(bench.sent)
    with pytest.raises(DispatchRefused, match="expired"):
        await bench.transport.publish(replace(intent, created_at_monotonic_s=bench.now - 1.), reason="heartbeat", ttl_s=.5)
    assert len(bench.sent) == count
    assert bench.transport.last_published_intent is None


@pytest.mark.asyncio
async def test_pending_rpc_is_joined_before_hold_and_cannot_restore_old_command_intent():
    bench = Bench()
    await bench.engage()
    entered, release = asyncio.Event(), asyncio.Event()
    async def block(packet):
        if packet.message_name == "SET_ATTITUDE_TARGET":
            entered.set()
            await release.wait()
    bench.after_send = block
    publication = asyncio.create_task(bench.transport.publish(bench.intent(), reason="heartbeat", ttl_s=.5))
    await asyncio.wait_for(entered.wait(), timeout=1.)
    stop = asyncio.create_task(bench.transport.stop("operator_stop"))
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(DispatchRefused):
        await publication
    assert (await stop)["executed"]
    assert bench.sent[-1].message_name == "COMMAND_LONG"
    assert bench.transport.last_published_intent is None


@pytest.mark.asyncio
async def test_mc_priming_and_confirmed_baseline_hold_engagement_altitude():
    bench = Bench(mc=True)
    baseline = await bench.transport.engage(before_dispatch=lambda: None)
    assert await bench.transport.publish(baseline, reason="startup", ttl_s=.5)
    packets = [json.loads(packet.fields_json) for packet in bench.sent if packet.message_name == "SET_POSITION_TARGET_LOCAL_NED"]
    assert packets and all(packet["type_mask"] == 1507 and packet["z"] == -50. for packet in packets)
