"""Follower declarations and pure input/aircraft eligibility decisions.

Requirements come from follower_commands.yaml; measurement semantics and field
guarantees come from tracker_schemas.yaml. This module does not create followers,
own sessions, grant authority or publish commands.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


NATIVE_PHASE_CONTRACTS = {
    "multicopter": "velocity_body_offboard",
    "fixed_wing": "fixed_wing_external",
    "vtol_transition": "vtol_transition_external",
}
PROFILE_FAMILIES = frozenset({"multicopter", "fixed_wing", "external", "vtol"})
PROFILE_VISIBILITIES = frozenset({"basic", "advanced", "experimental"})
OBSERVATION_REPRESENTATIONS = frozenset({"image_position", "angular_bearing", "provider_angles", "external"})


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class FollowerProfile:
    mode: str
    display_name: str
    description: str
    family: str
    config_section: str
    visibility: str
    control_type: str
    airframe_phase: str
    required_fields: tuple[str, ...]
    required_tracker_data: tuple[str, ...]
    native_phase_contracts: tuple[tuple[str, str], ...]
    implementation_available: bool

    @classmethod
    def from_info(cls, mode: str, info: Mapping) -> FollowerProfile:
        family = info.get("family")
        visibility = info.get("visibility")
        if family not in PROFILE_FAMILIES or visibility not in PROFILE_VISIBILITIES:
            raise ValueError("follower_catalog_metadata_invalid")
        return cls(
            mode=mode, display_name=info["display_name"], description=info["description"],
            family=family, visibility=visibility, config_section=info["config_section"], control_type=info["control_type"],
            airframe_phase=info["airframe_phase"], required_fields=tuple(info["required_fields"]),
            required_tracker_data=tuple(info["required_tracker_data"]),
            native_phase_contracts=tuple(info.get("native_phase_contracts", {}).items()),
            implementation_available=info.get("implementation_available") is True,
        )

    @property
    def phase_command_contracts(self) -> dict[str, str]:
        return {self.airframe_phase: self.control_type, **dict(self.native_phase_contracts)}

    @property
    def live_eligibility(self) -> Eligibility:
        if not self.implementation_available:
            return Eligibility(False, "follower_implementation_unavailable")
        # Preserve the existing live gate for non-native FW/rate implementations.
        if (self.airframe_phase in {"fixed_wing", "vtol_transition"}
                and self.airframe_phase not in dict(self.native_phase_contracts)):
            return Eligibility(False, "profile_not_live_qualified")
        return Eligibility(True)


def get_follower_profile(mode: str) -> FollowerProfile:
    from classes.follower import FollowerFactory

    return FollowerProfile.from_info(mode, FollowerFactory.get_follower_info(mode))


def get_follower_catalog() -> tuple[FollowerProfile, ...]:
    from classes.setpoint_handler import SetpointHandler

    return tuple(get_follower_profile(mode) for mode in SetpointHandler.get_available_profiles())


def evaluate_input(profile: FollowerProfile, manager, schema_type: str, *,
                   tracker_name: str | None = None,
                   sample_fields: Mapping | None = None) -> Eligibility:
    """Check representation before fields; optional fields are not guarantees.

    A tracker may promise an additional selected-target field (SmartTracker).
    Runtime calls validate actual fields instead; an advertised promise never
    substitutes for the current observation.
    """
    if not profile.implementation_available:
        return Eligibility(False, "follower_implementation_unavailable")
    schema = manager.get_schema(schema_type)
    if not isinstance(schema, dict) or not schema.get("representation"):
        return Eligibility(False, "tracker_output_unknown")
    guaranteed = set(schema.get("required_fields", []))
    if tracker_name is not None:
        tracker = manager.get_tracker_info(tracker_name)
        if not isinstance(tracker, dict) or tracker.get("data_type") != schema_type:
            return Eligibility(False, "tracker_output_unknown")
        promised = tracker.get("following_required_fields", [])
        declared = guaranteed | set(schema.get("optional_fields", []))
        if not isinstance(promised, list) or any(field not in declared for field in promised):
            return Eligibility(False, "tracker_output_unknown")
        guaranteed.update(promised)
    for required_type in profile.required_tracker_data:
        required = manager.get_schema(required_type)
        if (not isinstance(required, dict)
                or required.get("representation") != schema["representation"]):
            return Eligibility(False, "tracker_output_incompatible")
        fields = required.get("required_fields", [])
        if not fields:
            return Eligibility(False, "tracker_output_unknown")
        if sample_fields is None:
            if not set(fields).issubset(guaranteed):
                return Eligibility(False, "tracker_required_fields_not_guaranteed")
        else:
            for field in fields:
                if field == "bbox_or_normalized_bbox":
                    present = sample_fields.get("bbox") is not None or sample_fields.get("normalized_bbox") is not None
                else:
                    present = sample_fields.get(field) is not None
                if not present:
                    return Eligibility(False, "tracker_required_fields_missing")
                value = sample_fields.get(field)
                rules = required.get("validation", {}).get(field, {})
                if rules.get("type") == "tuple":
                    if not isinstance(value, (tuple, list)) or len(value) != rules.get("length", len(value)):
                        return Eligibility(False, "tracker_required_fields_invalid")
                    if rules.get("element_type") == "float" and any(
                        isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item)
                        for item in value
                    ):
                        return Eligibility(False, "tracker_required_fields_invalid")
    return Eligibility(True)


def evaluate_aircraft(profile: FollowerProfile, aircraft_kind: str, *,
                      observed_phase: str | None = None) -> Eligibility:
    """Selection is independent; starting needs a supported observed aircraft.

    VTOL admission stays closed until transition-preserving release is qualified.
    A configuration label or declared transition command cannot grant that gate.
    """
    if aircraft_kind not in {"multicopter", "fixed_wing", "vtol"}:
        return Eligibility(False, "aircraft_kind_unavailable")
    if observed_phase == "vtol_transition":
        return Eligibility(False, "following_transition_unavailable")
    if aircraft_kind == "vtol":
        return Eligibility(False, "vtol_transition_release_unqualified")
    phase = aircraft_kind
    if observed_phase is not None and observed_phase != phase:
        return Eligibility(False, "aircraft_phase_mismatch")
    if phase not in profile.phase_command_contracts:
        return Eligibility(False, "follower_aircraft_incompatible")
    return profile.live_eligibility
