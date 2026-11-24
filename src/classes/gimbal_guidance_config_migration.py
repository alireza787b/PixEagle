"""One-time interpretation of saved, retired gimbal guidance settings.

Only Config Sync/configuration admission calls this assessor. Runtime guidance
reads canonical restrictions; historical provider masking is not a mechanics or
physical timing qualification and never grants command authority.
"""

from copy import deepcopy
from collections.abc import Mapping

from classes.gimbal_guidance import GimbalObservationLimits, VECTOR_MC_MANOEUVRES, SPECIAL_MANOEUVRES


MIGRATION_ID = "split-gimbal-guidance-capabilities-v1"
LEGACY_PATH = ["GimbalTracker", "GUIDANCE", "CAPABILITIES"]
ALLOWED_PATH = ["GimbalTracker", "GUIDANCE", "ALLOWED_MANOEUVRES"]
LIMITS_PATH = ["GimbalTracker", "GUIDANCE", "OBSERVATION_LIMITS"]
_NEW_PATHS = (ALLOWED_PATH, LIMITS_PATH)
_ABSENT = object()
_FACTORY = {"KNOWN": False, "SUPPORTS_VERTICAL": False, "SUPPORTS_REVERSE": False,
            "SUPPORTS_YAW_FALLBACK": False, "AZIMUTH_LIMITS_DEG": [-180., 180.],
            "DEPRESSION_LIMITS_DEG": [-90., 90.]}
_FLAGS = ("SUPPORTS_VERTICAL", "SUPPORTS_REVERSE", "SUPPORTS_YAW_FALLBACK")
# Frozen historical aliases: a future provider must not inherit this masking history.
_TOPOTEK_IDS = {"topotek_sip_udp", "sip_udp", "topotek", "topotek_sip"}


def _get(config, path, default=_ABSENT):
    value = config
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return value


def canonical_guidance_restrictions(config):
    """Validate only current settings; never interpret the retired object."""
    guidance = _get(config, ["GimbalTracker", "GUIDANCE"], {})
    if not isinstance(guidance, Mapping):
        raise ValueError("gimbal_guidance_configuration_invalid")
    support = VECTOR_MC_MANOEUVRES.restricted(guidance.get("ALLOWED_MANOEUVRES"))
    limits = GimbalObservationLimits.from_mapping(guidance.get("OBSERVATION_LIMITS"))
    return support, limits


def _policy(config):
    support, limits = canonical_guidance_restrictions(config)
    return {**support.to_mapping(), "observation_limits": limits.to_mapping(),
            "manoeuvre_origin": "mc_vector_implementation_intersect_operator_restriction",
            "mechanical_qualification": "unqualified"}


def _legacy_values(raw):
    if not isinstance(raw, Mapping) or set(raw) - set(_FACTORY):
        return None
    values = {**deepcopy(_FACTORY), **deepcopy(dict(raw))}
    if any(type(values[key]) is not bool for key in ("KNOWN", *_FLAGS)):
        return None
    try:
        limits = GimbalObservationLimits(values["AZIMUTH_LIMITS_DEG"], values["DEPRESSION_LIMITS_DEG"])
    except ValueError:
        return None
    return values, limits


def _intersect(left, right):
    if left is None:
        return right
    if right is None:
        return left
    result = max(left[0], right[0]), min(left[1], right[1])
    if result[0] > result[1]:
        raise ValueError("gimbal_observation_limits_disjoint")
    return result


def assess_gimbal_guidance_migration(saved_config, *, candidate=None):
    """Return a bounded, credential-free diagnostic, without mutating input."""
    raw = _get(saved_config, LEGACY_PATH)
    if raw is _ABSENT:
        return None
    candidate = saved_config if candidate is None else candidate
    provider = _get(saved_config, ["GimbalTracker", "PROVIDER"], "topotek_sip_udp")
    known_provider = isinstance(provider, str) and provider.strip().lower() in _TOPOTEK_IDS
    parsed = _legacy_values(raw)
    placeholder = False
    equivalent = False
    if parsed is not None and known_provider:
        values, bounds = parsed
        full_domain = bounds.azimuth_limits_deg in (None, (-180., 180.)) and bounds.depression_limits_deg in (None, (-90., 90.))
        placeholder = (not values["KNOWN"] and not any(values[key] for key in _FLAGS) and full_domain)
        equivalent = placeholder or (values["KNOWN"] and all(values[key] for key in _FLAGS) and full_domain)
    review = not equivalent
    before = {"origin": "legacy_topotek_provider_override" if known_provider else "legacy_provider_effective_policy_unknown",
              "special_manoeuvres": list(SPECIAL_MANOEUVRES) if known_provider else None,
              "observation_limits": {"azimuth_limits_deg": None, "depression_limits_deg": None} if known_provider else None,
              "mechanical_qualification": "unqualified",
              "note": "Normalized representability and provider masking, not physical joint reachability or exposure timing."}
    if not known_provider and parsed is not None:
        values, bounds = parsed
        before["saved_fallback"] = {"known": values["KNOWN"],
            "special_manoeuvres": [name for name, flag in zip(SPECIAL_MANOEUVRES, _FLAGS) if values["KNOWN"] and values[flag]],
            "observation_limits": bounds.to_mapping(), "runtime_verified": False}
    proposed = _policy(candidate)
    recommended_allowed = _get(candidate, ALLOWED_PATH, None)
    _, proposed_bounds = canonical_guidance_restrictions(candidate)
    recommended_bounds = proposed_bounds
    saved_restrictions = None
    recommendation_error = None
    if parsed is not None:
        values, bounds = parsed
        saved_restrictions = {"known": values["KNOWN"],
            "declared_special_manoeuvres": [name for name, flag in zip(SPECIAL_MANOEUVRES, _FLAGS) if values[flag]],
            "observation_limits": bounds.to_mapping(), "masked_by_provider": known_provider}
        try:
            recommended_bounds = GimbalObservationLimits(
                _intersect(proposed_bounds.azimuth_limits_deg,
                           None if bounds.azimuth_limits_deg == (-180., 180.) else bounds.azimuth_limits_deg),
                _intersect(proposed_bounds.depression_limits_deg,
                           None if bounds.depression_limits_deg == (-90., 90.) else bounds.depression_limits_deg))
        except ValueError as error:
            recommendation_error = str(error)
        if values["KNOWN"]:
            supported = VECTOR_MC_MANOEUVRES.restricted(recommended_allowed).to_mapping()["special_manoeuvres"]
            recommended_allowed = [name for name, flag in zip(SPECIAL_MANOEUVRES, _FLAGS)
                                   if values[flag] and name in supported]
    operations = [
        {"op_type": "ADD_NEW", "path": ALLOWED_PATH[:], "value": deepcopy(recommended_allowed)},
        {"op_type": "ADD_NEW", "path": LIMITS_PATH[:], "value": {
            "AZIMUTH_LIMITS_DEG": (list(recommended_bounds.azimuth_limits_deg)
                                   if recommended_bounds.azimuth_limits_deg is not None else None),
            "DEPRESSION_LIMITS_DEG": (list(recommended_bounds.depression_limits_deg)
                                      if recommended_bounds.depression_limits_deg is not None else None)}},
        {"op_type": "REMOVE_RETIRED", "path": LEGACY_PATH[:]},
    ]
    restriction_errors = []
    if parsed is not None:
        values, bounds = parsed
        proposed_support, _ = canonical_guidance_restrictions(candidate)
        if values["KNOWN"]:
            admitted = proposed_support.to_mapping()["special_manoeuvres"]
            if any(name in admitted and not values[flag]
                   for name, flag in zip(SPECIAL_MANOEUVRES, _FLAGS)):
                restriction_errors.append("Canonical manoeuvres widen saved restrictions")
        for axis in ("azimuth_limits_deg", "depression_limits_deg"):
            old, new = getattr(bounds, axis), getattr(proposed_bounds, axis)
            full = (-180., 180.) if axis == "azimuth_limits_deg" else (-90., 90.)
            if old is not None and old != full and (new is None or new[0] < old[0] or new[1] > old[1]):
                restriction_errors.append(f"Canonical {axis} widens saved restrictions")
    return {"id": MIGRATION_ID, "path": LEGACY_PATH[:], "affected_profile": "gm_velocity_vector",
        "review_required": review, "reason_code": "gimbal_guidance_config_review_required" if review else None,
        "classification": "factory_placeholder" if placeholder else "equivalent_effective_policy" if equivalent else "custom_review",
        "effective_before": before, "effective_after": proposed, "saved_restrictions": saved_restrictions,
        "recommended_operations": operations, "recommendation_error": recommendation_error,
        "restriction_errors": restriction_errors,
        "canonical_choices_present": (all(_get(candidate, path) is not _ABSENT for path in _NEW_PATHS)
            and isinstance(_get(candidate, LIMITS_PATH), Mapping)
            and {"AZIMUTH_LIMITS_DEG", "DEPRESSION_LIMITS_DEG"}.issubset(_get(candidate, LIMITS_PATH))),
        "legacy_removed_in_candidate": _get(candidate, LEGACY_PATH) is _ABSENT}
