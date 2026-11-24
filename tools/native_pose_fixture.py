"""Shared retained native pose validation for explicitly simulated observations."""

from dataclasses import asdict, dataclass
from typing import Callable

from classes.aircraft_state import AircraftState, Quaternion, finite_number
from classes.observation_alignment import AlignmentBinding


@dataclass(frozen=True)
class NativeProjectionFrame:
    identity: tuple[int, int]
    position_ned: tuple[float, float, float]
    quaternion_wxyz: tuple[float, float, float, float]
    received_at_monotonic_s: float
    aircraft_state: AircraftState
    target_ned: tuple[float, float, float]
    timestamp_s: float


class NativePoseFixture:
    """One simulation binding; reads never create pose progress or new receipts."""

    def __init__(self, *, binding: AlignmentBinding, clock: Callable[[], float],
                 max_observation_age_s: float, max_attitude_age_s: float, allow_simulation: bool = False):
        if type(allow_simulation) is not bool or not allow_simulation:
            raise ValueError('sih_projection_fixture_not_enabled')
        if not isinstance(binding, AlignmentBinding) or not callable(clock):
            raise ValueError('sih_projection_fixture_contract_invalid')
        for value in (max_observation_age_s, max_attitude_age_s):
            if finite_number(value, 'sih_projection_age_limit') <= 0:
                raise ValueError('sih_projection_age_limit_not_positive')
        self.binding, self.clock = binding, clock
        self.observation_age, self.attitude_age = max_observation_age_s, max_attitude_age_s
        self.frame: NativeProjectionFrame | None = None
        self._observed_identity = self._observed_values = None
        self.invalidated = False

    def now(self):
        if self.invalidated:
            raise ValueError('sih_projection_owner_invalidated')
        return finite_number(self.clock(), 'sih_projection_clock')

    def require_state(self, state, now):
        if (not isinstance(state, AircraftState) or state.binding != self.binding.aircraft_binding
                or state.attitude_timing is None
                or state.attitude_timing.quat_reset_counter != self.binding.quat_reset_counter):
            self.invalidated = True
            raise ValueError('sih_projection_aircraft_binding_changed')
        if self.frame is not None and state.source != self.frame.aircraft_state.source:
            self.invalidated = True
            raise ValueError('sih_projection_aircraft_source_changed')
        if not state.fresh(now, self.attitude_age) or not state.attitude_timing.fresh(now, self.attitude_age):
            raise ValueError('sih_projection_attitude_stale')

    def _decode_pose(self, packet, state, now):
        self.require_state(state, now)
        if not isinstance(packet, dict) or packet.get('runtime_id') != self.binding.native_runtime_id:
            raise ValueError('sih_projection_native_packet_invalid')
        if packet.get('fresh') is False:
            raise ValueError('sih_projection_native_state_unavailable')
        if packet.get('fresh') is not True:
            raise ValueError('sih_projection_native_packet_invalid')
        payload = packet.get('aircraft_state')
        if not isinstance(payload, dict) or packet.get('attitude_timing') != asdict(state.attitude_timing):
            raise ValueError('sih_projection_native_state_mismatch')
        decoded = dict(payload)
        if decoded.get('attitude_timing') is None:
            decoded['attitude_timing'] = packet['attitude_timing']
        if AircraftState.from_payload(decoded) != state:
            raise ValueError('sih_projection_native_state_mismatch')
        pose = packet.get('vehicle_pose')
        if not isinstance(pose, dict) or pose.get('source') != 'px4_dds_observed':
            raise ValueError('sih_projection_pose_unavailable')
        received = finite_number(pose.get('observed_at_monotonic_s'), 'sih_pose_receipt')
        if received < 0 or not 0 <= now-received <= min(self.observation_age, self.attitude_age):
            raise ValueError('sih_projection_pose_stale')
        position, raw_q = pose.get('vehicle_ned'), pose.get('quaternion_wxyz')
        if (not isinstance(position, (list, tuple)) or len(position) != 3
                or not isinstance(raw_q, (list, tuple)) or len(raw_q) != 4):
            raise ValueError('sih_projection_pose_invalid')
        position = tuple(finite_number(value, 'sih_pose_position') for value in position)
        if Quaternion(*raw_q) != state.attitude_body_to_ned:
            raise ValueError('sih_projection_physical_quaternion_mismatch')
        timestamp = pose.get('px4_timestamp_us')
        if type(timestamp) is not int or not 0 < timestamp < 2**64:
            raise ValueError('sih_projection_pose_timestamp_invalid')
        return (timestamp, state.attitude_timing.sample_timestamp_us), (position, tuple(raw_q)), received

    def project(self, packet, state, target_ned, *, timestamp_s) -> tuple[NativeProjectionFrame, bool]:
        now = self.now()
        if finite_number(timestamp_s, 'sih_projection_display_epoch') <= 0:
            raise ValueError('sih_projection_display_epoch_invalid')
        if not isinstance(target_ned, tuple) or len(target_ned) != 3:
            raise ValueError('sih_projection_target_invalid')
        target = tuple(finite_number(value, 'sih_target_ned') for value in target_ned)
        try:
            identity, values, receipt = self._decode_pose(packet, state, now)
        except (ValueError, TypeError, KeyError) as error:
            if str(error) not in {'sih_projection_attitude_stale', 'sih_projection_pose_stale',
                                  'sih_projection_native_state_unavailable'}:
                self.invalidated = True
            raise
        if self._observed_identity is not None:
            if any(current < before for current, before in zip(identity, self._observed_identity)):
                self.invalidated = True
                raise ValueError('sih_projection_pose_reordered')
            if any(current == before and value != old for current, before, value, old in
                   zip(identity, self._observed_identity, values, self._observed_values)):
                self.invalidated = True
                raise ValueError('sih_projection_pose_rewritten')
        self._observed_identity, self._observed_values = identity, values
        if self.frame is not None and not all(current > before for current, before in zip(identity, self.frame.identity)):
            return self.retained_frame(state), False
        self.frame = NativeProjectionFrame(identity, *values, receipt, state, target, timestamp_s)
        return self.frame, True

    def retained_frame(self, current_state) -> NativeProjectionFrame:
        now = self.now()
        self.require_state(current_state, now)
        if self.frame is None:
            raise ValueError('sih_projection_output_unavailable_or_changed')
        self.require_state(self.frame.aircraft_state, now)
        if not 0 <= now-self.frame.received_at_monotonic_s <= self.observation_age:
            raise ValueError('sih_projection_frame_stale')
        return self.frame
