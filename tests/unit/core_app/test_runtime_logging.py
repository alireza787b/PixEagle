"""Tests for PixEagle durable runtime log sessions."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from classes.runtime_logging import (
    RUNTIME_LOG_CLAIM_BOUNDARY,
    RuntimeLogSessionManager,
    redact_text,
)


def _remove_runtime_handlers(run_id: str) -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_pixeagle_run_id", None) == run_id:
            root_logger.removeHandler(handler)
            handler.close()


def test_runtime_log_session_writes_redacted_jsonl(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_test_1")

    try:
        manifest = manager.configure_python_logging()
        logger = logging.getLogger("tests.runtime_logging")
        logger.warning(
            "operator password=swordfish Authorization: Bearer abcdefghijklmnop"
        )
    finally:
        _remove_runtime_handlers("pixeagle_test_1")

    assert manifest["run_id"] == "pixeagle_test_1"
    assert manifest["claim_boundary"] == RUNTIME_LOG_CLAIM_BOUNDARY

    entries = manager.read_entries("pixeagle_test_1", level="WARNING")
    assert entries is not None
    assert len(entries) == 1
    entry = entries[0]
    assert entry["run_id"] == "pixeagle_test_1"
    assert entry["level"] == "WARNING"
    assert "swordfish" not in entry["message"]
    assert "abcdefghijklmnop" not in entry["message"]
    assert "[REDACTED]" in entry["message"]


def test_runtime_log_session_rejects_unsafe_ids_and_components(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="safe_run")
    manager.initialize_session()

    for unsafe_run_id in ("../escape", ".", "..", "-dash", "under_"):
        with pytest.raises(ValueError):
            manager.read_entries(unsafe_run_id)

    for unsafe_component in ("../backend", ".", "-backend"):
        with pytest.raises(ValueError):
            manager.read_entries("safe_run", component=unsafe_component)


def test_runtime_log_session_lists_sessions_with_retention(tmp_path):
    stale = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_stale",
        max_sessions=1,
    )
    stale.initialize_session()
    stale_dir = Path(stale.session_dir)

    active = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_active",
        max_sessions=1,
    )
    active.initialize_session()

    sessions = active.list_sessions()
    assert [session["run_id"] for session in sessions] == ["pixeagle_active"]
    assert not stale_dir.exists()


def test_redact_text_handles_url_credentials_and_named_secrets():
    message = (
        "rtsp://user:pass@example.test/path token=abc123456 "
        "secret: open-sesame Authorization: Basic dXNlcjpwYXNz, Cookie: sid=abc"
    )

    redacted = redact_text(message)

    assert "user:pass" not in redacted
    assert "abc123456" not in redacted
    assert "open-sesame" not in redacted
    assert "dXNlcjpwYXNz" not in redacted
    assert "sid=abc" not in redacted
    assert redacted.count("[REDACTED]") == 5


def test_runtime_log_read_entries_applies_read_time_redaction(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_readback")
    manager.initialize_session()
    manager.component_path().write_text(
        '{"ts":"2026-07-04T00:00:00.000Z","level":"ERROR",'
        '"message":"Cookie: sid=abc","extra":{"Authorization":"Basic dXNlcjpwYXNz"}}\n',
        encoding="utf-8",
    )

    entries = manager.read_entries("pixeagle_readback", level="ERROR")

    assert entries is not None
    assert entries[0]["message"] == "Cookie: [REDACTED]"
    assert entries[0]["extra"]["Authorization"] == "[REDACTED]"


def test_runtime_log_rejects_invalid_level_filter(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_levels")
    manager.initialize_session()

    with pytest.raises(ValueError):
        manager.read_entries("pixeagle_levels", level="VERYLOUD")


def test_runtime_log_registers_sidecar_component_in_manifest(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_sidecar")

    manifest = manager.initialize_session(components=["dashboard", "mavlink2rest"])

    assert set(manifest["component_files"]) == {
        "backend",
        "dashboard",
        "mavlink2rest",
    }
    assert manager.component_path("dashboard").is_file()
    assert manager.component_path("mavlink2rest").is_file()


def test_runtime_log_appends_redacted_sidecar_message(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_stdout")

    entry = manager.append_component_message(
        "dashboard",
        "serve started password=swordfish",
        stream="stderr",
        source="launcher-pipe",
        extra={"Authorization": "Bearer abcdefgh"},
    )

    assert entry["component"] == "dashboard"
    assert entry["stream"] == "stderr"
    assert entry["source"] == "launcher-pipe"
    assert "swordfish" not in entry["message"]
    assert entry["extra"]["Authorization"] == "[REDACTED]"

    entries = manager.read_entries("pixeagle_stdout", component="dashboard")
    assert entries is not None
    assert len(entries) == 1
    assert entries[0]["message"] == entry["message"]


def test_runtime_log_active_handler_rotates_by_byte_budget(tmp_path):
    manager = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_rotate",
        max_total_bytes=2048,
    )

    try:
        manager.configure_python_logging()
        logger = logging.getLogger("tests.runtime_rotate")
        for index in range(30):
            logger.warning("runtime rotation probe %s %s", index, "x" * 400)
    finally:
        _remove_runtime_handlers("pixeagle_rotate")

    assert manager.component_path().stat().st_size <= 2048
    assert manager.component_path().with_name("backend.jsonl.1").exists()
