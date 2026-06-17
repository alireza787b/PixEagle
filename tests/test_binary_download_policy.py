"""Guards for setup binary download provenance and pinning policy."""

from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "scripts" / "setup" / "binary-manifest.env"
LINUX_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "download-binaries.sh"
WINDOWS_SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "download-binaries.bat"
POLICY_DOC = PROJECT_ROOT / "docs" / "setup" / "binary-download-policy.md"


def _read_manifest() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_binary_manifest_pins_versions_assets_and_sha256s():
    values = _read_manifest()

    assert values["PIXEAGLE_BINARY_MAVSDK_VERSION"] == "v3.12.0"
    assert values["PIXEAGLE_BINARY_MAVLINK2REST_VERSION"] == "1.0.0"

    for prefix in ["PIXEAGLE_BINARY_MAVSDK", "PIXEAGLE_BINARY_MAVLINK2REST"]:
        assert values[f"{prefix}_BASE_URL"].startswith("https://github.com/mavlink/")
        assert values[f"{prefix}_RELEASE_URL"].startswith("https://github.com/mavlink/")

    for platform_key in [
        "LINUX_X86_64",
        "LINUX_ARM64",
        "LINUX_ARMV7",
        "LINUX_ARMV6",
        "MACOS_X64",
        "MACOS_ARM64",
    ]:
        assert values[f"PIXEAGLE_BINARY_MAVSDK_ASSET_{platform_key}"]
        assert len(values[f"PIXEAGLE_BINARY_MAVSDK_SHA256_{platform_key}"]) == 64
        assert values[f"PIXEAGLE_BINARY_MAVLINK2REST_ASSET_{platform_key}"]
        assert len(values[f"PIXEAGLE_BINARY_MAVLINK2REST_SHA256_{platform_key}"]) == 64

    assert values["PIXEAGLE_BINARY_MAVSDK_ASSET_WINDOWS_X86_64"].endswith(".exe")
    assert len(values["PIXEAGLE_BINARY_MAVSDK_SHA256_WINDOWS_X86_64"]) == 64
    assert values["PIXEAGLE_BINARY_MAVLINK2REST_ASSET_WINDOWS_X86_64"].endswith(
        ".exe"
    )
    assert (
        len(values["PIXEAGLE_BINARY_MAVLINK2REST_SHA256_WINDOWS_X86_64"]) == 64
    )


def test_linux_downloader_dry_run_uses_manifest_without_writes():
    result = subprocess.run(
        ["bash", str(LINUX_SCRIPT), "--all", "--dry-run"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Dry-Run Download Plan" in stdout
    assert "mavsdk_server_musl_x86_64" in stdout
    assert "mavlink2rest-x86_64-unknown-linux-musl" in stdout
    assert "Expected SHA256" in stdout
    assert "no files were downloaded or modified" in stdout
    assert "Download failed" not in stdout


def test_linux_downloader_fails_closed_for_checksum_and_records_provenance():
    script = LINUX_SCRIPT.read_text(encoding="utf-8")

    assert "load_binary_manifest || exit 1" in script
    assert "SHA256 mismatch" in script
    assert "rm -f \"$temp_file\"" in script
    assert "record_provenance" in script
    assert "binary-provenance.jsonl" in script
    assert "PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1" in script
    assert "exit 1" in script


def test_windows_downloader_uses_manifest_without_fallback_tags():
    script = WINDOWS_SCRIPT.read_text(encoding="utf-8")

    assert "binary-manifest.env" in script
    assert "certutil -hashfile" in script
    assert "binary-provenance.jsonl" in script
    assert "--dry-run" in script
    assert "PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1" in script
    assert "TAG_CANDIDATES" not in script
    assert "ASSET_CANDIDATES" not in script
    assert "fallback release tags" in script


def test_binary_download_policy_is_linked_and_documents_limits():
    policy = POLICY_DOC.read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (PROJECT_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    install_doc = (PROJECT_ROOT / "docs" / "INSTALLATION.md").read_text(
        encoding="utf-8"
    )
    windows_doc = (PROJECT_ROOT / "docs" / "WINDOWS_SETUP.md").read_text(
        encoding="utf-8"
    )

    for required in [
        "scripts/setup/binary-manifest.env",
        "SHA-256",
        "bin/binary-provenance.jsonl",
        "not prove MAVSDK connectivity",
        "PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1",
        "not acceptable for production",
        "certutil -hashfile",
    ]:
        assert required in policy

    assert "Binary Download Policy" in readme
    assert "Binary Download Policy" in docs_index
    assert "binary-manifest.env" in install_doc
    assert "fallback release tags" in windows_doc


def test_init_scripts_do_not_bypass_binary_manifest_verification():
    linux_init = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    windows_init = (PROJECT_ROOT / "scripts" / "init.bat").read_text(encoding="utf-8")

    assert "verifying manifest checksum" in linux_init
    assert "bash \"$download_script\" --mavsdk" in linux_init
    assert "bash \"$download_script\" --mavlink2rest" in linux_init
    assert '|| [[ -f "$PIXEAGLE_DIR/mavsdk_server_bin" ]]' not in linux_init
    assert '|| [[ -f "$PIXEAGLE_DIR/mavlink2rest" ]]' not in linux_init

    assert "verifying manifest checksum" in windows_init
    assert 'call "%MAVSDK_SCRIPT%" --mavsdk' in windows_init
    assert 'call "%M2R_SCRIPT%" --mavlink2rest' in windows_init
    assert 'if exist "%PIXEAGLE_DIR%\\mavsdk_server_bin.exe" set "MAVSDK_STATUS' not in windows_init
    assert 'if exist "%PIXEAGLE_DIR%\\mavlink2rest.exe" set "M2R_STATUS' not in windows_init
