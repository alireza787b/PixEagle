#!/usr/bin/env python3
"""Collect local HTTPS/browser evidence for the production remote profile.

The default mode is side-effect-free. Execution is explicit and starts only
harness-owned loopback processes. It never installs a proxy, changes firewall
rules, starts PX4, or claims deployment/field readiness.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import suppress
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
import logging
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any, Iterable
import warnings

from fastapi import FastAPI, Request, Response, WebSocket, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
import httpx
from ruamel.yaml import YAML
import uvicorn
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

if TYPE_CHECKING:
    from classes.api_auth_runtime import APIAuthRuntime
    from classes.api_exposure_policy import APIExposurePolicy
    from classes.fastapi_handler import FastAPIHandler


DEFAULT_PUBLIC_HOST = "pixeagle.test"
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "reports" / "production-remote-browser"
DEFAULT_DASHBOARD_BUILD = PROJECT_ROOT / "dashboard" / "build"
DEFAULT_SESSION_COOKIE_NAME = "pixeagle_session"
EVIDENCE_SOURCE_FILES = (
    Path("tools/run_production_remote_browser_e2e.py"),
    Path("scripts/setup/apply-setup-profile.py"),
    Path("src/classes/api_auth_runtime.py"),
    Path("src/classes/api_exposure_policy.py"),
    Path("src/classes/api_security_audit.py"),
    Path("src/classes/api_security_policy.py"),
    Path("src/classes/fastapi_handler.py"),
    Path("src/classes/webrtc_manager.py"),
    Path("dashboard/e2e/production-remote.spec.js"),
    Path("dashboard/playwright.config.js"),
    Path("dashboard/src/services/apiClient.js"),
    Path("dashboard/src/services/apiEndpoints.js"),
)
CLAIM_BOUNDARY = (
    "Local self-signed HTTPS reverse-proxy and browser-policy evidence only. "
    "This is not target deployment, trusted-certificate, firewall, PX4/SITL/HIL, "
    "field, or real-aircraft evidence."
)
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
FORWARDED_HTTP_HEADERS = {
    "accept",
    "authorization",
    "cache-control",
    "content-type",
    "cookie",
    "expires",
    "idempotency-key",
    "origin",
    "pragma",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
    "x-pixeagle-csrf",
    "x-request-id",
}
SECRET_PATTERNS = (
    ("password_field", re.compile(r'"password"\s*:', re.IGNORECASE)),
    ("authorization_header", re.compile(r"\bauthorization\s*:", re.IGNORECASE)),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    ("session_cookie_value", re.compile(r"pixeagle_session\s*=", re.IGNORECASE)),
    ("pbkdf2_hash", re.compile(r"pbkdf2_sha256\$", re.IGNORECASE)),
)
ONE_PIXEL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////"
    "////////////////////////////////////2wBDAf//////////////////////////////"
    "////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAA"
    "AAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAA"
    "AAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF/"
    "/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAA"
    "AP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIA"
    "AwAAABD/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAA"
    "AAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q=="
)


def config_sync_v2_fixture() -> dict[str, Any]:
    """Return a complete no-op Config Sync v2 report for browser evidence."""
    return {
        "contract_version": 2,
        "new_parameters": [],
        "changed_defaults": [],
        "registered_retirements": [],
        "unknown_extensions": [],
        "counts": {
            "new": 0,
            "changed": 0,
            "retired": 0,
            "extensions": 0,
            "actionable": 0,
        },
        "baseline_available": True,
        "baseline_saved_at": "2026-01-01T00:00:00Z",
        "schema_version": "evidence-fixture-v2",
        "retirement_registry_version": 1,
        "retirement_registry_digest": "0" * 64,
    }


def config_schema_fixture() -> dict[str, Any]:
    """Return the smallest current schema contract needed by the browser gate."""
    return {
        "version": "evidence-fixture-v1",
        "sections": {
            "Evidence": {
                "category": "system",
                "parameters": {},
            }
        },
    }


def config_runtime_status_fixture() -> dict[str, Any]:
    """Return a current, inert pending-restart status for browser evidence."""
    return {
        "schema_version": 1,
        "source": "config_service",
        "startup_config_source": "checked_in_defaults",
        "persisted_config_source": "checked_in_defaults",
        "persisted_config_digest": "0" * 64,
        "startup_snapshot_timestamp": 1_767_225_600.0,
        "startup_snapshot_immutable": True,
        "system_restart_policy": "local_only",
        "restart_required": False,
        "pending_change_count": 0,
        "pending_changes": [],
        "restart_action": {
            "path": "/api/v1/actions/system-restart",
            "available": False,
            "reason": "no_pending_system_restart_changes",
            "requires_confirmation": True,
            "requires_idempotency_key": True,
        },
        "claim_boundary": "Inert browser evidence fixture; no process restart is executed.",
        "timestamp": 1_767_225_600.0,
    }


class HarnessError(RuntimeError):
    """Raised when guarded local evidence collection cannot proceed."""


class HarnessFramePublisher:
    """Deterministic inert frame publisher for production media handlers."""

    def __init__(self) -> None:
        self.client_count = 0
        self.frame_id = 0

    def register_client(self) -> None:
        self.client_count += 1

    def unregister_client(self) -> None:
        self.client_count = max(0, self.client_count - 1)

    def get_latest(self, *, prefer_osd: bool = True) -> Any:
        _ = prefer_osd
        self.frame_id += 1
        return type(
            "HarnessStampedFrame",
            (),
            {
                "frame": None,
                "frame_id": self.frame_id,
                "timestamp": asyncio.get_running_loop().time(),
                "is_osd": True,
            },
        )()


class HarnessQualityEngine:
    """Small deterministic quality-state adapter for WebSocket lifecycle tests."""

    def __init__(self) -> None:
        self.clients: dict[str, dict[str, Any]] = {}

    def register_client(self, client_id: str, quality: int) -> None:
        self.clients[client_id] = {"quality": int(quality)}

    def unregister_client(self, client_id: str) -> None:
        self.clients.pop(client_id, None)

    def set_client_quality(self, client_id: str, quality: int) -> None:
        if client_id in self.clients:
            self.clients[client_id]["quality"] = int(quality)

    def report_frame_sent(
        self,
        client_id: str,
        bytes_sent: int,
        encode_time: float,
    ) -> int:
        _ = bytes_sent, encode_time
        return int(self.clients.get(client_id, {}).get("quality", 50))

    def get_all_states(self) -> dict[str, Any]:
        return {"clients": dict(self.clients), "source": "local_evidence_harness"}


class HarnessStreamOptimizer:
    """Deterministic inert encoder used through production media handlers."""

    frame_cache: dict[Any, Any] = {}

    async def encode_frame_async(
        self,
        frame: Any,
        frame_id: int,
        quality: int,
    ) -> bytes:
        _ = frame, frame_id, quality
        return ONE_PIXEL_JPEG


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_manifest_hash(root: Path) -> tuple[str, int]:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            f"{path.relative_to(root).as_posix()}:{sha256_file(path)}"
        )
    payload = "\n".join(entries).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), len(entries)


def command_version(command: list[str], *, cwd: Path = PROJECT_ROOT) -> str | None:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def playwright_managed_browser_metadata() -> dict[str, Any]:
    metadata_path = (
        PROJECT_ROOT
        / "dashboard"
        / "node_modules"
        / "playwright-core"
        / "browsers.json"
    )
    if not metadata_path.is_file():
        return {
            "name": "chromium",
            "revision": None,
            "version": None,
            "metadata_sha256": None,
        }
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    browser = next(
        (
            item
            for item in payload.get("browsers", [])
            if item.get("name") == "chromium"
        ),
        {},
    )
    return {
        "name": "chromium",
        "revision": browser.get("revision"),
        "version": browser.get("browserVersion"),
        "metadata_sha256": sha256_file(metadata_path),
    }


def version_evidence(
    *,
    dashboard_build_dir: Path,
    browser_executable: Path | None,
) -> dict[str, Any]:
    build_hash, build_file_count = directory_manifest_hash(dashboard_build_dir)
    managed_browser = playwright_managed_browser_metadata()
    git_head = command_version(["git", "rev-parse", "HEAD"])
    git_status = subprocess.run(
        ["git", "status", "--short"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "collected_at": utc_now(),
        "git_head": git_head,
        "git_worktree_clean": not bool(git_status.stdout.strip()),
        "python": sys.version.split()[0],
        "node": command_version(["node", "--version"]),
        "npm": command_version(["npm", "--version"]),
        "playwright": command_version(
            ["npx", "playwright", "--version"],
            cwd=PROJECT_ROOT / "dashboard",
        ),
        "browser_executable": str(browser_executable) if browser_executable else "playwright-managed",
        "browser_version": (
            command_version([str(browser_executable), "--version"])
            if browser_executable
            else managed_browser["version"]
        ),
        "browser_revision": None if browser_executable else managed_browser["revision"],
        "playwright_browser_metadata_sha256": (
            None if browser_executable else managed_browser["metadata_sha256"]
        ),
        "openssl": command_version(["openssl", "version"]),
        "python_requirements_sha256": sha256_file(PROJECT_ROOT / "requirements.txt"),
        "dashboard_package_lock_sha256": sha256_file(
            PROJECT_ROOT / "dashboard" / "package-lock.json"
        ),
        "dashboard_build_manifest_sha256": build_hash,
        "dashboard_build_file_count": build_file_count,
        "source_sha256": {
            path.as_posix(): sha256_file(PROJECT_ROOT / path)
            for path in EVIDENCE_SOURCE_FILES
        },
        "python_packages": {
            distribution.metadata["Name"]: distribution.version
            for distribution in sorted(
                distributions(),
                key=lambda item: str(item.metadata["Name"]).lower(),
            )
            if distribution.metadata["Name"]
        },
        "claim_boundary": CLAIM_BOUNDARY,
    }


def choose_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
        handle.bind(("127.0.0.1", 0))
        return int(handle.getsockname()[1])


def authority(host: str, port: int) -> str:
    return f"{host}:{port}"


def build_dry_run_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "claim_boundary": CLAIM_BOUNDARY,
        "public_host": args.public_host,
        "dashboard_path": "/pixeagle/",
        "api_proxy_path": "/pixeagle-api/",
        "dashboard_build_dir": str(args.dashboard_build_dir),
        "artifact_root": str(args.artifact_root),
        "processes": [
            "loopback PixEagle policy backend",
            "loopback self-signed HTTPS reverse proxy",
            "one Playwright Chromium worker",
        ],
        "checks": [
            "production_remote profile generation and secure credential handoff",
            "dashboard subpath assets and SPA fallback",
            "unauthenticated media denial",
            "wrong Host and Origin denial",
            "Secure HttpOnly browser session cookie",
            "session-bound CSRF denial and success",
            "authenticated HTTP media and WebSocket ping/pong",
            "logout and post-logout media denial",
            "durable sanitized security-audit records",
            "retained-evidence secret scan",
        ],
        "prohibited_claims": [
            "trusted certificate deployment",
            "firewall enforcement",
            "target service ownership",
            "PX4/SITL/HIL/field or real-aircraft success",
        ],
    }


def validate_execute_consent(args: argparse.Namespace) -> None:
    if not args.execute_browser:
        return
    if not args.allow_local_self_signed_tls:
        raise HarnessError(
            "--execute-browser requires --allow-local-self-signed-tls because "
            "the harness uses an ephemeral self-signed certificate."
        )
    if args.public_host != DEFAULT_PUBLIC_HOST:
        raise HarnessError(
            f"Execution is pinned to the reserved local test host {DEFAULT_PUBLIC_HOST!r}; "
            "custom hosts are dry-run only."
        )
    dashboard_build_dir = Path(
        getattr(args, "dashboard_build_dir", DEFAULT_DASHBOARD_BUILD)
    ).resolve()
    if dashboard_build_dir != DEFAULT_DASHBOARD_BUILD.resolve():
        raise HarnessError(
            "Execution must build and serve dashboard/build from the current checkout; "
            "custom --dashboard-build-dir values are dry-run only."
        )


def build_current_dashboard(args: argparse.Namespace, run_dir: Path) -> None:
    build_log = run_dir / "dashboard-build.log"
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=PROJECT_ROOT / "dashboard",
            text=True,
            capture_output=True,
            timeout=args.dashboard_build_timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        build_log.write_text(
            (exc.stdout or "") + (exc.stderr or ""),
            encoding="utf-8",
        )
        raise HarnessError(
            "Dashboard production build exceeded "
            f"{args.dashboard_build_timeout_s:.0f}s; see dashboard-build.log."
        ) from exc
    except OSError as exc:
        build_log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise HarnessError(
            "Dashboard production build could not start; see dashboard-build.log."
        ) from exc
    build_log.write_text(
        (result.stdout or "") + (result.stderr or ""),
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise HarnessError(
            "Dashboard production build failed; see the local dashboard-build.log."
        )


def ensure_execute_prerequisites(args: argparse.Namespace) -> Path | None:
    build_index = args.dashboard_build_dir / "index.html"
    if not build_index.is_file():
        raise HarnessError(
            f"Dashboard build is missing: {build_index}. "
            "Run `npm --prefix dashboard run build` first."
        )
    build_mtime = build_index.stat().st_mtime
    dashboard_inputs = [
        PROJECT_ROOT / "dashboard" / "package.json",
        PROJECT_ROOT / "dashboard" / "package-lock.json",
        *(PROJECT_ROOT / "dashboard" / "src").rglob("*"),
        *(PROJECT_ROOT / "dashboard" / "public").rglob("*"),
    ]
    newer_inputs = [
        path
        for path in dashboard_inputs
        if path.is_file() and path.stat().st_mtime > build_mtime
    ]
    if newer_inputs:
        newest = max(newer_inputs, key=lambda path: path.stat().st_mtime)
        raise HarnessError(
            "The mandatory dashboard build did not refresh output relative to "
            f"{newest.relative_to(PROJECT_ROOT)}."
        )
    for command in ("openssl", "node", "npm"):
        if shutil.which(command) is None:
            raise HarnessError(f"Required command is not available: {command}")

    check = subprocess.run(
        ["node", "-e", "require.resolve('@playwright/test')"],
        cwd=PROJECT_ROOT / "dashboard",
        text=True,
        capture_output=True,
        check=False,
    )
    if check.returncode != 0:
        raise HarnessError(
            "Dashboard Playwright dependency is missing. Run `npm --prefix dashboard ci`."
        )

    explicit = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if explicit:
        executable = Path(explicit)
        if not executable.is_file():
            raise HarnessError(
                f"PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH does not exist: {executable}"
            )
        return executable

    browser_check = subprocess.run(
        [
            "node",
            "-e",
            (
                "const fs=require('fs');"
                "const {chromium}=require('playwright');"
                "process.exit(fs.existsSync(chromium.executablePath()) ? 0 : 1);"
            ),
        ],
        cwd=PROJECT_ROOT / "dashboard",
        text=True,
        capture_output=True,
        check=False,
    )
    if browser_check.returncode != 0:
        raise HarnessError(
            "Playwright Chromium is missing. Run "
            "`make production-remote-browser-install` before browser execution."
        )

    return None


def create_run_directory(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / f"{run_id}-{secrets.token_hex(3)}"
    if run_dir.exists():
        raise HarnessError(f"Refusing to reuse evidence directory: {run_dir}")
    run_dir.mkdir(mode=0o700)
    return run_dir


def generate_self_signed_certificate(work_dir: Path, host: str) -> tuple[Path, Path]:
    certificate = work_dir / "tls-cert.pem"
    private_key = work_dir / "tls-key.pem"
    command = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-nodes",
        "-days",
        "1",
        "-subj",
        f"/CN={host}",
        "-addext",
        f"subjectAltName=DNS:{host},IP:127.0.0.1",
        "-keyout",
        str(private_key),
        "-out",
        str(certificate),
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise HarnessError(f"OpenSSL certificate generation failed: {result.stderr.strip()}")
    private_key.chmod(0o600)
    certificate.chmod(0o600)
    return certificate, private_key


def certificate_metadata(certificate: Path, host: str) -> dict[str, Any]:
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256(der).hexdigest()
    return {
        "host": host,
        "self_signed": True,
        "trust_behavior": "Playwright ignoreHTTPSErrors enabled only by explicit local consent",
        "sha256_fingerprint": fingerprint,
        "private_key_retained": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def apply_production_profile(
    *,
    work_dir: Path,
    public_host: str,
    public_origin: str,
    backend_port: int,
) -> dict[str, Path]:
    config_path = work_dir / "config.yaml"
    user_file = work_dir / "browser-users.json"
    handoff_file = work_dir / "credential-handoff.json"
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "setup" / "apply-setup-profile.py"),
        "--profile",
        "production_remote",
        "--public-host",
        public_host,
        "--public-origin",
        public_origin,
        "--http-stream-port",
        str(backend_port),
        "--defaults",
        str(PROJECT_ROOT / "configs" / "config_default.yaml"),
        "--config",
        str(config_path),
        "--session-user-file",
        str(user_file),
        "--credential-handoff-file",
        str(handoff_file),
        "--no-backup",
    ]
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise HarnessError(
            "production_remote profile generation failed: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    for path in (config_path, user_file, handoff_file):
        if not path.is_file():
            raise HarnessError(f"Profile did not create required temporary file: {path}")
        if path.stat().st_mode & 0o077:
            raise HarnessError(f"Temporary credential/config file is not owner-only: {path}")
    return {
        "config": config_path,
        "user_file": user_file,
        "handoff_file": handoff_file,
    }


def load_profile_security(
    config_path: Path,
) -> tuple[dict[str, Any], APIExposurePolicy]:
    from classes.api_exposure_policy import resolve_api_exposure_policy

    yaml = YAML(typ="safe")
    payload = yaml.load(config_path.read_text(encoding="utf-8"))
    streaming = payload.get("Streaming", {})
    policy = resolve_api_exposure_policy(
        bind_host=streaming["HTTP_STREAM_HOST"],
        mode=streaming["API_EXPOSURE_MODE"],
        cors_allowed_origins=streaming["API_CORS_ALLOWED_ORIGINS"],
        allowed_hosts=streaming["API_ALLOWED_HOSTS"],
        api_port=streaming["HTTP_STREAM_PORT"],
        allow_credentials=True,
    )
    summary = {
        "api_exposure_mode": streaming["API_EXPOSURE_MODE"],
        "backend_bind_host": streaming["HTTP_STREAM_HOST"],
        "backend_port": streaming["HTTP_STREAM_PORT"],
        "cors_allowed_origins": list(streaming["API_CORS_ALLOWED_ORIGINS"]),
        "allowed_hosts": list(streaming["API_ALLOWED_HOSTS"]),
        "auth_mode": streaming["API_AUTH_MODE"],
        "secure_cookie": bool(streaming["API_SESSION_COOKIE_SECURE"]),
        "security_audit_enabled": bool(streaming["API_SECURITY_AUDIT_ENABLED"]),
        "credential_material_retained": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return summary, policy


def build_auth_runtime(user_file: Path) -> APIAuthRuntime:
    from classes.api_auth_runtime import APIAuthRuntime, load_user_records

    records = load_user_records(user_file)
    return APIAuthRuntime(
        mode="browser_session",
        users_by_username={record.username: record for record in records},
        user_file=user_file,
        session_cookie_secure=True,
        session_cookie_name=DEFAULT_SESSION_COOKIE_NAME,
    )


def build_evidence_backend(
    *,
    policy: APIExposurePolicy,
    auth_runtime: APIAuthRuntime,
    audit_path: Path,
) -> FastAPIHandler:
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from classes.api_security_audit import APISecurityAuditLogger
            from classes.api_v1_contracts import (
                APIActionRequest,
                APIStreamingMediaHealthResponse,
            )
            from classes.api_v1_streams import get_streaming_media_health_snapshot
            from classes.fastapi_handler import FastAPIHandler
    finally:
        logging.disable(previous_logging_disable)

    owner = FastAPIHandler.__new__(FastAPIHandler)
    owner.logger = logging.getLogger("pixeagle.production_remote_e2e.backend")
    owner.exposure_policy = policy
    owner.api_auth_runtime = auth_runtime
    owner.security_audit_logger = APISecurityAuditLogger(
        enabled=True,
        log_path=audit_path,
        max_bytes=2_000_000,
        backup_count=1,
    )
    owner.app = FastAPI(
        title="PixEagle production-remote local evidence backend",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    owner.app.add_exception_handler(
        RequestValidationError,
        owner._handle_request_validation_error,
    )
    owner._setup_middleware()

    owner.frame_publisher = HarnessFramePublisher()
    owner.quality_engine = HarnessQualityEngine()
    owner.stream_optimizer = HarnessStreamOptimizer()
    owner.connection_lock = asyncio.Lock()
    owner.http_connections = set()
    owner.ws_connections = {}
    owner.stats = {
        "frames_sent": 0,
        "frames_dropped": 0,
        "total_bandwidth": 0,
        "active_connections": 0,
    }
    owner.frame_interval = 0.05
    owner.is_shutting_down = False
    owner.app_controller = None

    owner.app.get("/api/v1/auth/session")(owner.get_auth_session)
    owner.app.post("/api/v1/auth/login")(owner.login_auth_session)
    owner.app.post("/api/v1/auth/logout")(owner.logout_auth_session)

    async def media_health() -> APIStreamingMediaHealthResponse:
        payload = await get_streaming_media_health_snapshot(owner)
        return APIStreamingMediaHealthResponse(**payload)

    async def tracking_stop_contract(request_body: dict[str, Any]) -> JSONResponse:
        request = APIActionRequest(**request_body)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "executed": False,
                "dry_run": bool(request.dry_run),
                "source": "local_evidence_harness",
                "claim_boundary": "CSRF and action-policy contract only; no flight action executed.",
            },
        )

    async def config_sections_fixture() -> dict[str, Any]:
        return {"success": True, "sections": []}

    async def config_categories_fixture() -> dict[str, Any]:
        return {"success": True, "categories": {}}

    async def dashboard_read_fixture(request: Request) -> JSONResponse:
        path = request.url.path
        payload: dict[str, Any] = {
            "success": True,
            "status": "ok",
            "source": "local_evidence_harness",
        }
        if path == "/api/config/schema":
            payload["schema"] = config_schema_fixture()
        elif path == "/api/config/diff":
            payload["differences"] = []
        elif path == "/api/config/defaults-sync":
            payload.update(config_sync_v2_fixture())
        elif path == "/api/config/history":
            payload["backups"] = []
        elif path == "/api/recordings":
            payload["recordings"] = []
        elif path == "/api/models":
            payload.update({"models": {}, "total_count": 0})
        elif path == "/api/models/active":
            payload.update({"available": False, "active_model_summary": None})
        elif path == "/api/follower/profiles":
            payload["profiles"] = []
        elif path == "/api/follower/current-profile":
            payload.update({"profile": None, "is_transitioning": False})
        elif path == "/api/follower/schema":
            payload.update({"profiles": {}, "commands": {}})
        elif path.startswith("/api/tracker/"):
            payload.update(
                {
                    "available": [],
                    "available_types": [],
                    "tracker": None,
                    "tracking": False,
                    "output": None,
                }
            )
        elif path == "/api/osd/presets":
            payload["presets"] = []
        elif path == "/api/recording/status":
            payload.update({"recording": False, "paused": False})
        elif path == "/api/v1/config/runtime-status":
            payload.update(config_runtime_status_fixture())
        return JSONResponse(
            payload,
            headers={"X-PixEagle-Evidence-Fixture": "1"},
        )

    owner.app.get(
        "/api/v1/streams/media-health",
        response_model=APIStreamingMediaHealthResponse,
    )(media_health)
    owner.app.get("/video_feed")(owner.video_feed)
    owner.app.get("/api/config/sections")(config_sections_fixture)
    owner.app.get("/api/config/categories")(config_categories_fixture)
    owner.app.post("/api/v1/actions/tracking-stop")(tracking_stop_contract)
    owner.app.websocket("/ws/video_feed")(owner.video_feed_websocket_optimized)
    owner.app.get("/{path:path}")(dashboard_read_fixture)
    return owner


def proxy_request_headers(request: Request) -> dict[str, str]:
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in FORWARDED_HTTP_HEADERS
    }
    headers["host"] = request.headers.get("host", "")
    return headers


def response_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    return [
        (name, value)
        for name, value in headers.multi_items()
        if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "set-cookie"
    ]


def safe_static_file(build_dir: Path, relative_path: str) -> Path | None:
    build_root = build_dir.resolve()
    candidate = (build_root / relative_path).resolve()
    try:
        candidate.relative_to(build_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def build_https_proxy(
    *,
    build_dir: Path,
    backend_port: int,
    public_host: str,
    public_port: int,
) -> FastAPI:
    app = FastAPI(
        title="PixEagle local HTTPS evidence proxy",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/pixeagle")
    async def dashboard_redirect() -> RedirectResponse:
        return RedirectResponse("/pixeagle/", status_code=status.HTTP_308_PERMANENT_REDIRECT)

    async def proxy_http(request: Request, path: str) -> Response:
        upstream_url = f"http://127.0.0.1:{backend_port}/{path}"
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=False)
        upstream_request = client.build_request(
            request.method,
            upstream_url,
            params=request.query_params,
            headers=proxy_request_headers(request),
            content=await request.body(),
        )
        try:
            upstream = await client.send(upstream_request, stream=True)
        except Exception:
            await client.aclose()
            raise

        async def upstream_body():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        proxy_response = StreamingResponse(
            upstream_body(),
            status_code=upstream.status_code,
            headers=dict(response_headers(upstream.headers)),
            media_type=upstream.headers.get("content-type"),
        )
        for cookie in upstream.headers.get_list("set-cookie"):
            proxy_response.headers.append("set-cookie", cookie)
        return proxy_response

    @app.api_route(
        "/pixeagle-api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    async def proxy_api(request: Request, path: str) -> Response:
        return await proxy_http(request, path)

    @app.websocket("/pixeagle-api/{path:path}")
    async def proxy_websocket(websocket: WebSocket, path: str) -> None:
        public_authority = authority(public_host, public_port)
        incoming_origin = websocket.headers.get("origin")
        incoming_cookie = websocket.headers.get("cookie")
        additional_headers = []
        if incoming_cookie:
            additional_headers.append(("Cookie", incoming_cookie))
        if request_id := websocket.headers.get("x-request-id"):
            additional_headers.append(("X-Request-ID", request_id))

        query = getattr(getattr(websocket, "url", None), "query", "")
        query_suffix = f"?{query}" if query else ""
        upstream_uri = f"ws://{public_authority}/{path}{query_suffix}"
        try:
            async with websocket_connect(
                upstream_uri,
                host="127.0.0.1",
                port=backend_port,
                origin=incoming_origin,
                additional_headers=additional_headers or None,
                proxy=None,
                open_timeout=5,
                close_timeout=2,
                ping_interval=None,
            ) as upstream:
                await websocket.accept()

                async def browser_to_backend() -> None:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            return
                        if message.get("text") is not None:
                            await upstream.send(message["text"])
                        elif message.get("bytes") is not None:
                            await upstream.send(message["bytes"])

                async def backend_to_browser() -> None:
                    try:
                        async for message in upstream:
                            if isinstance(message, str):
                                await websocket.send_text(message)
                            else:
                                await websocket.send_bytes(message)
                    except ConnectionClosed as exc:
                        await websocket.close(
                            code=int(exc.code or 1000),
                            reason=str(exc.reason or ""),
                        )

                tasks = {
                    asyncio.create_task(browser_to_backend()),
                    asyncio.create_task(backend_to_browser()),
                }
                done, pending = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*done, *pending, return_exceptions=True)
        except Exception as exc:
            logging.getLogger("pixeagle.production_remote_e2e.proxy").debug(
                "WebSocket proxy closed before/after accept: %s", type(exc).__name__
            )
            with suppress(Exception):
                await websocket.close(code=1008, reason="Upstream WebSocket denied")

    @app.get("/pixeagle/{path:path}")
    async def dashboard_assets(path: str) -> Response:
        relative_path = path or "index.html"
        static_file = safe_static_file(build_dir, relative_path)
        if static_file is not None:
            return FileResponse(static_file)
        return FileResponse(build_dir / "index.html")

    return app


def uvicorn_server(
    app: FastAPI,
    *,
    port: int,
    ssl_certificate: Path | None = None,
    ssl_private_key: Path | None = None,
) -> uvicorn.Server:
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        ssl_certfile=str(ssl_certificate) if ssl_certificate else None,
        ssl_keyfile=str(ssl_private_key) if ssl_private_key else None,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    return server


async def wait_for_server(port: int, *, timeout_s: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            _ = reader
            return
        except OSError:
            await asyncio.sleep(0.05)
    raise HarnessError(f"Timed out waiting for loopback server on port {port}")


async def run_http_adversarial_probes(
    *,
    public_origin: str,
    public_authority: str,
) -> dict[str, Any]:
    parsed_port = public_origin.rsplit(":", 1)[-1]
    connect_origin = f"https://127.0.0.1:{parsed_port}"
    url = f"{connect_origin}/pixeagle-api/api/v1/streams/media-health"
    async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
        unauthenticated = await client.get(
            url,
            headers={"Host": public_authority},
        )
        wrong_host = await client.get(
            url,
            headers={"Host": f"wrong.{DEFAULT_PUBLIC_HOST}"},
        )
        wrong_origin = await client.get(
            url,
            headers={
                "Host": public_authority,
                "Origin": "https://wrong.example",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        wrong_authority_port = await client.get(
            url,
            headers={"Host": f"{DEFAULT_PUBLIC_HOST}:5077"},
        )
        cross_site = await client.get(
            url,
            headers={
                "Host": public_authority,
                "Origin": public_origin,
                "Sec-Fetch-Site": "cross-site",
            },
        )
        query_token = await client.get(
            f"{url}?token=not-a-real-token",
            headers={"Host": public_authority},
        )
    probes = {
        "unauthenticated_media": {
            "status": unauthenticated.status_code,
            "passed": unauthenticated.status_code == 401,
        },
        "wrong_host": {
            "status": wrong_host.status_code,
            "passed": wrong_host.status_code == 403,
        },
        "wrong_origin": {
            "status": wrong_origin.status_code,
            "passed": wrong_origin.status_code == 403,
        },
        "wrong_authority_port": {
            "status": wrong_authority_port.status_code,
            "passed": wrong_authority_port.status_code == 403,
        },
        "cross_site": {
            "status": cross_site.status_code,
            "passed": cross_site.status_code == 403,
        },
        "query_token": {
            "status": query_token.status_code,
            "passed": query_token.status_code == 401,
        },
    }
    probes["passed"] = all(item["passed"] for item in probes.values())
    return probes


async def run_playwright(
    *,
    args: argparse.Namespace,
    public_origin: str,
    username: str,
    password: str,
    run_dir: Path,
    browser_executable: Path | None,
    secret_handoff_file: Path,
) -> tuple[dict[str, Any], list[str]]:
    browser_dir = run_dir / "browser"
    browser_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("FORCE_COLOR", None)
    env.update(
        {
            "PIXEAGLE_E2E_BASE_URL": public_origin,
            "PIXEAGLE_E2E_USERNAME": username,
            "PIXEAGLE_E2E_PASSWORD": password,
            "PIXEAGLE_E2E_EVIDENCE_DIR": str(browser_dir),
            "PIXEAGLE_E2E_PUBLIC_HOST": args.public_host,
            "PIXEAGLE_E2E_ALLOW_SELF_SIGNED_TLS": "1",
            "PIXEAGLE_E2E_SECRET_HANDOFF_FILE": str(secret_handoff_file),
            "NO_COLOR": "1",
        }
    )
    if browser_executable is not None:
        env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = str(browser_executable)

    process = await asyncio.create_subprocess_exec(
        "npm",
        "run",
        "test:e2e:production-remote",
        cwd=PROJECT_ROOT / "dashboard",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    timed_out = False
    cleanup_failed = False
    timeout_error: asyncio.TimeoutError | None = None
    try:
        output_bytes, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=args.browser_timeout_s,
        )
    except asyncio.TimeoutError as exc:
        timed_out = True
        timeout_error = exc
        if os.name == "posix":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            output_bytes, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=5,
            )
        except asyncio.TimeoutError:
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            try:
                output_bytes, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                cleanup_failed = True
                output_bytes = b""
                transport = getattr(process, "_transport", None)
                if transport is not None:
                    transport.close()
    output = output_bytes.decode("utf-8", errors="replace")
    (browser_dir / "playwright.log").write_text(output, encoding="utf-8")
    if cleanup_failed:
        raise HarnessError(
            "Playwright process group did not terminate within the bounded cleanup window"
        ) from timeout_error
    if timed_out:
        raise HarnessError(
            f"Playwright exceeded the {args.browser_timeout_s:.0f}s timeout"
        ) from timeout_error
    result_path = browser_dir / "browser-results.json"
    result = (
        json.loads(result_path.read_text(encoding="utf-8"))
        if result_path.is_file()
        else {"passed": False, "reason": "browser result artifact missing"}
    )
    result["process_exit_code"] = process.returncode
    result["passed"] = bool(result.get("passed")) and process.returncode == 0
    write_json(result_path, result)
    browser_secrets = consume_secret_handoff(secret_handoff_file)
    return result, browser_secrets


def consume_secret_handoff(path: Path) -> list[str]:
    """Read browser-generated secrets, then remove the temporary handoff."""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise HarnessError("Browser secret handoff must contain a JSON object")
        return [
            str(value)
            for value in payload.values()
            if isinstance(value, str) and value
        ]
    finally:
        path.unlink(missing_ok=True)


def summarize_audit(audit_path: Path, destination: Path) -> dict[str, Any]:
    if not audit_path.is_file():
        summary = {
            "passed": False,
            "reason": "security audit file missing",
            "event_count": 0,
        }
        write_json(destination, summary)
        return summary

    events = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))

    event_types = sorted({event.get("event_type") for event in events})
    outcomes = sorted({event.get("outcome") for event in events})
    raw = audit_path.read_text(encoding="utf-8").lower()
    forbidden = [
        marker
        for marker in ("password", "cookie", "bearer ", "csrf_token", "token=")
        if marker in raw
    ]
    required_types = {
        "api.auth.login",
        "api.auth.logout",
        "api.http.authorization",
        "api.http.origin",
        "api.websocket.authorization",
    }
    summary = {
        "passed": (
            required_types.issubset(set(event_types))
            and {"allowed", "denied"}.issubset(set(outcomes))
            and not forbidden
        ),
        "event_count": len(events),
        "event_types": event_types,
        "outcomes": outcomes,
        "forbidden_markers": forbidden,
        "required_event_types": sorted(required_types),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audit_path, destination.parent / "security_audit.jsonl")
    write_json(destination, summary)
    return summary


def scan_retained_evidence_for_secrets(
    run_dir: Path,
    *,
    secret_values: Iterable[str] = (),
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    binary_files_checked = 0
    normalized_secrets = [
        value.encode("utf-8")
        for value in dict.fromkeys(str(value) for value in secret_values)
        if value
    ]
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(run_dir)
        if relative_path.parts and relative_path.parts[0] == "upload":
            continue
        raw = path.read_bytes()
        for index, secret in enumerate(normalized_secrets, start=1):
            if secret in raw:
                findings.append(
                    {
                        "path": str(relative_path),
                        "type": f"exact_generated_secret_{index}",
                    }
                )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            binary_files_checked += 1
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(
                    {
                        "path": str(relative_path),
                        "type": label,
                    }
                )
    return {
        "passed": not findings,
        "findings": findings,
        "binary_files_checked_for_exact_secrets": binary_files_checked,
        "exact_secret_count_checked": len(normalized_secrets),
        "values_echoed": False,
    }


SANITIZED_UPLOAD_PATHS = (
    "manifest.json",
    "versions/runtime.json",
    "tls/certificate.json",
    "config/effective-security.json",
    "http/adversarial-probes.json",
    "browser/browser-results.json",
    "browser/request-ledger.json",
    "browser/websocket-ledger.json",
    "browser/response-ledger.json",
    "browser/request-failures.json",
    "audit/summary.json",
    "security/secret-scan.json",
)


def create_sanitized_upload_bundle(
    run_dir: Path,
    *,
    accepted: bool,
    secret_scan_passed: bool,
) -> None:
    upload_dir = run_dir / "upload"
    shutil.rmtree(upload_dir, ignore_errors=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        upload_dir / "upload-status.json",
        {
            "accepted": accepted,
            "secret_scan_passed": secret_scan_passed,
            "raw_artifacts_uploaded": False,
            "claim_boundary": CLAIM_BOUNDARY,
        },
    )
    if not secret_scan_passed:
        source = run_dir / "security" / "secret-scan.json"
        if source.is_file():
            target = upload_dir / "security" / "secret-scan.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return

    for relative in SANITIZED_UPLOAD_PATHS:
        source = run_dir / relative
        if not source.is_file():
            continue
        target = upload_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if accepted:
        for screenshot_name in ("login-gate.png", "authenticated-dashboard.png"):
            source = run_dir / "browser" / screenshot_name
            if source.is_file():
                target = upload_dir / "browser" / screenshot_name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


def finalize_evidence(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    secret_values: Iterable[str],
) -> None:
    manifest["completed_at"] = utc_now()
    manifest["accepted"] = False
    write_json(run_dir / "manifest.json", manifest)

    raw_scan = scan_retained_evidence_for_secrets(
        run_dir,
        secret_values=secret_values,
    )
    manifest["checks"]["secret_scan"] = raw_scan
    manifest["accepted"] = (
        bool(manifest["checks"])
        and all(bool(check.get("passed")) for check in manifest["checks"].values())
    )
    write_json(run_dir / "manifest.json", manifest)

    raw_scan = scan_retained_evidence_for_secrets(
        run_dir,
        secret_values=secret_values,
    )
    create_sanitized_upload_bundle(
        run_dir,
        accepted=bool(manifest["accepted"] and raw_scan["passed"]),
        secret_scan_passed=bool(raw_scan["passed"]),
    )
    upload_scan = scan_retained_evidence_for_secrets(
        run_dir / "upload",
        secret_values=secret_values,
    )
    overall_scan = {
        "passed": bool(raw_scan["passed"] and upload_scan["passed"]),
        "raw_retained_artifacts": raw_scan,
        "sanitized_upload_bundle": upload_scan,
        "values_echoed": False,
    }
    manifest["checks"]["secret_scan"] = overall_scan
    manifest["accepted"] = (
        bool(manifest["checks"])
        and all(bool(check.get("passed")) for check in manifest["checks"].values())
    )
    write_json(run_dir / "security" / "secret-scan.json", overall_scan)
    write_json(run_dir / "manifest.json", manifest)
    create_sanitized_upload_bundle(
        run_dir,
        accepted=bool(manifest["accepted"]),
        secret_scan_passed=bool(overall_scan["passed"]),
    )

    final_raw_scan = scan_retained_evidence_for_secrets(
        run_dir,
        secret_values=secret_values,
    )
    final_upload_scan = scan_retained_evidence_for_secrets(
        run_dir / "upload",
        secret_values=secret_values,
    )
    if not final_raw_scan["passed"] or not final_upload_scan["passed"]:
        overall_scan = {
            "passed": False,
            "raw_retained_artifacts": final_raw_scan,
            "sanitized_upload_bundle": final_upload_scan,
            "values_echoed": False,
        }
        manifest["checks"]["secret_scan"] = overall_scan
        manifest["accepted"] = False
        write_json(run_dir / "security" / "secret-scan.json", overall_scan)
        write_json(run_dir / "manifest.json", manifest)
        create_sanitized_upload_bundle(
            run_dir,
            accepted=False,
            secret_scan_passed=False,
        )


async def stop_servers(
    servers: Iterable[uvicorn.Server],
    tasks: Iterable[asyncio.Task[Any]],
) -> None:
    for server in servers:
        server.should_exit = True
    task_list = list(tasks)
    done, pending = await asyncio.wait(task_list, timeout=8)
    for task in done:
        with suppress(asyncio.CancelledError):
            task.exception()
    if not pending:
        return

    for server in servers:
        server.force_exit = True
    for task in pending:
        task.cancel()
    cancelled, still_pending = await asyncio.wait(pending, timeout=2)
    for task in cancelled:
        with suppress(asyncio.CancelledError):
            task.exception()
    if still_pending:
        raise HarnessError(
            "Harness-owned Uvicorn servers did not stop within the 10s cleanup window"
        )
    raise HarnessError("Harness-owned Uvicorn servers required forced cancellation")


async def execute(args: argparse.Namespace) -> tuple[int, Path]:
    validate_execute_consent(args)
    run_dir = create_run_directory(args.artifact_root)
    backend_port = args.backend_port or choose_loopback_port()
    https_port = args.https_port or choose_loopback_port()
    if backend_port == https_port:
        https_port = choose_loopback_port()
    public_authority = authority(args.public_host, https_port)
    public_origin = f"https://{public_authority}"

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "started_at": utc_now(),
        "mode": "execute-browser",
        "accepted": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "public_origin": public_origin,
        "dashboard_path": "/pixeagle/",
        "api_proxy_path": "/pixeagle-api/",
        "backend_bind": f"127.0.0.1:{backend_port}",
        "proxy_bind": f"127.0.0.1:{https_port}",
        "self_signed_tls": True,
        "checks": {},
    }
    write_json(run_dir / "manifest.json", manifest)

    backend_server: uvicorn.Server | None = None
    proxy_server: uvicorn.Server | None = None
    server_tasks: list[asyncio.Task[Any]] = []
    secret_values: list[str] = []
    work_dir_context = tempfile.TemporaryDirectory(prefix="pixeagle-browser-e2e-")
    work_dir = Path(work_dir_context.name)
    audit_path = work_dir / "security_audit.jsonl"
    browser_secret_handoff = work_dir / "browser-secrets.json"
    try:
        build_current_dashboard(args, run_dir)
        manifest["checks"]["dashboard_build"] = {"passed": True}
        browser_executable = ensure_execute_prerequisites(args)
        certificate, private_key = generate_self_signed_certificate(
            work_dir,
            args.public_host,
        )
        write_json(
            run_dir / "versions" / "runtime.json",
            version_evidence(
                dashboard_build_dir=args.dashboard_build_dir,
                browser_executable=browser_executable,
            ),
        )
        write_json(
            run_dir / "tls" / "certificate.json",
            certificate_metadata(certificate, args.public_host),
        )

        paths = apply_production_profile(
            work_dir=work_dir,
            public_host=args.public_host,
            public_origin=public_origin,
            backend_port=backend_port,
        )
        profile_summary, policy = load_profile_security(paths["config"])
        write_json(run_dir / "config" / "effective-security.json", profile_summary)

        handoff = json.loads(paths["handoff_file"].read_text(encoding="utf-8"))
        username = str(handoff["username"])
        password = str(handoff["password"])
        secret_values.append(password)
        paths["handoff_file"].unlink()

        auth_runtime = build_auth_runtime(paths["user_file"])
        backend_owner = build_evidence_backend(
            policy=policy,
            auth_runtime=auth_runtime,
            audit_path=audit_path,
        )
        proxy_app = build_https_proxy(
            build_dir=args.dashboard_build_dir,
            backend_port=backend_port,
            public_host=args.public_host,
            public_port=https_port,
        )
        backend_server = uvicorn_server(backend_owner.app, port=backend_port)
        proxy_server = uvicorn_server(
            proxy_app,
            port=https_port,
            ssl_certificate=certificate,
            ssl_private_key=private_key,
        )
        server_tasks = [
            asyncio.create_task(backend_server.serve()),
            asyncio.create_task(proxy_server.serve()),
        ]
        await wait_for_server(backend_port)
        await wait_for_server(https_port)

        adversarial = await run_http_adversarial_probes(
            public_origin=public_origin,
            public_authority=public_authority,
        )
        manifest["checks"]["http_adversarial"] = adversarial
        write_json(run_dir / "http" / "adversarial-probes.json", adversarial)

        browser_result, browser_secrets = await run_playwright(
            args=args,
            public_origin=public_origin,
            username=username,
            password=password,
            run_dir=run_dir,
            browser_executable=browser_executable,
            secret_handoff_file=browser_secret_handoff,
        )
        secret_values.extend(browser_secrets)
        manifest["checks"]["browser"] = browser_result

        await stop_servers(
            [backend_server, proxy_server],
            server_tasks,
        )
        server_tasks = []
        manifest["checks"]["process_cleanup"] = {"passed": True}
        audit_summary = summarize_audit(
            audit_path,
            run_dir / "audit" / "summary.json",
        )
        manifest["checks"]["security_audit"] = audit_summary
    except Exception as exc:
        manifest["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    finally:
        try:
            secret_values.extend(consume_secret_handoff(browser_secret_handoff))
        except HarnessError as exc:
            manifest.setdefault(
                "error",
                {"type": type(exc).__name__, "message": str(exc)},
            )
            manifest["checks"]["browser_secret_handoff"] = {
                "passed": False,
                "reason": str(exc),
            }
        if server_tasks and backend_server is not None and proxy_server is not None:
            try:
                await stop_servers([backend_server, proxy_server], server_tasks)
                manifest["checks"]["process_cleanup"] = {"passed": True}
            except HarnessError as exc:
                manifest["checks"]["process_cleanup"] = {
                    "passed": False,
                    "reason": str(exc),
                }
                manifest.setdefault(
                    "error",
                    {"type": type(exc).__name__, "message": str(exc)},
                )
        if audit_path.is_file() and "security_audit" not in manifest["checks"]:
            manifest["checks"]["security_audit"] = summarize_audit(
                audit_path,
                run_dir / "audit" / "summary.json",
            )
        finalize_evidence(
            run_dir=run_dir,
            manifest=manifest,
            secret_values=secret_values,
        )
        work_dir_context.cleanup()
    return (0 if manifest["accepted"] else 1), run_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or execute the local-only production remote HTTPS/browser "
            "evidence harness."
        )
    )
    parser.add_argument(
        "--execute-browser",
        action="store_true",
        help="Start harness-owned loopback servers and run Playwright.",
    )
    parser.add_argument(
        "--allow-local-self-signed-tls",
        action="store_true",
        help="Required consent for execute mode's ephemeral self-signed certificate.",
    )
    parser.add_argument(
        "--public-host",
        default=DEFAULT_PUBLIC_HOST,
        help=f"Reserved local test host. Execute mode requires {DEFAULT_PUBLIC_HOST}.",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=0,
        help="Optional fixed loopback backend port; default chooses a free port.",
    )
    parser.add_argument(
        "--https-port",
        type=int,
        default=0,
        help="Optional fixed loopback HTTPS port; default chooses a free port.",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Root for retained sanitized evidence.",
    )
    parser.add_argument(
        "--dashboard-build-dir",
        type=Path,
        default=DEFAULT_DASHBOARD_BUILD,
        help="Existing production dashboard build directory.",
    )
    parser.add_argument(
        "--dashboard-build-timeout-s",
        type=float,
        default=180.0,
        help="Maximum time for the mandatory current-checkout dashboard build.",
    )
    parser.add_argument(
        "--browser-timeout-s",
        type=float,
        default=90.0,
        help="Maximum time for the Playwright subprocess before termination.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the dry-run plan or final result as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.artifact_root = args.artifact_root.expanduser().resolve()
    args.dashboard_build_dir = args.dashboard_build_dir.expanduser().resolve()
    try:
        if args.dashboard_build_timeout_s <= 0 or args.browser_timeout_s <= 0:
            raise HarnessError("Harness timeouts must be positive seconds.")
        validate_execute_consent(args)
        if not args.execute_browser:
            plan = build_dry_run_plan(args)
            if args.json:
                print(json.dumps(plan, indent=2, sort_keys=True))
            else:
                print("Dry run: PixEagle production remote browser evidence harness")
                print(f"  Claim boundary: {CLAIM_BOUNDARY}")
                for check in plan["checks"]:
                    print(f"  - {check}")
            return 0

        exit_code, run_dir = asyncio.run(execute(args))
        result = {
            "accepted": exit_code == 0,
            "artifact_directory": str(run_dir),
            "claim_boundary": CLAIM_BOUNDARY,
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(
                "Accepted local browser evidence"
                if exit_code == 0
                else "Local browser evidence failed"
            )
            print(f"Artifacts: {run_dir}")
            print(f"Claim boundary: {CLAIM_BOUNDARY}")
        return exit_code
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
