"""Contract tests for the guarded production-remote browser evidence harness."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml


pytestmark = [pytest.mark.unit]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = PROJECT_ROOT / "tools" / "run_production_remote_browser_e2e.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "run_production_remote_browser_e2e",
        HARNESS_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dry_run_is_side_effect_free_and_explicit_about_claim_boundary(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry-run"
    assert "self-signed HTTPS" in payload["claim_boundary"]
    assert "PX4/SITL/HIL" in payload["claim_boundary"]
    assert "retained-evidence secret scan" in payload["checks"]
    assert not (tmp_path / "artifacts").exists()


def test_execute_requires_explicit_self_signed_tls_consent():
    harness = _load_harness()
    args = SimpleNamespace(
        execute_browser=True,
        allow_local_self_signed_tls=False,
        public_host=harness.DEFAULT_PUBLIC_HOST,
    )

    with pytest.raises(harness.HarnessError, match="allow-local-self-signed-tls"):
        harness.validate_execute_consent(args)


def test_execute_is_pinned_to_reserved_local_test_host():
    harness = _load_harness()
    args = SimpleNamespace(
        execute_browser=True,
        allow_local_self_signed_tls=True,
        public_host="deployment.example",
    )

    with pytest.raises(harness.HarnessError, match="pixeagle.test"):
        harness.validate_execute_consent(args)


def test_execute_rejects_custom_dashboard_build_directory(tmp_path):
    harness = _load_harness()
    args = SimpleNamespace(
        execute_browser=True,
        allow_local_self_signed_tls=True,
        public_host=harness.DEFAULT_PUBLIC_HOST,
        dashboard_build_dir=tmp_path,
    )

    with pytest.raises(harness.HarnessError, match="current checkout"):
        harness.validate_execute_consent(args)


def test_static_file_resolution_rejects_path_traversal(tmp_path):
    harness = _load_harness()
    build = tmp_path / "build"
    build.mkdir()
    (build / "index.html").write_text("ok", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("not public", encoding="utf-8")

    assert harness.safe_static_file(build, "index.html") == build / "index.html"
    assert harness.safe_static_file(build, "../secret.txt") is None


def test_retained_evidence_secret_scan_reports_types_without_values(tmp_path):
    harness = _load_harness()
    (tmp_path / "safe.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    (tmp_path / "unsafe.json").write_text(
        '{"password":"do-not-echo"}\n',
        encoding="utf-8",
    )

    result = harness.scan_retained_evidence_for_secrets(tmp_path)

    assert result["passed"] is False
    assert result["values_echoed"] is False
    assert result["findings"] == [
        {"path": "unsafe.json", "type": "password_field"}
    ]
    assert "do-not-echo" not in json.dumps(result)


def test_retained_evidence_secret_scan_checks_exact_values_in_binary_files(tmp_path):
    harness = _load_harness()
    actual_secret = "generated-secret-without-a-label"
    (tmp_path / "artifact.bin").write_bytes(
        b"\x00binary-prefix\xff" + actual_secret.encode("utf-8") + b"\x00"
    )

    result = harness.scan_retained_evidence_for_secrets(
        tmp_path,
        secret_values=[actual_secret],
    )

    assert result["passed"] is False
    assert result["findings"] == [
        {"path": "artifact.bin", "type": "exact_generated_secret_1"}
    ]
    assert actual_secret not in json.dumps(result)


def test_sanitized_upload_bundle_excludes_raw_logs_and_audit_events(tmp_path):
    harness = _load_harness()
    harness.write_json(tmp_path / "manifest.json", {"accepted": True})
    harness.write_json(tmp_path / "browser" / "browser-results.json", {"passed": True})
    (tmp_path / "browser" / "playwright.log").write_text(
        "raw process output",
        encoding="utf-8",
    )
    (tmp_path / "audit").mkdir(parents=True)
    (tmp_path / "audit" / "security_audit.jsonl").write_text(
        '{"event":"raw"}\n',
        encoding="utf-8",
    )

    harness.create_sanitized_upload_bundle(
        tmp_path,
        accepted=True,
        secret_scan_passed=True,
    )

    assert (tmp_path / "upload" / "manifest.json").is_file()
    assert (tmp_path / "upload" / "browser" / "browser-results.json").is_file()
    assert not (tmp_path / "upload" / "browser" / "playwright.log").exists()
    assert not (tmp_path / "upload" / "audit" / "security_audit.jsonl").exists()


def test_failed_secret_scan_upload_bundle_is_minimal(tmp_path):
    harness = _load_harness()
    harness.write_json(tmp_path / "manifest.json", {"accepted": False})
    harness.write_json(
        tmp_path / "security" / "secret-scan.json",
        {"passed": False, "findings": [{"type": "exact_generated_secret_1"}]},
    )

    harness.create_sanitized_upload_bundle(
        tmp_path,
        accepted=False,
        secret_scan_passed=False,
    )

    uploaded = sorted(
        path.relative_to(tmp_path / "upload").as_posix()
        for path in (tmp_path / "upload").rglob("*")
        if path.is_file()
    )
    assert uploaded == ["security/secret-scan.json", "upload-status.json"]


def test_finalize_evidence_scans_final_manifest_and_blocks_upload(tmp_path):
    harness = _load_harness()
    actual_secret = "exception-only-generated-secret"
    manifest = {
        "checks": {"browser": {"passed": True}},
        "error": {"message": actual_secret},
    }

    harness.finalize_evidence(
        run_dir=tmp_path,
        manifest=manifest,
        secret_values=[actual_secret],
    )

    retained_manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    secret_scan = json.loads(
        (tmp_path / "security" / "secret-scan.json").read_text(encoding="utf-8")
    )
    uploaded = sorted(
        path.relative_to(tmp_path / "upload").as_posix()
        for path in (tmp_path / "upload").rglob("*")
        if path.is_file()
    )
    assert retained_manifest["accepted"] is False
    assert secret_scan["passed"] is False
    assert {"path": "manifest.json", "type": "exact_generated_secret_1"} in (
        secret_scan["raw_retained_artifacts"]["findings"]
    )
    assert uploaded == ["security/secret-scan.json", "upload-status.json"]


def test_execute_prerequisites_default_to_playwright_managed_chromium(
    tmp_path,
    monkeypatch,
):
    harness = _load_harness()
    build = tmp_path / "build"
    build.mkdir()
    index = build / "index.html"
    index.write_text("current build", encoding="utf-8")
    os.utime(index, (4_102_444_800, 4_102_444_800))
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", raising=False)
    monkeypatch.setattr(harness.shutil, "which", lambda _command: "/usr/bin/tool")
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    selected = harness.ensure_execute_prerequisites(
        SimpleNamespace(dashboard_build_dir=build)
    )

    assert selected is None


def test_execute_prerequisites_report_missing_playwright_chromium(
    tmp_path,
    monkeypatch,
):
    harness = _load_harness()
    build = tmp_path / "build"
    build.mkdir()
    index = build / "index.html"
    index.write_text("current build", encoding="utf-8")
    os.utime(index, (4_102_444_800, 4_102_444_800))
    monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", raising=False)
    monkeypatch.setattr(harness.shutil, "which", lambda _command: "/usr/bin/tool")
    monkeypatch.setattr(
        harness.subprocess,
        "run",
        MagicMock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                SimpleNamespace(returncode=1, stdout="", stderr=""),
            ]
        ),
    )

    with pytest.raises(
        harness.HarnessError,
        match="make production-remote-browser-install",
    ):
        harness.ensure_execute_prerequisites(
            SimpleNamespace(dashboard_build_dir=build)
        )


def test_managed_browser_metadata_records_version_revision_and_hash():
    harness = _load_harness()

    metadata = harness.playwright_managed_browser_metadata()

    assert metadata["name"] == "chromium"
    assert metadata["version"]
    assert metadata["revision"]
    assert len(metadata["metadata_sha256"]) == 64


def test_dashboard_build_timeout_is_reported_without_hanging(tmp_path, monkeypatch):
    harness = _load_harness()

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["npm", "run", "build"],
            timeout=1,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(harness.subprocess, "run", raise_timeout)
    args = SimpleNamespace(dashboard_build_timeout_s=1)

    with pytest.raises(harness.HarnessError, match="exceeded 1s"):
        harness.build_current_dashboard(args, tmp_path)

    assert (tmp_path / "dashboard-build.log").read_text(encoding="utf-8") == (
        "partial stdoutpartial stderr"
    )


def test_playwright_contract_disables_secret_prone_artifacts_and_checks_proxy_boundary():
    config = (PROJECT_ROOT / "dashboard" / "playwright.config.js").read_text(
        encoding="utf-8"
    )
    spec = (
        PROJECT_ROOT / "dashboard" / "e2e" / "production-remote.spec.js"
    ).read_text(encoding="utf-8")
    package = json.loads(
        (PROJECT_ROOT / "dashboard" / "package.json").read_text(encoding="utf-8")
    )

    assert package["devDependencies"]["@playwright/test"] == "1.61.0"
    assert "trace: 'off'" in config
    assert "video: 'off'" in config
    assert "ignoreHTTPSErrors: true" in config
    assert "--host-resolver-rules=MAP" in config
    assert "unexpectedAuthorityRequests" in spec
    assert "unexpectedPathRequests" in spec
    assert "websocket-ledger.json" in spec
    assert "response-ledger.json" in spec
    assert "request-failures.json" in spec
    assert "PIXEAGLE_E2E_SECRET_HANDOFF_FILE" in spec
    assert "?token=not-real" in spec
    assert "approvedDashboardRoutes" in spec
    assert "approvedApiPaths" in spec
    assert "approvedWebSocketPaths" in spec
    assert "unexpectedErrorResponses" in spec
    assert "logout_closes_existing_mjpeg" in spec
    assert "logout_closes_existing_websocket" in spec
    assert "session_bound_csrf" in spec
    assert "pixeagle_session" in spec


def test_make_and_ci_keep_browser_execution_explicit_and_opt_in():
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    workflow_path = (
        PROJECT_ROOT
        / ".github"
        / "workflows"
        / "production-remote-browser-e2e.yml"
    )
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert "production-remote-browser-e2e-dry-run:" in makefile
    assert "production-remote-browser-install:" in makefile
    assert "playwright install --with-deps chromium" in makefile
    assert "production-remote-browser-e2e:" in makefile
    assert 'ALLOW_LOCAL_SELF_SIGNED_TLS)" != "1"' in makefile
    assert "--allow-local-self-signed-tls" in makefile
    assert workflow.get(True) == {"workflow_dispatch": None}
    assert "push:" not in workflow_text
    assert "pull_request:" not in workflow_text
    assert "npx playwright install --with-deps chromium" in workflow_text
    assert "reports/production-remote-browser/*/upload/" in workflow_text
    assert "dashboard/build" not in workflow_text
    assert "retention-days: 14" in workflow_text


def test_harness_uses_bounded_process_group_and_server_cleanup():
    source = HARNESS_PATH.read_text(encoding="utf-8")

    assert "start_new_session=os.name == \"posix\"" in source
    assert "os.killpg(process.pid, signal.SIGTERM)" in source
    assert "os.killpg(process.pid, signal.SIGKILL)" in source
    assert "await asyncio.wait(pending, timeout=2)" in source
    assert "await process.communicate()" not in source
