"""Contract tests for the generated RTP/UDP receiver proof harness."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "run_udp_video_receiver_proof.py"


def test_udp_video_receiver_proof_dry_run_is_side_effect_free(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--dry-run",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "dry-run-contract",
            "--json",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)

    assert payload["status"] == "dry_run"
    assert payload["would_start_processes"] is False
    assert payload["would_write_artifacts"] is False
    assert "Generated RTP/UDP video ingest proof only" in payload["claim_boundary"]
    assert payload["receiver_contract"]["valid"] is True
    assert not (tmp_path / "dry-run-contract").exists()


def test_udp_video_receiver_contract_requires_h264_rtp_caps():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import run_udp_video_receiver_proof as proof  # pylint: disable=import-outside-toplevel

    contract = proof.validate_receiver_pipeline(
        proof.STRICT_UDP_TEMPLATE,
        url="udp://127.0.0.1:5600",
        width=320,
        height=240,
    )

    assert contract["valid"] is True
    pipeline = contract["pipeline"]
    assert "udpsrc" in pipeline
    assert 'caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"' in pipeline
    assert "rtph264depay" in pipeline
    assert "h264parse" in pipeline
    assert "avdec_h264" in pipeline
    assert "video/x-raw,format=BGR" in pipeline
    assert "videoscale" in pipeline
    assert "width=320" in pipeline
    assert "height=240" in pipeline
    assert "appsink drop=true max-buffers=1 sync=false" in pipeline


def test_udp_video_receiver_proof_execute_requires_explicit_process_start():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--execute", "--json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert "--execute requires --allow-process-start" in payload["reason"]


def test_udp_video_receiver_execute_incomplete_writes_manifest(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import run_udp_video_receiver_proof as proof  # pylint: disable=import-outside-toplevel

    args = proof.parse_args(
        [
            "--execute",
            "--allow-process-start",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "missing-runtime",
        ]
    )
    monkeypatch.setattr(proof.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        proof,
        "_opencv_gstreamer_enabled",
        lambda: (False, {"opencv_version": "test", "gstreamer_enabled": False}),
    )
    contract = proof.validate_receiver_pipeline(
        proof.STRICT_UDP_TEMPLATE,
        url="udp://127.0.0.1:5600",
        width=320,
        height=240,
    )

    result = proof._run_execute(args, proof.STRICT_UDP_TEMPLATE, contract)

    manifest_path = tmp_path / "missing-runtime" / "manifest.json"
    assert result["status"] == "incomplete"
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "incomplete"


def test_udp_video_receiver_proof_does_not_manage_px4_or_services():
    source = TOOL.read_text(encoding="utf-8")

    forbidden_terms = [
        "docker run",
        "px4-sitl",
        "gz_",
        "mavlink-router",
        "systemctl",
        "sudo",
        "configure_mavlink_router",
    ]
    lowered = source.lower()
    for term in forbidden_terms:
        assert term not in lowered


@pytest.mark.parametrize(
    "bad_template, missing_term",
    [
        (
            "udpsrc uri={url} ! application/x-rtp ! rtph264depay ! avdec_h264 "
            "! videoconvert ! video/x-raw,format=BGR ! videoscale "
            "! video/x-raw,width={width},height={height} ! appsink drop=true sync=false",
            "h264parse",
        ),
        (
            "udpsrc uri={url} ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
            "! video/x-raw,format=BGR ! videoscale "
            "! video/x-raw,width={width},height={height} ! appsink drop=true max-buffers=1 sync=false",
            'caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"',
        ),
        (
            "udpsrc uri={url} ! rtph264depay "
            '! caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000" '
            "! h264parse ! avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! videoscale "
            "! video/x-raw,width={width},height={height} ! appsink drop=true max-buffers=1 sync=false",
            "rtph264depay",
        ),
    ],
)
def test_udp_video_receiver_contract_rejects_weak_pipelines(bad_template, missing_term):
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import run_udp_video_receiver_proof as proof  # pylint: disable=import-outside-toplevel

    contract = proof.validate_receiver_pipeline(
        bad_template,
        url="udp://127.0.0.1:5600",
        width=320,
        height=240,
    )

    assert contract["valid"] is False
    assert (
        missing_term in contract["missing"]
        or any(missing_term in term for term in contract["out_of_order"])
    )


def test_udp_video_receiver_contract_reads_real_default_template():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import run_udp_video_receiver_proof as proof  # pylint: disable=import-outside-toplevel

    template = proof._read_default_udp_template()
    contract = proof.validate_receiver_pipeline(
        template,
        url="udp://127.0.0.1:5600",
        width=320,
        height=240,
    )

    assert contract["valid"] is True


def test_udp_video_receiver_stale_gate_requires_actual_stale_status():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import run_udp_video_receiver_proof as proof  # pylint: disable=import-outside-toplevel

    assert proof.is_strict_post_stop_stale(
        {
            "usable_for_following": False,
            "reason": "udp_async_frame_stale",
            "frame_age_seconds": 0.7,
        },
        stale_timeout_seconds=0.6,
    )
    assert not proof.is_strict_post_stop_stale(
        {
            "usable_for_following": False,
            "reason": "udp_async_awaiting_new_frame",
            "frame_age_seconds": 0.7,
        },
        stale_timeout_seconds=0.6,
    )
    assert not proof.is_strict_post_stop_stale(
        {
            "usable_for_following": False,
            "reason": "udp_async_frame_stale",
            "frame_age_seconds": 0.3,
        },
        stale_timeout_seconds=0.6,
    )
