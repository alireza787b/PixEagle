"""Deterministic source-clock association; these fixtures are not flight evidence."""

from dataclasses import asdict, replace
import math
from types import SimpleNamespace

import pytest

from classes.aircraft_state import Quaternion
from classes.capture_timing import SourceSampleStamp
from classes.fixed_camera_calibration import (
    ActiveImageGeometry, FixedCameraCalibration, bind_fixed_camera_calibration, selected_source_signature,
)
from classes.frame_publisher import CaptureStamp
from classes.gazebo_capture import GazeboCameraSettings
from classes.gazebo_image_alignment import GazeboImageBearingResolver, SourceAttitudeHistory
from classes.guidance_observation import ImageMeasurement, ObservationProvenance
from classes.source_time_alignment import SourceAttitudeSample
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing


@pytest.fixture
def case():
    now = [100.05]
    state = aircraft_state(attitude_timing=attitude_timing(),
        attitude_body_to_ned=Quaternion(math.sqrt(.5), 0., 0., math.sqrt(.5)))
    signature = selected_source_signature(source_type='GAZEBO_CAMERA', backend='gazebo_transport',
        locator='/camera/image', options={'world': 'training', 'pixel_format': 'RGB_INT8'})
    calibration = FixedCameraCalibration(signature, 'camera-v1', 'decoder_pre_orientation',
        (640, 480), (320., 320.), (320., 240.), Quaternion(.5, .5, .5, .5), 'none', 'fixed')
    geometry = ActiveImageGeometry(signature, 'stream', 'epoch', (640, 480), 0, 'none',
                                   (640, 480), 'decoder_pre_orientation')
    bound = bind_fixed_camera_calibration(calibration, geometry)
    settings = GazeboCameraSettings('/run/camera.sock', 'clock-world', 'training', '/camera/image', .05)
    source = SourceSampleStamp('clock-world', 'provider', 1, 1_020_000, 'gazebo_sim_us')
    capture = CaptureStamp('epoch', '1', 100.01, 'fresh', source)
    provenance = ObservationProvenance('stream', 3, bound.geometry_revision, bound.calibration_revision, capture)
    measurement = ImageMeasurement(provenance, (320., 240.), (640, 480), bound.image_to_calibration, True)
    history = SourceAttitudeHistory()
    raw = SourceAttitudeSample(1_000_000, 1_001_000, (1., 0., 0., 0.),
        state.attitude_timing.quat_reset_counter, 100., 'px4_source_us')
    history.commit(asdict(raw), state, runtime_id='native', source_clock_id='clock-world')
    resolver = GazeboImageBearingResolver(settings, bound, history, binding=state.binding,
        runtime_id='native', native_source_clock_id='clock-world', timeout_s=.5, clock=lambda: now[0])
    return SimpleNamespace(now=now, state=state, settings=settings, bound=bound, history=history,
        raw=raw, measurement=measurement, output=SimpleNamespace(image_measurement=measurement), resolver=resolver)


def test_world_ray_uses_retained_raw_sample_not_latest_dds_attitude(case):
    result = case.resolver(case.output, case.state)
    assert (result.direction_ned.x, result.direction_ned.y, result.direction_ned.z) == pytest.approx((1., 0., 0.))
    assert result.association_kind == 'bounded_source_time'
    assert result.worst_case_skew_s == pytest.approx(.02)
    assert result.attitude_state == case.state
    assert result.source_time.attitude == case.raw


def test_duplicate_reads_retain_original_association_and_receipt(case):
    first = case.resolver(case.output, case.state)
    case.now[0] += .1
    assert case.resolver(case.output, case.state) is first
    assert first.source_time.attitude.received_at_monotonic_s == 100.
    assert not case.history.commit(asdict(case.raw), case.state,
        runtime_id='native', source_clock_id='clock-world')


@pytest.mark.parametrize('changes', [dict(received_at_monotonic_s=100.1), dict(quaternion_wxyz=(0., 0., 0., 1.))])
def test_same_source_sample_cannot_be_restamped_or_rotated(case, changes):
    with pytest.raises(ValueError, match='sample_rewritten'):
        case.history.commit(asdict(replace(case.raw, **changes)), case.state,
            runtime_id='native', source_clock_id='clock-world')
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_no_alignment_inferred_from_receipt_when_source_times_disagree(case):
    source = replace(case.measurement.provenance.capture.source_sample, timestamp_us=2_000_000)
    provenance = replace(case.measurement.provenance,
        capture=replace(case.measurement.provenance.capture, source_sample=source))
    case.output.image_measurement = replace(case.measurement, provenance=provenance)
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_unqualified_clock_label_is_not_a_timing_fallback(case):
    with pytest.raises(ValueError, match='source_clock_domain_unqualified'):
        GazeboImageBearingResolver(case.settings, case.bound, case.history, binding=case.state.binding,
            runtime_id='native', native_source_clock_id='other-clock', timeout_s=.5)


def test_same_frame_measurement_rewrite_is_rejected(case):
    case.resolver(case.output, case.state)
    case.output.image_measurement = replace(case.measurement, pixel_xy=(330., 240.))
    with pytest.raises(ValueError, match='capture_rewritten'):
        case.resolver(case.output, case.state)


def test_retarget_accepts_new_generation_without_accepting_obsolete_generation(case):
    case.resolver(case.output, case.state)
    provenance = replace(case.measurement.provenance, target_generation=4)
    case.output.image_measurement = replace(case.measurement, provenance=provenance)
    assert case.resolver(case.output, case.state).binding.target_generation == 4
    case.output.image_measurement = case.measurement
    with pytest.raises(ValueError, match='target_generation_obsolete'):
        case.resolver(case.output, case.state)


def test_history_retirement_invalidates_even_a_retained_valid_frame(case):
    case.resolver(case.output, case.state)
    case.history.clear()
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, case.state)


def test_stale_raw_attitude_does_not_become_fresh_when_pose_advances(case):
    case.now[0] = 100.8
    state = replace(case.state, sequence=2, observed_at_monotonic_s=100.8,
        attitude_timing=attitude_timing(publication_received_at_monotonic_s=100.8,
                                      sample_received_at_monotonic_s=100.8))
    with pytest.raises(ValueError, match='alignment_unavailable'):
        case.resolver(case.output, state)
