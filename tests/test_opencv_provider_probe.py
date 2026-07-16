"""Executable ownership and fingerprint tests for the OpenCV provider probe."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROBE = PROJECT_ROOT / "scripts" / "setup" / "opencv_provider_probe.py"

pytestmark = [pytest.mark.unit]


def _record_hash(path: Path) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
    return "sha256=" + encoded.decode("ascii").rstrip("=")


def _site_packages(environment: Path) -> Path:
    result = subprocess.run(
        [str(environment / "bin" / "python"), "-c", "import site; print(site.getsitepackages()[0])"],
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _write_fake_cv2(site_packages: Path, *, gstreamer: bool) -> Path:
    package = site_packages / "cv2"
    package.mkdir()
    module = package / "__init__.py"
    module.write_text(
        "\n".join(
            (
                '__version__ = "4.13.0"',
                "def getBuildInformation():",
                f'    return "FFMPEG: YES\\nGStreamer: {"YES" if gstreamer else "NO"}\\n"',
                "def TrackerCSRT_create(): return object()",
                "def TrackerKCF_create(): return object()",
                "",
            )
        ),
        encoding="utf-8",
    )
    return module


def _write_wheel_owner(site_packages: Path, name: str = "opencv-contrib-python-headless") -> Path:
    normalized = name.replace("-", "_")
    dist_info = site_packages / f"{normalized}-4.13.0.dist-info"
    dist_info.mkdir()
    metadata_file = dist_info / "METADATA"
    metadata_file.write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 4.13.0\n",
        encoding="utf-8",
    )
    native_dir = site_packages / f"{normalized}.libs"
    native_dir.mkdir(exist_ok=True)
    native_file = native_dir / "libfake.so"
    native_file.write_bytes(b"native-provider")
    module = site_packages / "cv2" / "__init__.py"
    record = dist_info / "RECORD"
    rows = []
    for path in (module, native_file, metadata_file):
        rows.append(
            (
                path.relative_to(site_packages).as_posix(),
                _record_hash(path),
                str(path.stat().st_size),
            )
        )
    rows.append((record.relative_to(site_packages).as_posix(), "", ""))
    with record.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    return native_file


@pytest.fixture
def fake_venv(tmp_path: Path) -> tuple[Path, Path]:
    environment = tmp_path / "venv"
    venv.EnvBuilder(with_pip=False).create(environment)
    return environment, _site_packages(environment)


def _run_probe(environment: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(environment / "bin" / "python"), str(PROBE)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_managed_wheel_verifies_complete_record_and_native_libraries(fake_venv):
    environment, site_packages = fake_venv
    _write_fake_cv2(site_packages, gstreamer=False)
    native = _write_wheel_owner(site_packages)

    result = _run_probe(environment)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["provider_kind"] == "managed_wheel"
    assert payload["distribution_owners"]["opencv-contrib-python-headless"][
        "record_verified"
    ]
    paths = {item["path"] for item in payload["fingerprinted_files"]}
    assert str(native.resolve()) in paths


@pytest.mark.parametrize("mutation", ["native", "module", "overlay"])
def test_managed_wheel_rejects_record_mutation_or_unowned_overlay(fake_venv, mutation):
    environment, site_packages = fake_venv
    module = _write_fake_cv2(site_packages, gstreamer=False)
    native = _write_wheel_owner(site_packages)
    if mutation == "native":
        native.write_bytes(b"mutated-native-provider")
    elif mutation == "module":
        module.write_text(module.read_text(encoding="utf-8") + "# overlay\n", encoding="utf-8")
    else:
        (module.parent / "foreign.py").write_text("overlay = True\n", encoding="utf-8")

    result = _run_probe(environment)

    assert result.returncode != 0
    assert "mismatch" in result.stderr or "unowned overlay" in result.stderr


def test_probe_rejects_multiple_or_foreign_cv2_metadata_owners(fake_venv):
    environment, site_packages = fake_venv
    _write_fake_cv2(site_packages, gstreamer=False)
    _write_wheel_owner(site_packages)
    _write_wheel_owner(site_packages, "foreign-cv-provider")

    result = _run_probe(environment)

    assert result.returncode != 0
    assert "multiple OpenCV distribution owners" in result.stderr


def test_probe_rejects_stale_known_opencv_metadata_without_cv2_record(fake_venv):
    environment, site_packages = fake_venv
    _write_fake_cv2(site_packages, gstreamer=False)
    _write_wheel_owner(site_packages)
    stale = site_packages / "opencv_python-4.13.0.dist-info"
    stale.mkdir()
    (stale / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: opencv-python\nVersion: 4.13.0\n",
        encoding="utf-8",
    )

    result = _run_probe(environment)

    assert result.returncode != 0
    assert "multiple OpenCV distribution owners" in result.stderr


def test_source_provider_fingerprints_native_layout_and_rejects_escape(fake_venv, tmp_path):
    environment, site_packages = fake_venv
    module = _write_fake_cv2(site_packages, gstreamer=True)
    native = environment / "lib" / "libopencv_core.so.4.13"
    native.write_bytes(b"source-native")

    first = _run_probe(environment)
    assert first.returncode == 0, first.stdout + first.stderr
    first_payload = json.loads(first.stdout)
    assert first_payload["provider_kind"] == "source_gstreamer"
    assert str(native) in {item["path"] for item in first_payload["fingerprinted_files"]}

    native.write_bytes(b"changed-source-native")
    second = _run_probe(environment)
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout != second.stdout

    victim = tmp_path / "outside.so"
    victim.write_bytes(b"outside")
    os.symlink(victim, module.parent / "escape.so")
    escaped = _run_probe(environment)
    assert escaped.returncode != 0
    assert "escapes the selected venv" in escaped.stderr


def test_source_provider_symlink_fingerprint_includes_target_content(fake_venv):
    environment, site_packages = fake_venv
    _write_fake_cv2(site_packages, gstreamer=True)
    native = environment / "lib" / "libopencv_core.so.4.13"
    native.write_bytes(b"source-native")
    alias = environment / "lib" / "libopencv_core.so"
    alias.symlink_to(native.name)

    first = _run_probe(environment)
    assert first.returncode == 0, first.stdout + first.stderr
    first_payload = json.loads(first.stdout)
    alias_evidence = next(
        item for item in first_payload["fingerprinted_files"] if item["path"] == str(alias)
    )
    assert alias_evidence["target_sha256"] == hashlib.sha256(b"source-native").hexdigest()

    native.write_bytes(b"changed-through-target")
    second = _run_probe(environment)
    assert second.returncode == 0, second.stdout + second.stderr
    assert first.stdout != second.stdout
