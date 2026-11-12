"""Phase-bound speed requests using the existing session-control value contract.

The owning follower supplies its canonical MC limits and profile step. Native
PX4 observations supply the FW envelope. Neither value changes saved settings.
"""

from __future__ import annotations

from dataclasses import replace

from classes.aircraft_state import AircraftState, AirframePhase, GuidanceSessionIdentity, finite_number
from classes.fixed_wing_vector_guidance import FixedWingVectorGuidance
from classes.follower_session_controls import SessionControl


class AirframeSessionControls:
    @classmethod
    def for_fixed_wing(cls, identity: GuidanceSessionIdentity, *, step_m_s: float):
        """Wait for measured engagement airspeed or native trim; invent no MC request."""
        return cls(identity, multicopter_startup_m_s=None, multicopter_ceiling_m_s=None, step_m_s=step_m_s)

    @classmethod
    def from_multicopter_control(cls, identity: GuidanceSessionIdentity, control: SessionControl):
        """Adopt the existing MC declaration rather than resolving its limits again."""
        if (not isinstance(control, SessionControl) or control.control_id != "requested_speed"
                or control.unit != "m/s" or control.minimum != 0.):
            raise ValueError("multicopter_speed_control_invalid")
        control.updated(control.value, control.revision)
        ceiling = finite_number(control.configured_maximum if control.configured_maximum is not None
                                else control.maximum, "multicopter_speed_ceiling")
        owner = cls(identity, multicopter_startup_m_s=min(control.value, ceiling),
                    multicopter_ceiling_m_s=ceiling, step_m_s=control.step)
        owner._requests[AirframePhase.MULTICOPTER] = control
        owner._revision = control.revision
        return owner

    def __init__(self, identity: GuidanceSessionIdentity, *, multicopter_startup_m_s: float | None,
                 multicopter_ceiling_m_s: float | None, step_m_s: float):
        step = finite_number(step_m_s, "speed_step")
        if (step <= 0 or (multicopter_startup_m_s is None) != (multicopter_ceiling_m_s is None)):
            raise ValueError("session_speed_configuration_invalid")
        startup = ceiling = None
        if multicopter_startup_m_s is not None:
            startup = finite_number(multicopter_startup_m_s, "startup_speed")
            ceiling = finite_number(multicopter_ceiling_m_s, "speed_ceiling")
            if not 0 <= startup <= ceiling or ceiling <= 0:
                raise ValueError("session_speed_configuration_invalid")
        self.identity = identity
        self._mc_ceiling = ceiling
        self._step = step
        self._requests = {} if startup is None else {AirframePhase.MULTICOPTER: SessionControl(
            "requested_speed", "3D speed", "m/s", 0., None, step, startup, configured_maximum=ceiling,
        )}
        self._phase = AirframePhase.UNKNOWN
        self._revision = 0
        self._ended = False
        self._unrestricted_verified = False
        self._envelope = None

    @property
    def current_control(self) -> SessionControl | None:
        return self._requests.get(self._phase)

    def enter_phase(self, identity: GuidanceSessionIdentity, state: AircraftState, *, now: float,
                    timeout_s: float, unrestricted_verified: bool = False) -> None:
        if self._ended:
            raise ValueError("follow_session_ended")
        if type(unrestricted_verified) is not bool:
            raise ValueError("unrestricted_capability_invalid")
        finite_number(now, "session_clock")
        if finite_number(timeout_s, "session_timeout") <= 0:
            raise ValueError("session_timeout_invalid")
        if (identity.follow_session_id != self.identity.follow_session_id
                or identity.binding != self.identity.binding or state.binding != identity.binding
                or identity != self.identity):
            raise ValueError("session_control_identity_stale")
        if not state.fresh(now, timeout_s) or state.rescue_active:
            raise ValueError("aircraft_state_unavailable")
        if self._phase is not AirframePhase.UNKNOWN:
            raise ValueError("session_control_phase_already_bound")
        retained = self._requests.get(state.phase)
        if state.phase is AirframePhase.MULTICOPTER:
            if retained is None or self._mc_ceiling is None:
                raise ValueError("session_control_phase_unavailable")
            minimum, ceiling = 0., self._mc_ceiling
            value, label = retained.value, "3D speed"
        elif state.phase is AirframePhase.FIXED_WING:
            envelope = state.fixed_wing_envelope
            if envelope is None:
                raise ValueError("fixed_wing_envelope_unavailable")
            minimum, ceiling = envelope.minimum_eas_m_s, envelope.maximum_eas_m_s
            initial, _ = FixedWingVectorGuidance.startup_speed(state, now=now, timeout_s=timeout_s)
            value, label = initial, "Airspeed"
        else:
            raise ValueError("aircraft_phase_unknown")
        self.identity, self._phase = identity, state.phase
        self._revision += 1
        override_allowed = state.phase is AirframePhase.MULTICOPTER or unrestricted_verified
        override_active = override_allowed and retained is not None and retained.override_active
        acknowledged = max(minimum, value if override_active else min(value, ceiling))
        self._requests = {state.phase: SessionControl(
            "requested_speed", label, "m/s", minimum, None if override_allowed else ceiling,
            self._step, acknowledged,
            self._revision, ceiling if override_allowed else None, override_active,
        )}
        self._unrestricted_verified = unrestricted_verified
        self._envelope = state.fixed_wing_envelope if state.phase is AirframePhase.FIXED_WING else None

    def refresh_envelope(self, state: AircraftState, *, now: float, timeout_s: float) -> bool:
        """Refresh native limits without ratcheting the acknowledged request.

        Dynamic load-dependent limits do not create edit conflicts on every
        telemetry sample. Parameter provenance changes do invalidate editors;
        every update is still validated against the current envelope. The native
        resolver handles a retained request outside its changing limits.
        """
        finite_number(now, "session_clock")
        if finite_number(timeout_s, "session_timeout") <= 0:
            raise ValueError("session_timeout_invalid")
        if (self._ended or self._phase is not AirframePhase.FIXED_WING or self.current_control is None
                or state.phase is not self._phase or state.binding != self.identity.binding
                or not state.fresh(now, timeout_s) or state.rescue_active):
            raise ValueError("session_control_context_unavailable")
        envelope = state.fixed_wing_envelope
        if envelope is None:
            raise ValueError("fixed_wing_envelope_unavailable")
        if envelope == self._envelope:
            return False
        if envelope.source != self._envelope.source or envelope.revision != self._envelope.revision:
            self._revision += 1
        self._requests[self._phase] = replace(
            self.current_control, minimum=envelope.minimum_eas_m_s,
            maximum=None if self._unrestricted_verified else envelope.maximum_eas_m_s,
            configured_maximum=envelope.maximum_eas_m_s if self._unrestricted_verified else None,
            revision=self._revision,
        )
        self._envelope = envelope
        return True

    def validate_update(self, value: float | None, *, identity: GuidanceSessionIdentity,
                        expected_revision: int, recovering: bool = False) -> SessionControl:
        if self._ended or identity != self.identity:
            raise ValueError("session_control_identity_stale")
        control = self.current_control
        if control is None:
            raise ValueError("session_control_phase_unavailable")
        updated = control.updated(value, expected_revision)
        if recovering and updated.value > control.value:
            raise ValueError("session_control_increase_unavailable_during_recovery")
        return updated

    def update(self, value: float | None, *, identity: GuidanceSessionIdentity,
               expected_revision: int, recovering: bool = False) -> SessionControl:
        updated = self.validate_update(value, identity=identity, expected_revision=expected_revision, recovering=recovering)
        self._requests[self._phase] = updated
        self._revision = updated.revision
        return updated

    def snapshot(self, *, client_contract_version: int) -> dict | None:
        # A client that only understands MC 3D speed must never label FW EAS as
        # translation magnitude, even though both happen to use m/s.
        control = self.current_control
        if self._ended or control is None or type(client_contract_version) is not int or client_contract_version < 2:
            return None
        return control.snapshot() | {
            "guidance_generation": self.identity.guidance_generation,
            "aircraft_phase": self._phase.value,
            "speed_basis": "equivalent_airspeed" if self._phase is AirframePhase.FIXED_WING else "translation_3d",
        }

    def end(self) -> None:
        self._ended = True
        self._requests.clear()
