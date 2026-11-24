"""Synthetic fixed-camera contract checks; no capture or aircraft connection."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, replace
import math

import cv2
import numpy as np
import pytest

from classes.fixed_camera_calibration import (
    ActiveImageGeometry,
    FixedCameraCalibration,
    PIXEL_GRID,
    bind_fixed_camera_calibration,
    selected_source_signature,
)
from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import ImageMeasurement, ObservationProvenance
from classes.image_bearing import image_to_body_bearing


@pytest.fixture
def calibration_mapping():
    return {
        'source_signature': selected_source_signature(
            source_type='USB_CAMERA', backend='opencv', locator='0', options={'width': 16, 'height': 12}),
        'revision': 'synthetic-1', 'pixel_grid': PIXEL_GRID,
        'image_size_px': [16, 12], 'focal_length_px': [14., 15.],
        'principal_point_px': [7.5, 5.5], 'optical_to_body_frd_wxyz': [.5, .5, .5, .5],
        'distortion_model': 'none', 'mount_kind': 'fixed',
    }


@pytest.fixture
def saved(calibration_mapping):
    return FixedCameraCalibration.from_mapping(calibration_mapping)


@pytest.fixture
def geometry(saved):
    return ActiveImageGeometry(saved.source_signature, 'runtime-camera-a', 'epoch-a',
                               (16, 12), 0, 'none', (8, 3), PIXEL_GRID)


def measurement(binding, pixel):
    provenance = ObservationProvenance(
        binding.calibration.source_id, 1, binding.geometry_revision, binding.calibration_revision,
        CaptureStamp(binding.geometry.source_epoch, 'synthetic-capture-1', 100., 'fresh'),
    )
    return ImageMeasurement(provenance, pixel, binding.geometry.analysis_size_px,
                            binding.image_to_calibration, True)


def test_none_is_inert_and_parsed_values_are_immutable(saved):
    assert FixedCameraCalibration.from_mapping(None) is None
    assert bind_fixed_camera_calibration(None, None) is None
    with pytest.raises(FrozenInstanceError):
        saved.revision = 'changed'


@pytest.mark.parametrize('changes', [
    {'source_signature': 'rtsp://user:secret@example.invalid/video'},
    {'revision': ''}, {'revision': 'rtsp://not-an-id'},
    {'pixel_grid': 'sensor'}, {'mount_kind': 'gimbal'}, {'distortion_model': 'opencv'},
    {'image_size_px': [True, 12]}, {'image_size_px': [0, 12]}, {'image_size_px': [16]},
    {'focal_length_px': [0, 15]}, {'focal_length_px': [-1, 15]},
    *[{'focal_length_px': [value, 15]} for value in (True, '14', math.nan, math.inf)],
    {'principal_point_px': [0, math.inf]}, {'principal_point_px': [False, 0]},
    {'optical_to_body_frd_wxyz': [0, 0, 0, 0]},
    {'optical_to_body_frd_wxyz': [1, 1, 0, 0]},
    {'optical_to_body_frd_wxyz': [math.nan, 0, 0, 1]},
    {'optical_to_body_frd_wxyz': [True, 0, 0, 0]},
    {'optical_to_body_frd_wxyz': [1, 0, 0]},
    {'extra': 1},
])
def test_config_never_infers_invalid_or_missing_calibration(calibration_mapping, changes):
    with pytest.raises(ValueError):
        FixedCameraCalibration.from_mapping({**calibration_mapping, **changes})


@pytest.mark.parametrize('key', [
    'source_signature', 'revision', 'pixel_grid', 'image_size_px', 'focal_length_px',
    'principal_point_px', 'optical_to_body_frd_wxyz', 'distortion_model', 'mount_kind',
])
def test_every_calibration_component_is_explicit(calibration_mapping, key):
    calibration_mapping.pop(key)
    with pytest.raises(ValueError, match='keys_invalid'):
        FixedCameraCalibration.from_mapping(calibration_mapping)


def test_source_signature_is_canonical_private_and_backend_specific(caplog):
    locator = 'rtsp://user:private-password@example.invalid/channel?token=private-token'
    spec = dict(source_type='RTSP_STREAM', backend='gstreamer', locator=locator,
                options={'pipeline': 'private pipeline', 'width': 16, 'height': 12})
    signature = selected_source_signature(**spec)
    assert selected_source_signature(**{**spec, 'options': dict(reversed(list(spec['options'].items())))}) == signature
    for changes in ({'backend': 'opencv'}, {'source_type': 'RTSP_OPENCV'},
                    {'locator': locator + '2'}, {'options': {'width': 32}}):
        assert selected_source_signature(**{**spec, **changes}) != signature
    assert len(signature) == len('sha256-v1:') + 64
    assert 'private' not in signature
    assert locator not in caplog.text
    with pytest.raises(ValueError) as error:
        selected_source_signature(**{**spec, 'options': {'width': [16, 12]}})
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('changes', [
    {'source_type': 'UNKNOWN'}, {'source_type': []}, {'backend': 'auto'}, {'locator': ''},
    {'options': []}, {'options': {'bad key': 'value'}}, {'options': {'width': math.nan}},
    {'options': {'width': {'nested': 1}}},
])
def test_selected_source_spec_is_closed_and_typed(changes):
    spec = dict(source_type='USB_CAMERA', backend='opencv', locator='0', options={})
    with pytest.raises(ValueError):
        selected_source_signature(**{**spec, **changes})


def test_saved_source_binds_to_runtime_uuid_without_changing_saved_identity(saved, geometry):
    bound = bind_fixed_camera_calibration(saved, geometry)
    assert bound.calibration.source_id == geometry.runtime_stream_id
    assert saved.source_signature != geometry.runtime_stream_id
    assert bound.calibration_revision == saved.content_revision
    assert bound.geometry_revision == geometry.geometry_revision
    bound.require_current(geometry)
    new_geometry = replace(geometry, runtime_stream_id='new-runtime', source_epoch='new-epoch')
    next_bound = bind_fixed_camera_calibration(saved, new_geometry)
    assert next_bound.calibration.source_id == 'new-runtime'
    assert next_bound.geometry_revision != bound.geometry_revision
    assert next_bound.calibration_revision == bound.calibration_revision
    assert 'locator' not in repr(bound) and 'options' not in repr(bound)


@pytest.mark.parametrize('changes,error', [
    ({'source_signature': 'sha256-v1:' + 'f' * 64}, 'source_changed'),
    ({'runtime_stream_id': 'other-stream'}, 'runtime_stream_changed'),
    ({'source_epoch': 'other-epoch'}, 'source_epoch_changed'),
    ({'analysis_size_px': (7, 3)}, 'geometry_changed'),
    ({'oriented_decoded_size_px': (32, 24)}, 'geometry_changed'),
    ({'rotation_deg': 180}, 'geometry_changed'),
    ({'flip_mode': 'horizontal'}, 'geometry_changed'),
])
def test_old_runtime_binding_refuses_changed_source_or_geometry(saved, geometry, changes, error):
    bound = bind_fixed_camera_calibration(saved, geometry)
    with pytest.raises(ValueError, match=error):
        bound.require_current(replace(geometry, **changes))


@pytest.mark.parametrize('changes', [
    {'oriented_decoded_size_px': (0, 12)}, {'analysis_size_px': (True, 3)},
    {'rotation_deg': True}, {'rotation_deg': 45}, {'flip_mode': 'auto'},
    {'pixel_grid': 'unknown'}, {'pixel_grid': 'sensor'}, {'source_epoch': ''},
])
def test_active_geometry_never_guesses_unknown_grid_or_operations(geometry, changes):
    with pytest.raises(ValueError):
        replace(geometry, **changes)


def test_source_mismatch_and_decoder_grid_mismatch_never_rescale_intrinsics(saved, geometry):
    with pytest.raises(ValueError, match='source_mismatch'):
        bind_fixed_camera_calibration(saved, replace(geometry, source_signature='sha256-v1:' + 'f'*64))
    with pytest.raises(ValueError, match='decoder_grid_mismatch'):
        bind_fixed_camera_calibration(saved, replace(geometry, oriented_decoded_size_px=(32, 24)))


def test_changed_values_change_revision_even_when_label_is_reused(calibration_mapping, saved, geometry):
    bound = bind_fixed_camera_calibration(saved, geometry)
    original = measurement(bound, (3.5, 1.))
    calibration_mapping['focal_length_px'][0] += 1
    updated = FixedCameraCalibration.from_mapping(calibration_mapping)
    assert updated.revision == saved.revision
    assert updated.content_revision != saved.content_revision
    replacement = bind_fixed_camera_calibration(updated, geometry)
    with pytest.raises(ValueError, match='calibration_revision_changed'):
        image_to_body_bearing(original, replacement.calibration)
    assert original.provenance.capture.captured_at == 100.


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('flip', ['none', 'horizontal', 'vertical', 'both'])
def test_all_orientation_and_flip_compositions_match_actual_opencv_pixels(saved, geometry, rotation, flip):
    yy, xx = np.indices((12, 16), dtype=np.float64)
    pixels = np.dstack((xx, yy))
    if rotation:
        pixels = cv2.rotate(pixels, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                    270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation])
    if flip != 'none':
        pixels = cv2.flip(pixels, {'horizontal': 1, 'vertical': 0, 'both': -1}[flip])
    height, width = pixels.shape[:2]
    analysis_size = (width//2, height//4)
    active = replace(geometry, oriented_decoded_size_px=(width, height), rotation_deg=rotation,
                     flip_mode=flip, analysis_size_px=analysis_size)
    bound = bind_fixed_camera_calibration(saved, active)
    expected = cv2.resize(pixels, analysis_size, interpolation=cv2.INTER_AREA)
    ay, ax = np.indices(expected.shape[:2], dtype=np.float64)
    points = np.dstack((ax, ay, np.ones_like(ax)))
    actual = points @ np.array(bound.image_to_calibration).reshape(2, 3).T
    assert actual == pytest.approx(expected)


def test_noninteger_unequal_resize_uses_pixel_centre_offsets(saved, geometry):
    bound = bind_fixed_camera_calibration(saved, replace(geometry, analysis_size_px=(7, 5)))
    a, b, tx, c, d, ty = bound.image_to_calibration
    assert (a, b, tx, c, d, ty) == pytest.approx((16/7, 0, (16/7-1)/2, 0, 12/5, (12/5-1)/2))
    pixel = (3., 2.)
    result = image_to_body_bearing(measurement(bound, pixel), bound.calibration)
    assert result.direction_body_frd.x == pytest.approx(1.)


def test_already_scaled_decoder_grid_can_be_calibrated_without_native_sensor_claim(saved, geometry):
    bound = bind_fixed_camera_calibration(saved, replace(geometry, analysis_size_px=(16, 12)))
    assert bound.image_to_calibration == (1., 0., 0., 0., 1., 0.)
    assert bound.calibration.image_size_px == (16, 12)


def test_upsampled_border_outside_calibration_centres_is_rejected_not_clamped(saved, geometry):
    bound = bind_fixed_camera_calibration(saved, replace(geometry, analysis_size_px=(32, 24)))
    with pytest.raises(ValueError, match='calibration_pixel_outside_image'):
        image_to_body_bearing(measurement(bound, (0., 0.)), bound.calibration)


def test_input_mutation_does_not_edit_saved_or_bound_calibration(calibration_mapping, geometry):
    parsed = FixedCameraCalibration.from_mapping(deepcopy(calibration_mapping))
    bound = bind_fixed_camera_calibration(parsed, geometry)
    before = asdict(bound)
    calibration_mapping['focal_length_px'][0] = 0
    assert asdict(bound) == before
