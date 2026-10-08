"""Sender identity mapping without GStreamer, a camera or a network."""

import math

import pytest

from classes.gstreamer_frame_association import GStreamerFrameAssociation

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


def test_fragments_emit_only_at_marker_and_freeze_metadata():
    association = GStreamerFrameAssociation()
    epoch = association.epoch
    context = {"frame_id": 42, "geometry": {"width": 1280, "height": 720}}
    assert association.submit(epoch, 50_000_000, context)
    context["geometry"]["width"] = 1
    assert association.observe_packet(epoch, 50_000_000, 123, 9845, marker=False) is None
    result = association.observe_packet(epoch, 50_000_000, 123, 9845, marker=True)
    assert result.metadata()["geometry"]["width"] == 1280
    assert (result.ssrc, result.rtp_timestamp, result.running_time_ns) == (123, 9845, 50_000_000)
    result.metadata()["geometry"]["width"] = 7
    assert result.metadata()["geometry"]["width"] == 1280
    assert association.observe_packet(epoch, 50_000_000, 123, 9845, marker=True) is None


def test_wrap_uses_actual_timestamp_and_reordered_output_uses_exact_input():
    association = GStreamerFrameAssociation()
    epoch = association.epoch
    for frame in range(3):
        assert association.submit(epoch, frame * 50_000_000, {"frame_id": frame})
    for frame, timestamp in [(2, 5704), (0, 4294964000), (1, 1204)]:
        result = association.observe_packet(epoch, frame * 50_000_000, 5, timestamp, marker=True)
        assert result.metadata()["frame_id"] == frame
        assert result.rtp_timestamp == timestamp
    assert association.snapshot()["pending_frames"] == 0


def test_epoch_reset_rejects_late_packets_even_when_input_time_repeats():
    association = GStreamerFrameAssociation()
    previous = association.epoch
    association.submit(previous, 0, {"frame_id": "old"})
    current = association.reset()
    assert current != previous
    assert not association.submit(previous, 0, {"frame_id": "late"})
    assert association.submit(current, 0, {"frame_id": "new"})
    assert association.observe_packet(previous, 0, 1, 2, marker=True) is None
    assert association.observe_packet(current, 0, 1, 2, marker=True).metadata()["frame_id"] == "new"


def test_expiry_capacity_and_discard_never_assign_a_replacement_frame():
    now = [0.0]
    association = GStreamerFrameAssociation(max_pending=2, max_age_seconds=1, clock=lambda: now[0])
    epoch = association.epoch
    for i in range(3):
        association.submit(epoch, i, {"frame_id": i})
    assert association.snapshot()["pending_frames"] == 2
    assert association.observe_packet(epoch, 0, 1, 2, marker=True) is None
    association.discard(epoch, 1)
    assert association.observe_packet(epoch, 1, 1, 2, marker=True) is None
    now[0] = 1.01
    assert association.observe_packet(epoch, 2, 1, 2, marker=True) is None
    assert association.snapshot()["pending_frames"] == 0


def test_inconsistent_fragments_and_ambiguous_timestamp_are_rejected():
    association = GStreamerFrameAssociation()
    epoch = association.epoch
    association.submit(epoch, 0, {})
    assert association.observe_packet(epoch, 0, 1, 2, marker=False) is None
    assert association.observe_packet(epoch, 0, 1, 3, marker=True) is None
    association.submit(epoch, 1, {})
    association.submit(epoch, 2, {})
    assert association.observe_packet(epoch, 1, 1, 4, marker=False) is None
    assert association.observe_packet(epoch, 2, 1, 4, marker=True) is None
    assert association.observe_packet(epoch, 1, 1, 4, marker=True) is None


def test_reused_input_and_rtp_identity_are_rejected():
    association = GStreamerFrameAssociation()
    epoch = association.epoch
    assert association.submit(epoch, 1, {})
    assert not association.submit(epoch, 1, {})
    assert association.observe_packet(epoch, 1, 1, 2, marker=True)
    assert association.submit(epoch, 2, {})
    assert association.observe_packet(epoch, 2, 1, 2, marker=True) is None


@pytest.mark.parametrize("value", [-1, True, math.nan, (1 << 64) - 1])
def test_invalid_input_time_is_not_admitted(value):
    association = GStreamerFrameAssociation()
    with pytest.raises(ValueError):
        association.submit(association.epoch, value, {})


def test_metadata_has_size_and_finite_json_bounds():
    association = GStreamerFrameAssociation(max_metadata_bytes=16)
    with pytest.raises(ValueError):
        association.submit(association.epoch, 0, {"large": "x" * 32})
    with pytest.raises(ValueError):
        association.submit(association.epoch, 0, {"nan": math.nan})
