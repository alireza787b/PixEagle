"""Measured image producers retain only explicitly bound fixed-camera geometry."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from classes.fixed_camera_calibration import FixedCameraCalibration
from classes.image_bearing import image_to_body_bearing
from tests.unit.core_app.test_image_provenance import controller, update_classic  # noqa: F401


SIGNATURE = 'sha256-v1:' + 'a' * 64


def measured_calibration(signature=SIGNATURE):
    return FixedCameraCalibration.from_mapping({
        'source_signature': signature, 'revision': 'fixture-1', 'pixel_grid': 'decoder_pre_orientation',
        'image_size_px': [1280, 720], 'focal_length_px': [900., 900.], 'principal_point_px': [639.5, 359.5],
        'optical_to_body_frd_wxyz': [.5, .5, .5, .5], 'distortion_model': 'none', 'mount_kind': 'fixed',
    })


def publish(owner, *, receipt=100., source_signature=SIGNATURE):
    video = owner.video_handler
    if video.cap is None:
        video.cap = SimpleNamespace(isOpened=lambda: True, release=lambda: None)
    video._capture_identities[id(video.cap)] = (video.cap, source_signature)
    frame = video._apply_frame_orientation(np.zeros((720, 1280, 3), np.uint8))
    video.current_raw_frame = frame
    video._reset_failure_counters(captured_at=receipt)
    stamp, geometry, signature = video.get_capture_context(frame)
    analysis = video.analysis_frame(frame)
    owner._publish_tracking_input_frame(analysis, capture=stamp, capture_geometry=geometry,
                                        capture_source_signature=signature)
    return analysis, owner.tracking_input_context


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('flip', ['none', 'horizontal', 'vertical', 'both'])
def test_explicit_calibration_mapping_is_frozen_before_tracking(controller, rotation, flip):
    video = controller.video_handler
    video.fixed_camera_calibration = measured_calibration()
    video._frame_rotation_deg, video._frame_flip_mode = rotation, flip
    frame, context = publish(controller)
    binding = controller._image_calibration_binding
    assert binding is not None and controller._image_calibration_error is None
    assert context.image_to_calibration == binding.image_to_calibration
    output = update_classic(controller, frame, context)
    sample = output.image_measurement
    assert sample is not None
    assert sample.image_to_calibration is context.image_to_calibration
    assert sample.provenance is context.provenance
    assert sample.provenance.calibration_revision == binding.calibration_revision
    ray = image_to_body_bearing(sample, binding.calibration)
    assert ray.provenance is sample.provenance
    assert ray.direction_body_frd.magnitude == pytest.approx(1.)
    assert ray.direction_body_frd.x > 0.
    assert controller.tracker.get_output().image_measurement is sample


def test_changed_source_preserves_image_tracking_but_cannot_reuse_calibration(controller):
    controller.video_handler.fixed_camera_calibration = measured_calibration()
    frame, context = publish(controller, source_signature='sha256-v1:' + 'b' * 64)
    output = update_classic(controller, frame, context)
    assert controller._image_calibration_error == 'calibration_source_mismatch'
    assert controller._image_calibration_binding is None
    assert output.raw_data['usable_for_following'] is True
    assert output.image_measurement.provenance.calibration_revision is None
    assert output.image_measurement.image_to_calibration is None


@pytest.mark.parametrize('native_capture', [False, True])
def test_binding_uses_the_actual_decoder_grid_in_both_capture_modes(controller, native_capture):
    video = controller.video_handler
    video.native_capture_resolution = native_capture
    video.fixed_camera_calibration = measured_calibration()
    frame, context = publish(controller)
    binding = controller._image_calibration_binding
    assert binding is not None
    assert binding.geometry.decoded_size_px == (1280, 720)
    assert context.image_size_px == (frame.shape[1], frame.shape[0])
    assert update_classic(controller, frame, context).image_measurement is not None


def test_editing_values_without_changing_label_cannot_reuse_previous_revision(controller):
    saved = measured_calibration()
    controller.video_handler.fixed_camera_calibration = saved
    frame, first_context = publish(controller)
    previous = update_classic(controller, frame, first_context).image_measurement
    controller.video_handler.fixed_camera_calibration = replace(saved, focal_length_px=(1000., 1000.))
    frame, second_context = publish(controller, receipt=101.)
    binding = controller._image_calibration_binding
    assert first_context.provenance.calibration_revision != second_context.provenance.calibration_revision
    with pytest.raises(ValueError, match='calibration_revision_changed'):
        image_to_body_bearing(previous, binding.calibration)


def test_fixed_extrinsics_never_substitute_for_a_movable_camera_pose(controller):
    controller.video_handler.fixed_camera_calibration = measured_calibration()
    controller.camera_runtime = SimpleNamespace(settings={'CONTROL_ENABLED': True})
    frame, context = publish(controller)
    output = update_classic(controller, frame, context)
    assert controller._image_calibration_binding is None
    assert controller._image_calibration_error == 'moving_camera_extrinsics_unqualified'
    assert output.image_measurement.provenance.calibration_revision is None


def test_missing_geometry_drops_the_prior_binding_instead_of_advertising_it_ready(controller):
    controller.video_handler.fixed_camera_calibration = measured_calibration()
    frame, context = publish(controller)
    assert controller._image_calibration_binding is not None
    controller._publish_tracking_input_frame(frame)
    assert controller.tracking_input_context is None
    assert controller._image_calibration_binding is None
    assert controller._image_calibration_error == 'capture_geometry_unavailable'


def test_old_source_context_cannot_commit_calibrated_output_after_replacement(controller):
    controller.video_handler.fixed_camera_calibration = measured_calibration()
    frame, context = publish(controller)
    controller.video_handler._advance_source_epoch()
    assert update_classic(controller, frame, context).image_measurement is None
