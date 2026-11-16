"""Connection-bound stock guidance observations and read-only parameter setup.

The existing MAVLink poller owns all receipt/identity clocks. This adapter adds
no polling, firmware handshake, command authority or parallel parameter store.
"""

import asyncio
from dataclasses import asdict, dataclass
import hashlib
import json

from classes.aircraft_state import AircraftBinding, AirframePhase, finite_number
from classes.fixed_wing_mavlink_control import FIXED_WING_MAVLINK_PARAMETERS, resolve_mavlink_configuration
from classes.mavlink_aircraft_state import MavlinkGuidanceObservation
from classes.stock_mavlink_setpoints import PX4_OFFBOARD_MODE


@dataclass(frozen=True)
class MavlinkStartContext:
    binding: AircraftBinding
    runtime_id: str
    source_epoch: tuple[str, str]
    phase: AirframePhase
    phase_generation: int
    mode_generation: int
    flight_mode: int
    altitude_reference_generation: int
    parameter_revision: str

    def __post_init__(self):
        if (not isinstance(self.binding, AircraftBinding)
                or not isinstance(self.source_epoch, tuple) or len(self.source_epoch) != 2
                or any(not isinstance(value, str) or not value for value in (*self.source_epoch, self.runtime_id, self.parameter_revision))
                or self.source_epoch[0] != self.binding.aircraft_uid
                or not isinstance(self.phase, AirframePhase)
                or self.phase not in {AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING}
                or any(type(getattr(self, name)) is not int or getattr(self, name) < 0 for name in (
                    "phase_generation", "mode_generation", "flight_mode", "altitude_reference_generation"))
                or self.flight_mode == PX4_OFFBOARD_MODE):
            raise ValueError("mavlink_start_context_invalid")

    @property
    def context_id(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def require_match(self, binding, runtime_id, *, phase=None):
        if self.binding != binding or self.runtime_id != runtime_id or phase is not None and self.phase is not phase:
            raise ValueError("mavlink_start_context_changed")


class MavlinkGuidanceSource:
    def __init__(self, manager, binding, source_epoch, *, current_binding, envelope=None, tuning=None):
        if (not isinstance(binding, AircraftBinding) or not callable(current_binding)
                or not isinstance(source_epoch, tuple) or len(source_epoch) != 2 or source_epoch[0] != binding.aircraft_uid
                or any(not isinstance(value, str) or not value for value in source_epoch)):
            raise ValueError("mavlink_guidance_source_invalid")
        self.manager, self.binding, self.source_epoch = manager, binding, source_epoch
        self.current_binding = current_binding
        self.envelope, self.tuning = envelope, tuning
        payload = [asdict(binding), source_epoch, None if envelope is None else envelope.revision]
        self.runtime_id = "stock-mavlink:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def observation(self):
        if self.current_binding() != self.binding:
            return None
        observation = self.manager.get_guidance_observation(self.binding, source_epoch=self.source_epoch, envelope=self.envelope)
        if (not isinstance(observation, MavlinkGuidanceObservation)
                or observation.state.binding != self.binding or observation.source_epoch != self.source_epoch
                or self.envelope is not None and observation.state.fixed_wing_envelope != self.envelope
                or self.current_binding() != self.binding):
            return None
        return observation

    @property
    def start_context(self):
        observation = self.observation()
        if observation is None or observation.flight_mode == PX4_OFFBOARD_MODE:
            return None
        state = observation.state
        if state.phase not in {AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING} or state.rescue_active:
            return None
        if state.phase is AirframePhase.FIXED_WING and (self.envelope is None or self.tuning is None):
            return None
        return MavlinkStartContext(self.binding, self.runtime_id, self.source_epoch, state.phase,
            observation.phase_generation, observation.mode_generation, observation.flight_mode,
            state.altitude_reference_generation, "not_required" if self.envelope is None else self.envelope.revision)

    @classmethod
    async def prepare(cls, manager, binding, *, current_binding, parameter_client, lookahead_m, timeout_s):
        """Read the aircraft snapshot once before a session, never at flight rate."""
        if finite_number(timeout_s, "parameter_timeout") <= 0:
            raise ValueError("mavlink_parameter_timeout_invalid")
        epoch = manager.get_aircraft_state_source_epoch()
        if current_binding() != binding or epoch is None or epoch[0] != binding.aircraft_uid:
            raise ValueError("mavlink_guidance_source_changed")
        values = await asyncio.wait_for(asyncio.gather(*(
            parameter_client.get_param_float(name) for name in FIXED_WING_MAVLINK_PARAMETERS)), timeout=timeout_s)
        if current_binding() != binding or manager.get_aircraft_state_source_epoch() != epoch:
            raise ValueError("mavlink_guidance_source_changed")
        parameters = dict(zip(FIXED_WING_MAVLINK_PARAMETERS, values))
        revision = hashlib.sha256(json.dumps(parameters, sort_keys=True, allow_nan=False).encode()).hexdigest()
        envelope, tuning = resolve_mavlink_configuration(parameters, revision=revision, lookahead_m=lookahead_m)
        source = cls(manager, binding, epoch, current_binding=current_binding, envelope=envelope, tuning=tuning)
        if source.start_context is None:
            raise ValueError("mavlink_aircraft_state_unavailable")
        return source
