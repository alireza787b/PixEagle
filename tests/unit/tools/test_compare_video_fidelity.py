"""Fidelity measurements compare coherent grids and retain evidence boundaries."""
import json

import numpy as np
import pytest

from tools import compare_video_fidelity as compare


def test_psnr_requires_equal_grids_and_represents_identity_without_invalid_json():
    source = np.zeros((2, 3, 3), dtype=np.uint8)
    assert compare.psnr(source, source) is None
    with pytest.raises(ValueError, match='matching'):
        compare.psnr(source, np.zeros((3, 2, 3)))


def test_native_profile_preserves_aspect_and_does_not_upscale():
    source = np.full((90, 160, 3), 90, dtype=np.uint8)
    metrics, jpeg, restored = compare.measure_profile(
        source, compare.PROFILES['native-fit-720p-q80'], 2, 20)
    assert metrics['encoded_dimensions'] == [160, 90]
    assert metrics['jpeg_bytes'] == jpeg.nbytes
    assert metrics['payload_kbps_at_requested_fps'] == jpeg.nbytes * 8 * 20 / 1000
    assert restored.shape == source.shape
    assert metrics['encode_ms_p95'] >= 0


def test_report_labels_reconstruction_and_refuses_to_overwrite(tmp_path):
    source = np.arange(90 * 160 * 3, dtype=np.uint8).reshape(90, 160, 3)
    original = source.copy()
    report = compare.run_comparison(source, tmp_path / 'run', {'kind': 'synthetic'}, trials=1)
    np.testing.assert_array_equal(source, original)
    saved = json.loads((tmp_path / 'run/report.json').read_text())
    assert saved['source_dimensions'] == [160, 90]
    assert saved['profiles']['legacy-reconstructed-480p-q50']['encoded_dimensions'] == [640, 480]
    assert 'not a capture of the old Pi process' in saved['limitations'][0]
    assert report['source_pixels_sha256'] == saved['source_pixels_sha256']
    assert (tmp_path / 'run/native-fit-720p-q80-source-grid-crop.png').exists()
    with pytest.raises(ValueError, match='never overwritten'):
        compare.run_comparison(source, tmp_path / 'run', {'kind': 'synthetic'}, trials=1)


def test_synthetic_detail_fixture_is_repeatable_full_hd():
    first, second = compare.synthetic_detail(), compare.synthetic_detail()
    assert first.shape == (1080, 1920, 3)
    np.testing.assert_array_equal(first, second)
