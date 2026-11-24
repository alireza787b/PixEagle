"""Calibrated image pursuit through the shared native PX4 FW strategy.

This experimental profile is registered but not live-qualified. The flight owner supplies
one read-only input resolver and owns publication, continuity and teardown.
"""

from collections.abc import Callable
import inspect
import logging

from classes.aircraft_state import AircraftState, AirframePhase
from classes.airframe_session_controls import AirframeSessionControls
from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.follower_config_manager import get_follower_config_manager
from classes.followers.base_follower import BaseFollower
from classes.guidance_observation import ImageMeasurement
from classes.guidance_phase_session import PhaseSessionState
from classes.observation_alignment import (
    AlignedBearing, bearing_intent_requires_update, require_current_bearing_association,
)
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerOutput
from classes.tracker_runtime_status import evaluate_tracker_command_freshness
from classes.vector_guidance_session import VectorGuidanceSession


GuidanceInputResolver = Callable[[TrackerOutput, AircraftState], AlignedBearing]
logger = logging.getLogger(__name__)


class FWNavigationChaseFollower(BaseFollower):
    """Produce course/EAS/vertical intent, with no MC or local TECS fallback."""

    def __init__(
        self, px4_controller, initial_target_coords, *, geometry_policy: BearingGeometryPolicy | None = None,
        input_resolver: GuidanceInputResolver | None = None, profile_name: str = "fw_navigation_chase",
    ):
        if geometry_policy is None:
            section = SetpointHandler.get_profile_info(profile_name)["config_section"]
            geometry_policy = BearingGeometryPolicy.from_mapping(getattr(Parameters, section, None))
        if not isinstance(geometry_policy, BearingGeometryPolicy):
            raise ValueError("bearing_geometry_policy_invalid")
        if input_resolver is not None and (not callable(input_resolver) or inspect.iscoroutinefunction(input_resolver)):
            raise ValueError("guidance_input_resolver_invalid")
        self._airframe_session = None
        self._airframe_session_bound = False
        self._ended = False
        self._input_resolver = input_resolver
        self._last_guidance_input = None
        self._last_image_measurement = None
        self._last_guidance_intent = None
        self._last_guidance_state = None
        self._last_control_revision = None
        self.geometry_policy = geometry_policy
        super().__init__(px4_controller, profile_name)
        if (self.setpoint_handler.get_transport() != "px4_native"
                or self.get_control_type() != "fixed_wing_external"
                or self.get_airframe_phase() != AirframePhase.FIXED_WING.value):
            raise ValueError("native_fixed_wing_profile_required")
        operational = get_follower_config_manager()
        self.enable_altitude_control = operational.get_param("ENABLE_ALTITUDE_CONTROL", self._follower_config_name)
        self.update_rate = operational.get_param("CONTROL_UPDATE_RATE", self._follower_config_name)
        self._session_controls = {}
        self.reset_command_history()

    def bind_guidance_input_resolver(self, resolver: GuidanceInputResolver) -> None:
        """Bind before preparation; replacing an active source needs a new owner."""
        if not callable(resolver) or inspect.iscoroutinefunction(resolver):
            raise ValueError("guidance_input_resolver_invalid")
        if self._airframe_session is not None or self._ended:
            raise ValueError("guidance_input_resolver_already_bound")
        self._input_resolver = resolver

    def create_airframe_session(self, identity, capabilities, *, session_factory=None, **policy):
        if self._airframe_session is not None or self._ended:
            raise ValueError("airframe_session_already_bound")
        declaration = self.setpoint_handler.profile_config.get("session_controls", {}).get("requested_speed")
        if not isinstance(declaration, dict) or declaration.get("unit") != "m/s":
            raise ValueError("native_speed_control_declaration_missing")
        factory = VectorGuidanceSession if session_factory is None else session_factory
        session = factory(
            identity, capabilities, profile_name=self.profile_name,
            controls=AirframeSessionControls.for_fixed_wing(identity, step_m_s=declaration["step"]),
            supported_phases=frozenset({AirframePhase.FIXED_WING}),
            geometry_policy=self.geometry_policy, altitude_control=self.enable_altitude_control,
            altitude_limits=self.altitude_limits, **policy,
        )
        # Preparation retains discovery identity, but grants no command authority.
        self._airframe_session = session
        return session

    def bind_airframe_session(self, session) -> None:
        if (self._ended or self._airframe_session_bound or session is not self._airframe_session
                or not isinstance(session, VectorGuidanceSession)):
            raise ValueError("airframe_session_binding_invalid")
        state = session.require_state()
        if state.phase is not AirframePhase.FIXED_WING:
            raise ValueError("fixed_wing_phase_required")
        self._airframe_session_bound = True

    def _require_session(self, *, bound: bool = False) -> VectorGuidanceSession:
        if self._ended:
            raise ValueError("follow_session_ended")
        session = self._airframe_session
        if session is None or bound and not self._airframe_session_bound:
            raise ValueError("native_guidance_session_unprepared")
        if session.phase_owner.state is PhaseSessionState.ENDED:
            raise ValueError("guidance_session_ended")
        return session

    def _resolve_guidance_input(
        self, tracker_output: TrackerOutput | None, aircraft_state: AircraftState | None,
    ) -> AlignedBearing:
        session = self._require_session()
        if not isinstance(aircraft_state, AircraftState):
            raise ValueError("native_aircraft_state_unavailable")
        if (aircraft_state.phase is not AirframePhase.FIXED_WING
                or aircraft_state.binding != session.identity.binding):
            raise ValueError("guidance_aircraft_binding_changed")
        if not aircraft_state.fresh(session.clock(), session.phase_owner.observation_timeout_s):
            raise ValueError("aircraft_state_stale")
        if (not isinstance(tracker_output, TrackerOutput)
                or not self.validate_tracker_compatibility(tracker_output)):
            raise ValueError("tracker_output_incompatible")
        freshness = evaluate_tracker_command_freshness(tracker_output)
        if not freshness["usable_for_following"]:
            raise ValueError(freshness["reason_code"])
        measurement = tracker_output.image_measurement
        if not isinstance(measurement, ImageMeasurement) or not measurement.measured:
            raise ValueError("image_measurement_unavailable")
        if not callable(self._input_resolver):
            raise ValueError("physical_capture_timing_unqualified")
        aligned = self._input_resolver(tracker_output, aircraft_state)
        if not isinstance(aligned, AlignedBearing):
            if inspect.iscoroutine(aligned):
                aligned.close()
            raise ValueError("guidance_input_resolver_contract_invalid")
        # A resolver must revalidate timing on every read; a retained typed result
        # cannot bypass the owner's ordinary receipt/sample freshness contract.
        timeout = session.phase_owner.observation_timeout_s
        require_current_bearing_association(aligned, measurement.provenance, aircraft_state,
            native_runtime_id=session.phase_owner.capabilities.runtime_id, now_monotonic_s=session.clock(),
            max_observation_age_s=timeout, max_attitude_age_s=timeout)
        return aligned

    def require_guidance_input(
        self, tracker_output: TrackerOutput | None, aircraft_state: AircraftState | None,
    ) -> None:
        self._resolve_guidance_input(tracker_output, aircraft_state)

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        session = self._require_session(bound=True)
        state = session.require_state()
        aligned = self._resolve_guidance_input(tracker_data, state)
        previous = self._last_guidance_input
        duplicate = (previous is not None
                     and (aligned.binding.source_id, aligned.binding.source_epoch,
                          aligned.bearing.provenance.capture.capture_id)
                     == (previous.binding.source_id, previous.binding.source_epoch,
                         previous.bearing.provenance.capture.capture_id))
        if duplicate and (aligned != previous or tracker_data.image_measurement != self._last_image_measurement):
            raise ValueError("guidance_capture_rewritten")
        revision = session.controls.current_control.revision
        if not bearing_intent_requires_update(aligned, previous, state, self._last_guidance_state,
                                             revision, self._last_control_revision):
            self._last_command_intent = self.setpoint_handler.set_native_intent(self._last_guidance_intent)
            return
        # Real source progress updates native constraints against the retained
        # world bearing; polling renews neither aircraft nor image evidence.
        intent = session.calculate_ned(aligned.direction_ned, frame="ned")
        if intent.guidance_identity != session.identity:
            raise ValueError("native_intent_identity_changed")
        self._last_command_intent = self.setpoint_handler.set_native_intent(intent)
        self._last_guidance_input = aligned
        self._last_image_measurement = tracker_data.image_measurement
        self._last_guidance_intent = self._last_command_intent
        self._last_guidance_state = state
        self._last_control_revision = revision
        self.update_telemetry_metadata("guidance_input_reason", None)
        self.update_telemetry_metadata("guidance_input_association", aligned.association_kind)

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        try:
            self.calculate_control_commands(tracker_data)
            return True
        except ValueError as error:
            reason = str(error)
        except Exception:
            logger.exception("Native image guidance calculation failed")
            reason = "guidance_calculation_failed"
        self._invalidate_command_intent(reason)
        self.update_telemetry_metadata("guidance_input_reason", reason)
        return False

    def prepare_authorized_command(self, fields: dict, *, loss_decay: bool) -> dict:
        return self._require_session(bound=True).guard_native_fields(dict(fields))

    def session_controls(self) -> list:
        if not self._airframe_session_bound or self._ended:
            return []
        control = self._airframe_session.controls.snapshot(client_contract_version=2)
        return [] if control is None else [control]

    def validate_session_control(self, control_id, value, revision) -> None:
        if control_id != "requested_speed":
            raise ValueError("session_control_unsupported")
        session = self._require_session(bound=True)
        session.require_state()
        session.controls.validate_update(value, identity=session.identity, expected_revision=revision)

    def update_session_control(self, control_id, value, revision) -> None:
        self.validate_session_control(control_id, value, revision)
        session = self._require_session(bound=True)
        session.controls.update(value, identity=session.identity, expected_revision=revision)

    def reset_target_state(self, reason: str) -> bool:
        session = self._require_session(bound=True)
        session.reset_target_state()
        self._clear_target_input()
        return True

    def _clear_target_input(self) -> None:
        self._last_guidance_input = None
        self._last_image_measurement = None
        self._last_guidance_intent = None
        self._last_guidance_state = None
        self._last_control_revision = None

    def release_session_controls(self) -> None:
        session = self._airframe_session
        if session is not None:
            session.end("follow_session_ended")
        self._airframe_session_bound = False
        self._ended = True
        self._input_resolver = None
        self._clear_target_input()
        self._invalidate_command_intent("follow_session_ended")
