"""Service-status guardrails for typed media-health probing."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


SAMPLE_MEDIA_HEALTH = {
    "schema_version": 1,
    "source": "streaming_media",
    "status": "active",
    "consumer_guidance": "serving_media",
    "transports": [
        {
            "name": "http_mjpeg",
            "status": "idle",
            "active_connections": 0,
            "max_connections": 20,
        },
        {
            "name": "websocket_jpeg",
            "status": "active",
            "active_connections": 1,
            "max_connections": 10,
        },
        {
            "name": "gstreamer_udp_h264",
            "status": "active",
            "active_connections": 0,
            "max_connections": None,
        },
    ],
    "frames": {
        "source_available": True,
        "latest_frame_stale": False,
        "latest_frame_age_s": 0.2,
    },
    "health_issues": [],
}


@contextlib.contextmanager
def _media_health_server(*, status: int = 200, payload=None, body: bytes | None = None):
    records = []
    response_body = body
    if response_body is None:
        response_body = json.dumps(payload if payload is not None else SAMPLE_MEDIA_HEALTH).encode(
            "utf-8"
        )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib callback name
            records.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                }
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v1/streams/media-health", records
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _run_probe(url: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "PIXEAGLE_MEDIA_HEALTH_URL": url,
            "PYTHON": sys.executable,
        }
    )
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [
            "bash",
            "-lc",
            "source scripts/service/utils.sh; probe_media_health 5077",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_service_media_health_probe_uses_loopback_without_auth_headers():
    with _media_health_server() as (url, records):
        result = _run_probe(url)

    assert result.returncode == 0, result.stderr
    assert "Backend media: active (serving_media)" in result.stdout
    assert "Frame publisher: fresh (0.2s)" in result.stdout
    assert "websocket_jpeg=active/1" in result.stdout
    assert "gstreamer_udp_h264=active" in result.stdout
    assert "Remote receipt: not proven by this process-local check" in result.stdout
    assert records[0]["path"] == "/api/v1/streams/media-health"
    assert "Authorization" not in records[0]["headers"]
    assert "X-Forwarded-For" not in records[0]["headers"]


def test_service_media_health_probe_uses_explicit_bearer_file_without_printing_secret(tmp_path):
    token_file = tmp_path / "media-token"
    token_file.write_text("super-secret-token\n", encoding="utf-8")

    with _media_health_server() as (url, records):
        result = _run_probe(
            url,
            {"PIXEAGLE_MEDIA_HEALTH_BEARER_TOKEN_FILE": str(token_file)},
        )

    assert result.returncode == 0, result.stderr
    assert records[0]["headers"]["Authorization"] == "Bearer super-secret-token"
    assert records[0]["path"] == "/api/v1/streams/media-health"
    assert "super-secret-token" not in result.stdout
    assert "token=" not in records[0]["path"]


def test_service_media_health_probe_reports_auth_required_without_media_down_claim():
    with _media_health_server(status=403, payload={"detail": "forbidden"}) as (url, _records):
        result = _run_probe(url)

    assert result.returncode == 0, result.stderr
    assert "Backend media: auth required (HTTP 403; requires media:read)" in result.stdout
    assert "probe failed" not in result.stdout
    assert "Remote receipt: not proven by this process-local check" in result.stdout


def test_service_media_health_probe_reports_malformed_json_distinctly():
    with _media_health_server(body=b"not-json") as (url, _records):
        result = _run_probe(url)

    assert result.returncode == 0, result.stderr
    assert "Backend media: invalid response (expected JSON)" in result.stdout
    assert "Remote receipt: not proven by this process-local check" in result.stdout
