#!/usr/bin/env python3
"""Compare the same recorded/synthetic pixels through explicit JPEG profiles.

This camera-free measurement reconstructs the former low-resolution display
path. It does not connect to a backend, run trackers or measure display latency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from classes.video_geometry import fit_dimensions, resize_pixels  # noqa: E402

PROFILES = {
    "legacy-reconstructed-480p-q50": {"bounds": (640, 480), "quality": 50, "legacy": True},
    "native-fit-720p-q80": {"bounds": (1280, 720), "quality": 80, "legacy": False},
    "native-fit-1080p-q80": {"bounds": (1920, 1080), "quality": 80, "legacy": False},
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def synthetic_detail():
    """Deterministic 1080p detail fixture, explicitly not camera footage."""
    height, width = 1080, 1920
    y, x = np.indices((height, width))
    frame = np.stack(((x * 255 // width), (y * 255 // height), ((x + y) % 256)), axis=2).astype(np.uint8)
    for offset, period in enumerate((1, 2, 4, 8, 16, 32)):
        left = 60 + 300 * offset
        pattern = ((x[:260, :260] // period + y[:260, :260] // period) % 2 * 255).astype(np.uint8)
        frame[150:410, left:left + 260] = pattern[:, :, None]
        cv2.putText(frame, f"{period}px", (left, 130), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    for size, row in ((0.4, 490), (0.7, 560), (1.0, 650), (1.4, 760)):
        cv2.putText(frame, "SYNTHETIC detail 0123456789 ABCDEFG target edges", (120, row),
                    cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), 1, cv2.LINE_AA)
    rng = np.random.default_rng(42)
    frame[810:1060, 780:1140] = rng.integers(0, 256, (250, 360, 3), dtype=np.uint8)
    cv2.circle(frame, (1500, 820), 140, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def read_recorded_frame(path, index):
    path = path.expanduser().resolve(strict=True)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"Cannot decode recorded source: {path.name}")
        # Sequential decoding selects the exact requested frame instead of trusting keyframe seeking.
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame = None
        for _ in range(index + 1):
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ValueError(f"Source ended before requested frame {index}")
        return frame, {"kind": "recorded", "file": path.name, "file_sha256": sha256(path),
                       "frame_index": index, "nominal_fps": fps}
    finally:
        capture.release()


def psnr(reference, observed):
    if reference.shape != observed.shape:
        raise ValueError("PSNR requires matching pixel grids")
    error = np.mean((reference.astype(np.float64) - observed.astype(np.float64)) ** 2)
    # JSON null denotes mathematically infinite PSNR for exact equality.
    return None if error == 0 else 10 * math.log10(255 * 255 / error)


def prepare_frame(source, profile, clahe):
    width, height = profile["bounds"]
    if profile["legacy"]:
        # Reconstruction only: these named settings are explicit, not read from any deployment.
        image = cv2.resize(source, (width, height), interpolation=cv2.INTER_NEAREST)
        image = cv2.GaussianBlur(image, (5, 5), 0)
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    width, height = fit_dimensions(source.shape[1], source.shape[0], width, height)
    return resize_pixels(source, width, height)


def measure_profile(source, profile, trials, fps):
    if trials < 1 or fps <= 0:
        raise ValueError("Trial count and FPS must be positive")
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    processing, encoding = [], []
    for iteration in range(trials + 3):
        started = time.perf_counter()
        prepared = prepare_frame(source, profile, clahe)
        ready = time.perf_counter()
        success, encoded = cv2.imencode(".jpg", prepared, [cv2.IMWRITE_JPEG_QUALITY, profile["quality"]])
        finished = time.perf_counter()
        if not success:
            raise RuntimeError("JPEG encoding failed")
        if iteration >= 3:
            processing.append((ready - started) * 1000)
            encoding.append((finished - ready) * 1000)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("JPEG read-back failed")
    restored = resize_pixels(decoded, source.shape[1], source.shape[0])
    summary = {
        "encoded_dimensions": [int(decoded.shape[1]), int(decoded.shape[0])],
        "jpeg_quality": profile["quality"], "jpeg_bytes": int(encoded.nbytes),
        "payload_kbps_at_requested_fps": encoded.nbytes * 8 * fps / 1000,
        "prepare_ms_p50": float(np.percentile(processing, 50)),
        "prepare_ms_p95": float(np.percentile(processing, 95)),
        "encode_ms_p50": float(np.percentile(encoding, 50)),
        "encode_ms_p95": float(np.percentile(encoding, 95)),
        "total_service_ms_p95": float(np.percentile(np.array(processing) + encoding, 95)),
        "jpeg_psnr_db_at_encoded_grid": psnr(prepared, decoded),
        "source_psnr_db_at_source_grid": psnr(source, restored),
    }
    return summary, encoded, restored


def write_image(path, pixels):
    if not cv2.imwrite(str(path), pixels):
        raise RuntimeError(f"Cannot write {path}")


def run_comparison(source, output, source_info, trials=30, fps=20.0):
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use a fresh empty output directory; previous evidence is never overwritten")
    height, width = source.shape[:2]
    crop = (width // 4, height // 4, width * 3 // 4, height * 3 // 4)
    x1, y1, x2, y2 = crop
    write_image(output / "source.png", source)
    write_image(output / "source-crop.png", source[y1:y2, x1:x2])
    profiles = {}
    for name, profile in PROFILES.items():
        metrics, encoded, restored = measure_profile(source, profile, trials, fps)
        (output / f"{name}.jpg").write_bytes(encoded.tobytes())
        write_image(output / f"{name}-source-grid-crop.png", restored[y1:y2, x1:x2])
        profiles[name] = metrics
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    report = {
        "measurement": "offline_same_source_frame_jpeg_fidelity", "source": source_info,
        "source_dimensions": [width, height], "source_pixels_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
        "crop_source_pixels_xyxy": crop, "trials_after_three_warmups": trials, "requested_fps": fps,
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "python": platform.python_version(), "opencv": cv2.__version__,
                 "opencv_threads": cv2.getNumThreads()},
        "git_revision": revision, "tool_sha256": sha256(__file__),
        "production_resize_sha256": sha256(ROOT / "src/classes/video_geometry.py"),
        "profiles": profiles,
        "limitations": [
            "Legacy profile is a reconstruction with nearest-neighbour 640x480, blur 5, CLAHE clip 2/grid 8, JPEG 50; not a capture of the old Pi process.",
            "Native candidates use production resize helpers; this is not an end-to-end backend/QGC measurement.",
            "Service time measures offline resize/preprocessing/JPEG only; excludes capture, tracking, network, queue and physical display latency.",
            "Payload estimates exclude transport overhead, other clients and frame-to-frame scene variation.",
            "PSNR compares matched pixel grids; contrast enhancement changes PSNR and it is not an operator quality score.",
            "1080p bounds never upscale a 720p input; synthetic 1080p is identified separately.",
            "No Raspberry Pi, radio throughput or hardware camera qualification claim.",
        ],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Offline same-frame fidelity measurement", "", f"Source: {source_info['kind']}, {width}×{height}.", "",
             "| Profile | Encoded pixels | JPEG KiB | Payload Mbps at selected FPS | Encode p95 ms | Source-grid PSNR dB |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, result in profiles.items():
        dims = '×'.join(map(str, result['encoded_dimensions']))
        quality = result['source_psnr_db_at_source_grid']
        quality_label = 'exact' if quality is None else f'{quality:.2f}'
        lines.append(f"| {name} | {dims} | {result['jpeg_bytes'] / 1024:.1f} | "
                     f"{result['payload_kbps_at_requested_fps'] / 1000:.2f} | {result['encode_ms_p95']:.2f} | "
                     f"{quality_label} |")
    lines.extend(["", *[f"- {item}" for item in report["limitations"]]])
    (output / "README.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="Local recorded video (no live camera connections)")
    source.add_argument("--synthetic-1080p", action="store_true")
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--fps", type=float, default=20)
    parser.add_argument("--opencv-threads", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.frame < 0 or not 1 <= args.trials <= 1000 or not 0 < args.fps <= 120 or not 1 <= args.opencv_threads <= 64:
        parser.error("Require nonnegative frame, 1..1000 trials, 0..120 FPS and 1..64 OpenCV threads")
    cv2.setNumThreads(args.opencv_threads)
    if args.video:
        pixels, info = read_recorded_frame(args.video, args.frame)
    else:
        pixels, info = synthetic_detail(), {"kind": "synthetic", "fixture": "deterministic1080p-detail-v1", "random_seed": 42}
    report = run_comparison(pixels, args.output, info, args.trials, args.fps)
    print(json.dumps({"report": str(args.output.expanduser().resolve() / "report.json"),
                      "source_dimensions": report["source_dimensions"], "profiles": report["profiles"]}, indent=2))


if __name__ == "__main__":
    main()
