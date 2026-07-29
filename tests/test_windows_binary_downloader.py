"""Focused native-Windows downloader contract and behavioral tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_DOWNLOADER = (
    PROJECT_ROOT / "scripts" / "setup" / "download-binaries.ps1"
)
BATCH_WRAPPER = PROJECT_ROOT / "scripts" / "setup" / "download-binaries.bat"
POWERSHELL = shutil.which("powershell.exe") if os.name == "nt" else None


def _minimal_x64_pe(marker: int = 0) -> bytes:
    """Return a small structurally valid PE32+ x64 fixture."""

    image = bytearray(256)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x40)
    image[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", image, 0x44, 0x8664)
    struct.pack_into("<H", image, 0x46, 1)
    struct.pack_into("<H", image, 0x54, 0x70)
    struct.pack_into("<H", image, 0x56, 0x0002)
    struct.pack_into("<H", image, 0x58, 0x020B)
    struct.pack_into("<I", image, 0x58 + 56, 0x1000)
    image[-1] = marker
    return bytes(image)


def _write_test_checkout(
    tmp_path: Path,
    *,
    expected_binary: bytes,
    existing_binary: bytes | None,
) -> tuple[Path, Path]:
    setup_dir = tmp_path / "scripts" / "setup"
    setup_dir.mkdir(parents=True)
    script = setup_dir / POWERSHELL_DOWNLOADER.name
    shutil.copyfile(POWERSHELL_DOWNLOADER, script)

    expected_sha = hashlib.sha256(expected_binary).hexdigest()
    (setup_dir / "binary-manifest.env").write_text(
        "\n".join(
            [
                "PIXEAGLE_BINARY_MAVSDK_VERSION=v-test",
                "PIXEAGLE_BINARY_MAVSDK_BASE_URL=https://example.invalid/releases",
                "PIXEAGLE_BINARY_MAVSDK_RELEASE_URL=https://example.invalid/releases/v-test",
                "PIXEAGLE_BINARY_MAVSDK_ASSET_WINDOWS_X86_64=mavsdk-test.exe",
                f"PIXEAGLE_BINARY_MAVSDK_SHA256_WINDOWS_X86_64={expected_sha}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    binary_path = tmp_path / "bin" / "mavsdk_server_bin.exe"
    if existing_binary is not None:
        binary_path.parent.mkdir()
        binary_path.write_bytes(existing_binary)
    return script, binary_path


def _run_downloader(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    env = os.environ.copy()
    env["PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS"] = "1"
    return subprocess.run(
        [
            POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(script),
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_powershell_source_owns_the_hardened_transaction():
    source = POWERSHELL_DOWNLOADER.read_text(encoding="utf-8")

    required_contracts = [
        "PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS",
        "WINDOWS_X86_64",
        "binary-manifest.env",
        "[System.IO.FileShare]::None",
        "[System.IO.FileMode]::CreateNew",
        "[Guid]::NewGuid()",
        "Get-FileHash",
        "Assert-X64PeImage",
        "[System.IO.File]::Move(",
        "ConvertTo-Json",
        "binary-provenance.jsonl",
    ]
    for contract in required_contracts:
        assert contract in source

    forbidden_patterns = [
        "Invoke-Expression",
        "Start-Process",
        "cmd.exe",
        "Move-Item -Force",
        "Remove-Item",
        "PIXEAGLE_ALLOW_UNVERIFIED_BINARY",
        "WINDOWS_ARM64",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source


def test_batch_file_is_only_a_known_argument_compatibility_wrapper():
    source = BATCH_WRAPPER.read_text(encoding="utf-8")

    for argument in [
        "--all",
        "--mavsdk",
        "--mavlink2rest",
        "--dry-run",
    ]:
        assert argument in source
    assert "download-binaries.ps1" in source
    assert "powershell.exe" in source

    for implementation_detail in [
        "certutil",
        "Invoke-WebRequest",
        "binary-manifest.env",
        "binary-provenance.jsonl",
        "move /y",
        "del /",
    ]:
        assert implementation_detail.lower() not in source.lower()


@pytest.mark.skipif(POWERSHELL is None, reason="native Windows PowerShell unavailable")
def test_dry_run_does_not_create_bin_directory(tmp_path: Path):
    expected = _minimal_x64_pe()
    script, _ = _write_test_checkout(
        tmp_path,
        expected_binary=expected,
        existing_binary=None,
    )

    result = _run_downloader(script, "-Mavsdk", "-DryRun")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no files or directories were modified" in result.stdout
    assert not (tmp_path / "bin").exists()


@pytest.mark.skipif(POWERSHELL is None, reason="native Windows PowerShell unavailable")
def test_verified_existing_binary_is_kept_and_jsonl_is_valid(tmp_path: Path):
    expected = _minimal_x64_pe()
    script, binary_path = _write_test_checkout(
        tmp_path,
        expected_binary=expected,
        existing_binary=expected,
    )

    result = _run_downloader(script, "-Mavsdk")

    assert result.returncode == 0, result.stdout + result.stderr
    assert binary_path.read_bytes() == expected
    provenance_path = tmp_path / "bin" / "binary-provenance.jsonl"
    records = [
        json.loads(line)
        for line in provenance_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(records) == 1
    assert records[0]["platform_key"] == "WINDOWS_X86_64"
    assert records[0]["verification_mode"] == "existing_sha256_pe_x64"
    assert records[0]["actual_sha256"] == hashlib.sha256(expected).hexdigest()
    assert records[0]["output_path"] == str(binary_path.resolve())


@pytest.mark.skipif(POWERSHELL is None, reason="native Windows PowerShell unavailable")
def test_mismatched_existing_binary_is_never_replaced(tmp_path: Path):
    expected = _minimal_x64_pe(marker=1)
    operator_file = _minimal_x64_pe(marker=2)
    script, binary_path = _write_test_checkout(
        tmp_path,
        expected_binary=expected,
        existing_binary=operator_file,
    )

    result = _run_downloader(script, "-Mavsdk")

    assert result.returncode != 0
    assert "left untouched" in result.stdout
    assert binary_path.read_bytes() == operator_file
    assert not (tmp_path / "bin" / "binary-provenance.jsonl").exists()
