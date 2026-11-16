"""Source-bound stock input association; no guessed calibration or clocks."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion, Vector3
from classes.fixed_camera_calibration import bind_fixed_camera_calibration
from classes.received_guidance_input import ReceivedImageBearingResolver
from tests.unit.followers.test_fixed_camera_calibration import calibration_mapping, saved, geometry, measurement
from tests.unit.followers.test_received_bearing_association import untimed_pair


@pytest.fixture
def case(saved, geometry):
    calibration = bind_fixed_camera_calibration(saved, geometry)
    _, state = untimed_pair()
    state = replace(state, attitude_body_to_ned=Quaternion(1., 0., 0., 0.))
    resolver = ReceivedImageBearingResolver(calibration, binding=state.binding,
        runtime_id="stock-a", timeout_s=.5, clock=lambda: 100.125)
    output = SimpleNamespace(image_measurement=measurement(calibration, (3.5, 1.)))
    return calibration, state, resolver, output


def test_receipt_only_image_uses_calibration_and_keeps_original_attitude(case):
    _, state, resolver, output = case
    first = resolver(output, state)
    assert first.direction_ned == Vector3(1., 0., 0.)
    assert first.association_kind == "latest_received_bearing"
    assert first.source_time is None and first.binding.quat_reset_counter is None
    newer = replace(state, sequence=state.sequence+1, observed_at_monotonic_s=100.1,
        attitude_body_to_ned=Quaternion.from_euler(0., 0., 1.))
    assert resolver(output, newer) == first


@pytest.mark.parametrize("field,value", [
    ("source_id", "replacement-camera"), ("geometry_revision", "replacement-grid"),
    ("calibration_revision", "replacement-calibration"),
])
def test_other_source_or_geometry_cannot_authorize_an_existing_pixel(case, field, value):
    _, state, resolver, output = case
    resolver(output, state)
    image = output.image_measurement
    output.image_measurement = replace(image, provenance=replace(image.provenance, **{field: value}))
    with pytest.raises(ValueError, match="geometry_changed"):
        resolver(output, state)


def test_new_target_rebinds_once_but_obsolete_target_never_returns(case):
    _, state, resolver, output = case
    first = resolver(output, state)
    image = output.image_measurement
    output.image_measurement = replace(image, provenance=replace(image.provenance, target_generation=2))
    assert resolver(output, state).binding.target_generation == 2
    output.image_measurement = image
    with pytest.raises(ValueError, match="target_generation_obsolete"):
        resolver(output, state)
    assert first.binding.target_generation == 1


def test_stale_frame_and_missing_calibration_do_not_gain_freshness(case):
    calibration, state, resolver, output = case
    resolver(output, state)
    resolver.clock = lambda: 101.
    with pytest.raises(ValueError, match="stale"):
        resolver(output, replace(state, sequence=state.sequence+1, observed_at_monotonic_s=101.))
    with pytest.raises(ValueError, match="camera_calibration_required"):
        ReceivedImageBearingResolver(None, binding=state.binding, runtime_id="stock-a", timeout_s=.5)
    assert calibration.geometry.runtime_stream_id == output.image_measurement.provenance.source_id
