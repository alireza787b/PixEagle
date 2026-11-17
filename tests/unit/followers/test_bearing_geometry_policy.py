"""FW geometry consumes thresholds without adopting an MC/gimbal manoeuvre law."""

from dataclasses import replace

import pytest

from classes.bearing_geometry_policy import BearingGeometryPolicy
from classes.fixed_wing_vector_guidance import FixedWingVectorGuidance
from classes.gimbal_guidance import GimbalGuidancePolicy


def test_gimbal_thresholds_are_shared_without_reverse_or_yaw_timers():
    configured = GimbalGuidancePolicy(
        policy='forward_only', vertical_enter_horizontal_norm=.1, vertical_exit_horizontal_norm=.4,
        rearward_entry_bearing_deg=110., forward_reentry_bearing_deg=70.,
        transition_dwell_ms=900., rearward_grace_ms=1200.,
    )
    assert configured.geometry == BearingGeometryPolicy(.1, .4, 110., 70.)
    planner = FixedWingVectorGuidance(enable_altitude_control=False, geometry_policy=configured.geometry)
    assert planner.geometry_policy is not configured
    assert not hasattr(planner.geometry_policy, 'rearward_grace_ms')


@pytest.mark.parametrize('field', BearingGeometryPolicy.__dataclass_fields__)
@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, '0.2'])
def test_geometry_requires_finite_numeric_thresholds(field, value):
    with pytest.raises(ValueError):
        replace(BearingGeometryPolicy(.2, .3, 100., 80.), **{field: value})


@pytest.mark.parametrize('values', [(.3, .2, 100., 80.), (-.1, .3, 100., 80.),
                                  (.2, 1.1, 100., 80.), (.2, .3, 70., 80.),
                                  (.2, .3, 181., 80.), (.2, .3, 100., -1.)])
def test_geometry_preserves_asymmetric_threshold_order(values):
    with pytest.raises(ValueError):
        BearingGeometryPolicy(*values)


def test_fw_does_not_accept_unqualified_provider_or_mapping_as_geometry():
    for value in (GimbalGuidancePolicy(), {}, None):
        with pytest.raises(ValueError, match='bearing_geometry_policy_invalid'):
            FixedWingVectorGuidance(enable_altitude_control=False, geometry_policy=value)
