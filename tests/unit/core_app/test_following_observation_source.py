"""Source identity is immutable and separate from samples and follow authority."""

from dataclasses import FrozenInstanceError, asdict, replace
from types import SimpleNamespace

import pytest

from classes.following_observation_source import (
    GimbalFollowingSource, ImageFollowingSource, ImageObservationOwner, ObservationSourceVerdict,
    compare_following_observation_source, project_following_observation_source,
)
from classes.frame_publisher import CaptureStamp
from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
from classes.guidance_observation import ImageFrameContext, ObservationProvenance


pytestmark = pytest.mark.unit


def image_context(**changes):
    provenance = ObservationProvenance("image-owner", 3, "analysis-geometry", None,
                                       CaptureStamp("capture-epoch", "1", 100., "fresh"))
    return ImageFrameContext(replace(provenance, **changes), (640, 480))


def gimbal_observation(**changes):
    values = dict(source=CameraObservationSource("camera-owner", 1), target_generation=3,
                  provider_id="provider", geometry_revision="mount-geometry", angles_deg=(0., 90., 0.),
                  coordinate_system="gimbal_body", angle_receipt_sequence=1,
                  angle_received_at_monotonic_s=100., tracking_state="TRACKING_ACTIVE",
                  tracking_received_at_monotonic_s=99.9)
    return GimbalAngleObservation(**(values | changes))


def compare(pin, current, sample):
    return compare_following_observation_source(pin, current=current, sample=sample)


def test_image_context_and_measurement_project_the_existing_provenance():
    context = image_context()
    sample = context.at_pixel((319.5, 239.5))
    pin = project_following_observation_source(context)
    assert pin == ImageFollowingSource("image-owner", "capture-epoch", "analysis-geometry", None)
    assert project_following_observation_source(sample) == pin
    assert compare(pin, context, sample) is ObservationSourceVerdict.UNCHANGED


@pytest.mark.parametrize("context", [None, image_context(), image_context(
    capture=CaptureStamp("capture-epoch", "1", 1., "cached")), {}])
@pytest.mark.parametrize("sample", [None, image_context().at_pixel((1., 1.)), {}])
def test_image_publisher_restart_precedes_missing_stale_or_malformed_analysis_and_sample(context, sample):
    pin = project_following_observation_source(image_context())
    assert compare_following_observation_source(pin,
        current=ImageObservationOwner("image-owner", "restarted-epoch"), current_context=context,
        sample=sample) is ObservationSourceVerdict.DEFINITELY_CHANGED


def test_image_owner_and_current_analysis_geometry_must_both_match_the_pin():
    old = image_context()
    pin = project_following_observation_source(old)
    owner = ImageObservationOwner(pin.source_id, pin.source_epoch)
    sample = old.at_pixel((1., 1.))
    assert compare_following_observation_source(pin, current=owner, current_context=old,
        sample=sample) is ObservationSourceVerdict.UNCHANGED
    for context in (image_context(geometry_revision="new-analysis"), image_context(calibration_revision="new-optics")):
        assert compare_following_observation_source(pin, current=owner, current_context=context,
            sample=sample) is ObservationSourceVerdict.DEFINITELY_CHANGED
    for context in (None, {}, object()):
        assert compare_following_observation_source(pin, current=owner, current_context=context,
            sample=sample) is ObservationSourceVerdict.UNAVAILABLE


def test_image_owner_replacement_is_definite_without_an_analysis_frame():
    pin = project_following_observation_source(image_context())
    assert compare_following_observation_source(pin, current=ImageObservationOwner("new-publisher", pin.source_epoch),
        current_context=None, sample=None) is ObservationSourceVerdict.DEFINITELY_CHANGED


def test_partial_image_owner_cannot_be_used_as_a_frozen_pin_or_sample():
    context = image_context()
    pin = project_following_observation_source(context)
    owner = ImageObservationOwner(pin.source_id, pin.source_epoch)
    with pytest.raises(ValueError, match="source_contract_invalid"):
        project_following_observation_source(owner)
    assert compare_following_observation_source(owner, current=owner, current_context=context,
        sample=context) is ObservationSourceVerdict.UNAVAILABLE
    assert compare_following_observation_source(pin, current=owner, current_context=context,
        sample=owner) is ObservationSourceVerdict.UNAVAILABLE


def test_gimbal_projection_retains_the_exact_source_without_requiring_a_physical_target_id():
    sample = gimbal_observation()
    pin = project_following_observation_source(sample)
    assert pin == GimbalFollowingSource(sample.source, "provider", "mount-geometry")
    assert pin.source is sample.source
    assert compare(pin, sample.source, sample) is ObservationSourceVerdict.UNCHANGED
    assert not sample.physical_target_identity_confirmed


def test_missing_gimbal_source_is_unavailable_not_a_new_owner():
    sample = gimbal_observation(source=None)
    assert project_following_observation_source(sample) is None
    pin = project_following_observation_source(gimbal_observation())
    assert compare(pin, pin.source, sample) is ObservationSourceVerdict.UNAVAILABLE
    assert compare(None, pin.source, gimbal_observation()) is ObservationSourceVerdict.UNAVAILABLE


@pytest.mark.parametrize("changes", [{"source_id": "other-source"}, {"geometry_revision": "new-geometry"},
                                    {"calibration_revision": "new-calibration"},
                                    {"capture": CaptureStamp("new-epoch", "2", 101., "fresh")}])
def test_image_source_geometry_epoch_and_calibration_changes_are_detected(changes):
    old = image_context()
    pin = project_following_observation_source(old)
    changed = image_context(**changes)
    assert compare(pin, changed, old) is ObservationSourceVerdict.DEFINITELY_CHANGED
    assert compare(pin, old, changed) is ObservationSourceVerdict.DEFINITELY_CHANGED
    assert compare(pin, changed, None) is ObservationSourceVerdict.DEFINITELY_CHANGED


@pytest.mark.parametrize("changes", [{"source": CameraObservationSource("new-camera", 1)},
    {"source": CameraObservationSource("camera-owner", 2)}, {"provider_id": "new-provider"},
    {"geometry_revision": "new-mount"}])
def test_gimbal_source_owner_generation_provider_and_geometry_changes_are_detected(changes):
    old = gimbal_observation()
    pin = project_following_observation_source(old)
    changed = gimbal_observation(**changes)
    assert compare(pin, changed, old) is ObservationSourceVerdict.DEFINITELY_CHANGED
    assert compare(pin, old.source, changed) is ObservationSourceVerdict.DEFINITELY_CHANGED
    assert compare(pin, changed, None) is ObservationSourceVerdict.DEFINITELY_CHANGED


@pytest.mark.parametrize("sample", [None, object(), {}, {"source": "camera-owner"}])
def test_current_owner_restart_wins_over_a_missing_or_malformed_sample(sample):
    pin = project_following_observation_source(gimbal_observation())
    restarted = CameraObservationSource("camera-owner", 2)
    assert compare(pin, restarted, sample) is ObservationSourceVerdict.DEFINITELY_CHANGED


def test_old_cached_sample_cannot_pass_after_same_object_provider_restart():
    old = gimbal_observation()
    pin = project_following_observation_source(old)
    current = replace(old.source, source_generation=old.source.source_generation+1)
    assert old.source == pin.source
    assert compare(pin, current, old) is ObservationSourceVerdict.DEFINITELY_CHANGED


@pytest.mark.parametrize("current,sample", [(None, None), (None, "matching_sample"),
                                          ("matching_owner", None), ({}, "matching_sample"),
                                          ("matching_owner", object())])
def test_missing_or_unknown_current_context_and_samples_never_confirm_a_pin(current, sample):
    original = gimbal_observation()
    pin = project_following_observation_source(original)
    if current == "matching_owner":
        current = original.source
    if sample == "matching_sample":
        sample = original
    assert compare(pin, current, sample) is ObservationSourceVerdict.UNAVAILABLE


def test_new_sample_from_a_different_source_is_rejected_even_with_missing_current_context():
    pin = project_following_observation_source(gimbal_observation())
    new = gimbal_observation(source=CameraObservationSource("another-camera", 1))
    assert compare(pin, None, new) is ObservationSourceVerdict.DEFINITELY_CHANGED


def test_source_identity_excludes_retarget_capture_progress_and_pixel_position():
    original = image_context()
    pin = project_following_observation_source(original)
    retarget = image_context(target_generation=4, capture=CaptureStamp("capture-epoch", "2", 101., "fresh"))
    assert compare(pin, retarget, retarget.at_pixel((100., 120.))) is ObservationSourceVerdict.UNCHANGED
    angles = gimbal_observation()
    pin = project_following_observation_source(angles)
    updated = replace(angles, target_generation=4, angle_receipt_sequence=2,
                      angle_received_at_monotonic_s=101., tracking_received_at_monotonic_s=100.9,
                      angles_deg=(10., 100., 3.))
    assert compare(pin, angles.source, updated) is ObservationSourceVerdict.UNCHANGED


def test_image_and_gimbal_sources_cannot_be_interchanged():
    image, angles = image_context(), gimbal_observation()
    pin = project_following_observation_source(image)
    assert compare(pin, angles.source, image) is ObservationSourceVerdict.DEFINITELY_CHANGED
    assert compare(pin, image, angles) is ObservationSourceVerdict.DEFINITELY_CHANGED


def test_media_delivery_metadata_cannot_supply_analysis_source_identity():
    context = image_context()
    pin = project_following_observation_source(context)
    delivery = SimpleNamespace(source_id="image-owner", source_epoch="capture-epoch",
                               stream_epoch="receiver-epoch", encoded_width=1280, encoded_height=720,
                               geometry_revision="analysis-geometry")
    with pytest.raises(ValueError, match="source_contract_invalid"):
        project_following_observation_source(delivery)
    assert compare(pin, delivery, context.at_pixel((1., 1.))) is ObservationSourceVerdict.UNAVAILABLE
    delivery.stream_epoch, delivery.encoded_width = "new-receiver-epoch", 320
    assert compare(pin, context, context.at_pixel((1., 1.))) is ObservationSourceVerdict.UNCHANGED


def test_source_checks_neither_mutate_nor_revive_stale_image_or_lost_target_evidence():
    context = image_context(capture=CaptureStamp("capture-epoch", "1", 1., "cached"))
    sample = context.at_pixel((1., 1.))
    pin = project_following_observation_source(sample)
    before = asdict(sample)
    for _ in range(3):
        assert compare(pin, context, sample) is ObservationSourceVerdict.UNCHANGED
    assert asdict(sample) == before
    with pytest.raises(ValueError, match="image_receipt_not_fresh"):
        sample.provenance.require_current(source_id=pin.source_id, source_epoch=pin.source_epoch,
            target_generation=3, geometry_revision=pin.geometry_revision, calibration_revision=None,
            now_monotonic_s=1000., max_receipt_age_s=.5)
    lost = gimbal_observation(tracking_state="TARGET_LOST")
    pin = project_following_observation_source(lost)
    before = asdict(lost)
    assert compare(pin, lost.source, lost) is ObservationSourceVerdict.UNCHANGED
    assert asdict(lost) == before and lost.tracking_state == "TARGET_LOST"


@pytest.mark.parametrize("value", ["", " bad ", None, True, 1])
def test_source_variants_reject_malformed_identities(value):
    with pytest.raises(ValueError):
        ImageFollowingSource(value, "epoch", "geometry")
    if value is not None:
        with pytest.raises(ValueError):
            ImageFollowingSource("owner", "epoch", "geometry", value)
    with pytest.raises(ValueError):
        GimbalFollowingSource(CameraObservationSource("camera", 1), value, "geometry")
    with pytest.raises(ValueError):
        ImageObservationOwner("owner", value)


def test_source_values_are_immutable_and_owner_only_samples_are_insufficient():
    sample = gimbal_observation()
    pin = project_following_observation_source(sample)
    with pytest.raises(FrozenInstanceError):
        pin.geometry_revision = "other"
    with pytest.raises(ValueError, match="camera_observation_source_invalid"):
        GimbalFollowingSource(None, "provider", "geometry")
    assert compare(pin, sample.source, sample.source) is ObservationSourceVerdict.UNAVAILABLE
