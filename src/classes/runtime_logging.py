"""Durable PixEagle runtime log sessions.

This module is intentionally separate from ``logging_manager.py``. The existing
manager reduces noisy repeated messages; this module owns runtime evidence:
JSONL files, session manifests, retention, redaction, and path-safe reads.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


RUNTIME_LOG_CLAIM_BOUNDARY = (
    "PixEagle process-local runtime logs only; not PX4, SITL, HIL, field, "
    "QGC receiver, follower-response, or real-aircraft proof."
)

DEFAULT_RUNTIME_LOG_DIR = "logs/runtime"
DEFAULT_COMPONENT = "backend"
DEFAULT_MAX_SESSIONS = 20
DEFAULT_MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_READ_LIMIT = 1000
DEFAULT_READ_LIMIT = 200

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,94}[A-Za-z0-9])?$")
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9])?$")
_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}
_SECRET_PATTERNS = (
    (
        re.compile(
            r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie|x-pixeagle-csrf)"
            r"(\s*[:=]\s*)([^,\r\n]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)\b(password|passwd|token|secret|api[_-]?key|csrf|session[_-]?id)"
            r"(\s*[:=]\s*)([^,\s\"'}]{3,})"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"([a-z][a-z0-9+.-]*://)([^/@\s]+)@"),
        r"\1[REDACTED]@",
    ),
)
_SECRET_KEY_RE = re.compile(
    r"(?i)(authorization|proxy-authorization|cookie|set-cookie|password|passwd|"
    r"token|secret|api[_-]?key|csrf|session[_-]?id)"
)


def utc_now_iso() -> str:
    """Return a compact UTC timestamp with millisecond precision."""
    value = datetime.now(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def generate_run_id() -> str:
    """Generate a sortable, path-safe PixEagle runtime session id."""
    value = datetime.now(timezone.utc).strftime("pixeagle_%Y%m%dT%H%M%SZ")
    return f"{value}_{os.getpid()}"


def redact_text(value: Any) -> str:
    """Redact common credential patterns from a string representation."""
    text = str(value)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    """Recursively redact common credential keys and string values."""
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = redact_value(item)
        return redacted
    if isinstance(value, list | tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def sanitize_log_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Apply read-time redaction to a parsed log entry before returning it."""
    sanitized = redact_value(entry)
    return sanitized if isinstance(sanitized, dict) else {}


class RuntimeJSONLFormatter(logging.Formatter):
    """Format standard logging records as PixEagle runtime JSONL entries."""

    def __init__(self, run_id: str):
        super().__init__()
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S."
            )
            + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "component": getattr(record, "pixeagle_component", record.name),
            "logger": record.name,
            "run_id": self.run_id,
            "pid": record.process,
            "thread": record.threadName,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": redact_text(record.getMessage()),
        }
        extra = getattr(record, "pixeagle_extra", None)
        if extra is not None:
            entry["extra"] = redact_value(extra)
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            entry["traceback"] = redact_text(record.exc_text)
        return json.dumps(entry, ensure_ascii=True, default=str)


class RuntimeLogSessionManager:
    """Manage one active runtime log session and path-safe historical reads."""

    def __init__(
        self,
        *,
        base_dir: str | Path | None = None,
        run_id: str | None = None,
        max_sessions: int | None = None,
        max_total_bytes: int | None = None,
    ) -> None:
        raw_base_dir = base_dir or os.environ.get(
            "PIXEAGLE_RUNTIME_LOG_DIR",
            DEFAULT_RUNTIME_LOG_DIR,
        )
        self.base_dir = Path(raw_base_dir).expanduser().resolve()
        self.run_id = self._validate_run_id(
            run_id or os.environ.get("PIXEAGLE_RUN_ID") or generate_run_id()
        )
        self.max_sessions = self._positive_int(
            max_sessions,
            os.environ.get("PIXEAGLE_RUNTIME_LOG_MAX_SESSIONS"),
            DEFAULT_MAX_SESSIONS,
        )
        self.max_total_bytes = self._positive_int(
            max_total_bytes,
            os.environ.get("PIXEAGLE_RUNTIME_LOG_MAX_BYTES"),
            DEFAULT_MAX_TOTAL_BYTES,
        )
        self._lock = threading.Lock()
        self._configured = False

    @staticmethod
    def _positive_int(explicit: int | None, env_value: str | None, default: int) -> int:
        value = explicit if explicit is not None else env_value
        try:
            parsed = int(value) if value is not None else default
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _validate_run_id(run_id: str) -> str:
        normalized = str(run_id or "").strip()
        if not _RUN_ID_RE.fullmatch(normalized):
            raise ValueError(f"Invalid PixEagle runtime log run id: {run_id!r}")
        return normalized

    @staticmethod
    def _validate_component(component: str) -> str:
        normalized = str(component or DEFAULT_COMPONENT).strip()
        if not _COMPONENT_RE.fullmatch(normalized):
            raise ValueError(f"Invalid PixEagle runtime log component: {component!r}")
        return normalized

    @staticmethod
    def _validate_level(level: str | None) -> str | None:
        normalized = str(level or "").strip().upper()
        if not normalized:
            return None
        if normalized not in _LEVEL_ORDER:
            raise ValueError(f"Invalid PixEagle runtime log level: {level!r}")
        return normalized

    @property
    def session_dir(self) -> Path:
        return self._session_dir_for(self.run_id)

    @property
    def manifest_path(self) -> Path:
        return self.session_dir / "manifest.json"

    def component_path(self, component: str = DEFAULT_COMPONENT) -> Path:
        return self._component_path_for(self.run_id, component)

    def _session_dir_for(self, run_id: str) -> Path:
        safe_run_id = self._validate_run_id(run_id)
        path = (self.base_dir / safe_run_id).resolve()
        try:
            path.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Runtime log session escapes base dir: {run_id!r}") from exc
        return path

    def _component_path_for(self, run_id: str, component: str) -> Path:
        safe_component = self._validate_component(component)
        path = (self._session_dir_for(run_id) / "components" / f"{safe_component}.jsonl").resolve()
        try:
            path.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError(f"Runtime log component escapes base dir: {component!r}") from exc
        return path

    def initialize_session(self) -> dict[str, Any]:
        """Create session directories and manifest if needed."""
        with self._lock:
            components_dir = self.session_dir / "components"
            components_dir.mkdir(parents=True, exist_ok=True)
            self.component_path(DEFAULT_COMPONENT).touch(exist_ok=True)
            manifest = self._build_manifest()
            if not self.manifest_path.exists():
                self.manifest_path.write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            self.cleanup_retention()
            return self.read_manifest(self.run_id) or manifest

    def _build_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "app": "pixeagle",
            "run_id": self.run_id,
            "created_at": utc_now_iso(),
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "python": sys.version.split()[0],
            "component_files": {
                DEFAULT_COMPONENT: str(self.component_path(DEFAULT_COMPONENT)),
            },
            "claim_boundary": RUNTIME_LOG_CLAIM_BOUNDARY,
        }

    def configure_python_logging(self, level: int = logging.INFO) -> dict[str, Any]:
        """Attach one JSONL handler to the root logger for this process."""
        manifest = self.initialize_session()
        with self._lock:
            if self._configured:
                return manifest
            handler = RotatingFileHandler(
                self.component_path(DEFAULT_COMPONENT),
                mode="a",
                maxBytes=max(1024, self.max_total_bytes // 2),
                backupCount=1,
                encoding="utf-8",
            )
            handler.setFormatter(RuntimeJSONLFormatter(self.run_id))
            handler.setLevel(logging.DEBUG)
            handler._pixeagle_runtime_handler = True  # type: ignore[attr-defined]
            handler._pixeagle_run_id = self.run_id  # type: ignore[attr-defined]

            root_logger = logging.getLogger()
            duplicate = any(
                getattr(existing, "_pixeagle_runtime_handler", False)
                and getattr(existing, "_pixeagle_run_id", None) == self.run_id
                for existing in root_logger.handlers
            )
            if not duplicate:
                root_logger.addHandler(handler)
            root_logger.setLevel(min(root_logger.level or level, level))
            self._configured = True
        return manifest

    def status(self) -> dict[str, Any]:
        manifest = self.read_manifest(self.run_id)
        return {
            "enabled": True,
            "active_run_id": self.run_id,
            "base_dir": str(self.base_dir),
            "active_session_dir": str(self.session_dir),
            "manifest": manifest,
            "claim_boundary": RUNTIME_LOG_CLAIM_BOUNDARY,
        }

    def read_manifest(self, run_id: str) -> Optional[dict[str, Any]]:
        path = self._session_dir_for(run_id) / "manifest.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.base_dir.is_dir():
            return []
        safe_limit = max(1, min(int(limit or 50), 200))
        sessions: list[dict[str, Any]] = []
        for child in self.base_dir.iterdir():
            if not child.is_dir() or not _RUN_ID_RE.fullmatch(child.name):
                continue
            manifest = self.read_manifest(child.name)
            size_bytes = self._dir_size(child)
            modified = child.stat().st_mtime
            sessions.append(
                {
                    "run_id": child.name,
                    "active": child.name == self.run_id,
                    "created_at": (manifest or {}).get("created_at"),
                    "size_bytes": size_bytes,
                    "modified_at": datetime.fromtimestamp(
                        modified,
                        timezone.utc,
                    ).isoformat().replace("+00:00", "Z"),
                    "components": self._list_components(child.name),
                    "claim_boundary": RUNTIME_LOG_CLAIM_BOUNDARY,
                }
            )
        sessions.sort(key=lambda item: (item.get("created_at") or "", item["run_id"]), reverse=True)
        return sessions[:safe_limit]

    def _list_components(self, run_id: str) -> list[str]:
        components_dir = self._session_dir_for(run_id) / "components"
        if not components_dir.is_dir():
            return []
        return sorted(
            path.stem
            for path in components_dir.glob("*.jsonl")
            if _COMPONENT_RE.fullmatch(path.stem)
        )

    def read_entries(
        self,
        run_id: str,
        *,
        component: str = DEFAULT_COMPONENT,
        level: str | None = None,
        limit: int = DEFAULT_READ_LIMIT,
        offset: int = 0,
        since: str | None = None,
    ) -> Optional[list[dict[str, Any]]]:
        path = self._component_path_for(run_id, component)
        if not path.is_file():
            return None
        normalized_level = self._validate_level(level)
        min_level = _LEVEL_ORDER.get(normalized_level, 0)
        safe_limit = max(1, min(int(limit or DEFAULT_READ_LIMIT), MAX_READ_LIMIT))
        safe_offset = max(0, int(offset or 0))

        entries: list[dict[str, Any]] = []
        matched_index = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                entry_level = str(entry.get("level", "")).upper()
                if normalized_level and _LEVEL_ORDER.get(entry_level, 0) < min_level:
                    continue
                if since and str(entry.get("ts", "")) <= since:
                    continue
                if matched_index < safe_offset:
                    matched_index += 1
                    continue
                matched_index += 1
                entries.append(sanitize_log_entry(entry))
                if len(entries) >= safe_limit:
                    break
        return entries

    def cleanup_retention(self) -> None:
        if not self.base_dir.is_dir():
            return
        session_dirs = [
            child
            for child in self.base_dir.iterdir()
            if child.is_dir() and _RUN_ID_RE.fullmatch(child.name)
        ]
        session_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for stale in session_dirs[self.max_sessions :]:
            if stale.name != self.run_id:
                shutil.rmtree(stale, ignore_errors=True)

        session_dirs = [
            child
            for child in self.base_dir.iterdir()
            if child.is_dir() and _RUN_ID_RE.fullmatch(child.name)
        ]
        session_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        total_size = sum(self._dir_size(path) for path in session_dirs)
        for stale in reversed(session_dirs):
            if total_size <= self.max_total_bytes or stale.name == self.run_id:
                continue
            stale_size = self._dir_size(stale)
            shutil.rmtree(stale, ignore_errors=True)
            total_size -= stale_size

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
        return total


_manager: RuntimeLogSessionManager | None = None
_manager_lock = threading.Lock()


def get_runtime_log_manager() -> RuntimeLogSessionManager:
    """Return the process-global PixEagle runtime log manager."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = RuntimeLogSessionManager()
        return _manager


def configure_runtime_logging(level: int = logging.INFO) -> dict[str, Any]:
    """Configure process-global runtime logging and return the manifest."""
    return get_runtime_log_manager().configure_python_logging(level=level)


def reset_runtime_log_manager_for_tests(manager: RuntimeLogSessionManager | None = None) -> None:
    """Replace the process-global manager in tests."""
    global _manager
    with _manager_lock:
        _manager = manager


__all__ = [
    "DEFAULT_COMPONENT",
    "DEFAULT_READ_LIMIT",
    "MAX_READ_LIMIT",
    "RUNTIME_LOG_CLAIM_BOUNDARY",
    "RuntimeJSONLFormatter",
    "RuntimeLogSessionManager",
    "configure_runtime_logging",
    "generate_run_id",
    "get_runtime_log_manager",
    "redact_text",
    "redact_value",
    "reset_runtime_log_manager_for_tests",
    "utc_now_iso",
]
