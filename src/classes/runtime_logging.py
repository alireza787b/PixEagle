"""Durable PixEagle runtime log sessions.

This module is intentionally separate from ``logging_manager.py``. The existing
manager reduces noisy repeated messages; this module owns runtime evidence:
JSONL files, session manifests, retention, redaction, and path-safe reads.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import hashlib
import io
import os
import re
import shutil
import sys
import threading
import tarfile
import tempfile
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


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
EXPORT_MEDIA_TYPE = "application/gzip"

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


@dataclass(frozen=True)
class RuntimeLogReadWindow:
    """One bounded read window from a runtime component log."""

    entries: list[dict[str, Any]]
    offset: int
    limit: int
    next_offset: int
    tail: bool
    matched_total: int | None = None
    has_more: bool | None = None


@dataclass(frozen=True)
class RuntimeLogExport:
    """One temporary sanitized runtime log export bundle."""

    path: Path
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    run_id: str
    claim_boundary: str = RUNTIME_LOG_CLAIM_BOUNDARY

    def cleanup(self) -> None:
        """Remove the temporary export file after it has been served."""
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            return


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
        self._lock = threading.RLock()
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

    def initialize_session(self, components: Iterable[str] | None = None) -> dict[str, Any]:
        """Create session directories and manifest if needed."""
        with self._lock:
            components_dir = self.session_dir / "components"
            components_dir.mkdir(parents=True, exist_ok=True)
            component_names = self._normalize_component_set(
                [DEFAULT_COMPONENT, *(components or [])]
            )
            for component_name in component_names:
                self.component_path(component_name).touch(exist_ok=True)
            manifest = self._build_manifest(component_names)
            if self.manifest_path.exists():
                manifest = self._merge_manifest_components(
                    self.read_manifest(self.run_id) or manifest,
                    component_names,
                )
                self._write_manifest(manifest)
            else:
                self.manifest_path.write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            self.cleanup_retention()
            return self.read_manifest(self.run_id) or manifest

    def _build_manifest(self, components: Iterable[str] | None = None) -> dict[str, Any]:
        component_names = self._normalize_component_set(
            components or [DEFAULT_COMPONENT]
        )
        return {
            "schema_version": 1,
            "app": "pixeagle",
            "run_id": self.run_id,
            "created_at": utc_now_iso(),
            "pid": os.getpid(),
            "cwd": str(Path.cwd()),
            "python": sys.version.split()[0],
            "component_files": self._component_files_payload(component_names),
            "claim_boundary": RUNTIME_LOG_CLAIM_BOUNDARY,
        }

    def _component_files_payload(self, components: Iterable[str]) -> dict[str, str]:
        return {
            component: str(self.component_path(component))
            for component in self._normalize_component_set(components)
        }

    def _normalize_component_set(self, components: Iterable[str]) -> list[str]:
        seen: dict[str, None] = {}
        for component in components:
            seen[self._validate_component(component)] = None
        return sorted(seen)

    def _write_manifest(self, manifest: Mapping[str, Any]) -> None:
        self.manifest_path.write_text(
            json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _merge_manifest_components(
        self,
        manifest: Mapping[str, Any],
        components: Iterable[str],
    ) -> dict[str, Any]:
        merged = dict(manifest)
        component_files = dict(merged.get("component_files") or {})
        component_files.update(self._component_files_payload(components))
        merged["component_files"] = component_files
        merged.setdefault("claim_boundary", RUNTIME_LOG_CLAIM_BOUNDARY)
        return merged

    def register_component(self, component: str) -> dict[str, Any]:
        """Ensure a component JSONL file exists and is listed in the manifest."""
        safe_component = self._validate_component(component)
        with self._lock:
            (self.session_dir / "components").mkdir(parents=True, exist_ok=True)
            self.component_path(safe_component).touch(exist_ok=True)
            if self.manifest_path.exists():
                manifest = self._merge_manifest_components(
                    self.read_manifest(self.run_id) or self._build_manifest(),
                    [safe_component],
                )
            else:
                manifest = self._build_manifest([DEFAULT_COMPONENT, safe_component])
            self._write_manifest(manifest)
            self.cleanup_retention()
            return manifest

    def append_component_message(
        self,
        component: str,
        message: Any,
        *,
        level: str = "INFO",
        stream: str = "stdout",
        source: str = "process",
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one sanitized stdout/stderr-style message to a component log."""
        safe_component = self._validate_component(component)
        normalized_level = self._validate_level(level) or "INFO"
        path = self.component_path(safe_component)
        entry: dict[str, Any] = {
            "ts": utc_now_iso(),
            "level": normalized_level,
            "component": safe_component,
            "logger": f"pixeagle.component.{safe_component}",
            "run_id": self.run_id,
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
            "stream": redact_text(stream),
            "source": redact_text(source),
            "message": redact_text(str(message).rstrip("\r\n")),
        }
        if extra is not None:
            entry["extra"] = redact_value(extra)
        with self._lock:
            if not path.is_file():
                self.register_component(safe_component)
            self._rotate_component_if_needed(path)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")
        return sanitize_log_entry(entry)

    def _rotate_component_if_needed(self, path: Path) -> None:
        max_component_bytes = max(1024, self.max_total_bytes // 4)
        try:
            if path.exists() and path.stat().st_size >= max_component_bytes:
                backup = path.with_name(f"{path.name}.1")
                backup.unlink(missing_ok=True)
                path.rename(backup)
                path.touch()
        except OSError:
            return

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
        window = self.read_entry_window(
            run_id,
            component=component,
            level=level,
            limit=limit,
            offset=offset,
            since=since,
        )
        return None if window is None else window.entries

    def read_entry_window(
        self,
        run_id: str,
        *,
        component: str = DEFAULT_COMPONENT,
        level: str | None = None,
        limit: int = DEFAULT_READ_LIMIT,
        offset: int = 0,
        since: str | None = None,
        tail: bool = False,
    ) -> Optional[RuntimeLogReadWindow]:
        """Read a bounded component log window plus cursor metadata."""
        path = self._component_path_for(run_id, component)
        read_paths = self._component_paths_for_read(run_id, component)
        if not read_paths:
            return None
        normalized_level = self._validate_level(level)
        min_level = _LEVEL_ORDER.get(normalized_level, 0)
        safe_limit = max(1, min(int(limit or DEFAULT_READ_LIMIT), MAX_READ_LIMIT))
        safe_offset = max(0, int(offset or 0))

        if tail:
            entries_tail: deque[dict[str, Any]] = deque(maxlen=safe_limit)
            matched_total = 0
            for read_path in read_paths:
                with read_path.open("r", encoding="utf-8") as handle:
                    for entry in self._matching_entries(
                        handle,
                        normalized_level,
                        min_level,
                        since,
                    ):
                        matched_total += 1
                        entries_tail.append(sanitize_log_entry(entry))
            entries = list(entries_tail)
            actual_offset = max(0, matched_total - len(entries))
            return RuntimeLogReadWindow(
                entries=entries,
                offset=actual_offset,
                limit=safe_limit,
                next_offset=matched_total,
                tail=True,
                matched_total=matched_total,
                has_more=actual_offset > 0,
            )

        entries: list[dict[str, Any]] = []
        matched_index = 0
        has_more = False
        for read_path in read_paths:
            with read_path.open("r", encoding="utf-8") as handle:
                for entry in self._matching_entries(handle, normalized_level, min_level, since):
                    if matched_index < safe_offset:
                        matched_index += 1
                        continue
                    if len(entries) >= safe_limit:
                        has_more = True
                        break
                    matched_index += 1
                    entries.append(sanitize_log_entry(entry))
            if has_more:
                break
        return RuntimeLogReadWindow(
            entries=entries,
            offset=safe_offset,
            limit=safe_limit,
            next_offset=matched_index,
            tail=False,
            matched_total=None if has_more else matched_index,
            has_more=has_more,
        )

    def _matching_entries(
        self,
        handle: Iterable[str],
        normalized_level: str | None,
        min_level: int,
        since: str | None,
    ) -> Iterable[dict[str, Any]]:
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
            yield entry

    def export_session_bundle(self, run_id: str) -> Optional[RuntimeLogExport]:
        """Create a temporary sanitized tar.gz bundle for one runtime session."""
        safe_run_id = self._validate_run_id(run_id)
        session_dir = self._session_dir_for(safe_run_id)
        manifest = self.read_manifest(safe_run_id)
        if not session_dir.is_dir() or manifest is None:
            return None

        export_dir = (self.base_dir / ".exports").resolve()
        try:
            export_dir.relative_to(self.base_dir)
        except ValueError as exc:
            raise ValueError("Runtime log export directory escapes base dir") from exc
        export_dir.mkdir(parents=True, exist_ok=True)

        fd, raw_export_path = tempfile.mkstemp(
            prefix=f"{safe_run_id}-",
            suffix=".tar.gz",
            dir=export_dir,
        )
        os.close(fd)
        export_path = Path(raw_export_path)
        exported_at = utc_now_iso()
        exported_components: dict[str, list[str]] = {}
        skipped_invalid_lines: dict[str, int] = {}

        try:
            with tarfile.open(export_path, mode="w:gz") as archive:
                self._add_tar_bytes(
                    archive,
                    "README.txt",
                    (
                        "PixEagle runtime log evidence bundle\n\n"
                        f"Run ID: {safe_run_id}\n"
                        f"Exported at: {exported_at}\n\n"
                        f"Claim boundary: {RUNTIME_LOG_CLAIM_BOUNDARY}\n\n"
                        "This bundle contains PixEagle process-local runtime "
                        "logs only. It is not PX4, SITL, HIL, field, QGC "
                        "receiver, follower-response, or real-aircraft proof.\n"
                    ).encode("utf-8"),
                )
                self._add_tar_json(
                    archive,
                    "manifest.json",
                    redact_value(manifest),
                )

                for component in self._list_components(safe_run_id):
                    for path in self._component_paths_for_export(
                        safe_run_id,
                        component,
                    ):
                        if not path.is_file():
                            continue
                        payload, skipped = self._sanitized_jsonl_bytes(path)
                        arcname = f"components/{path.name}"
                        self._add_tar_bytes(archive, arcname, payload)
                        exported_components.setdefault(component, []).append(arcname)
                        if skipped:
                            skipped_invalid_lines[arcname] = skipped

                self._add_tar_json(
                    archive,
                    "export_manifest.json",
                    {
                        "schema_version": 1,
                        "app": "pixeagle",
                        "source": "runtime_log_export",
                        "run_id": safe_run_id,
                        "exported_at": exported_at,
                        "components": exported_components,
                        "skipped_invalid_lines": skipped_invalid_lines,
                        "claim_boundary": RUNTIME_LOG_CLAIM_BOUNDARY,
                    },
                )
        except Exception:
            export_path.unlink(missing_ok=True)
            raise

        size_bytes = export_path.stat().st_size
        sha256 = hashlib.sha256(export_path.read_bytes()).hexdigest()
        return RuntimeLogExport(
            path=export_path,
            filename=f"{safe_run_id}-runtime-logs.tar.gz",
            media_type=EXPORT_MEDIA_TYPE,
            size_bytes=size_bytes,
            sha256=sha256,
            run_id=safe_run_id,
        )

    def _component_paths_for_export(self, run_id: str, component: str) -> list[Path]:
        return self._component_paths_for_read(run_id, component)

    def _component_paths_for_read(self, run_id: str, component: str) -> list[Path]:
        path = self._component_path_for(run_id, component)
        paths = [path.with_name(f"{path.name}.1"), path]
        return [candidate for candidate in paths if candidate.is_file()]

    @staticmethod
    def _add_tar_bytes(archive: tarfile.TarFile, arcname: str, payload: bytes) -> None:
        info = tarfile.TarInfo(arcname)
        info.size = len(payload)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(payload))

    def _add_tar_json(
        self,
        archive: tarfile.TarFile,
        arcname: str,
        payload: Mapping[str, Any],
    ) -> None:
        self._add_tar_bytes(
            archive,
            arcname,
            (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode(
                "utf-8"
            ),
        )

    def _sanitized_jsonl_bytes(self, path: Path) -> tuple[bytes, int]:
        lines: list[str] = []
        skipped = 0
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if not isinstance(payload, dict):
                    skipped += 1
                    continue
                lines.append(
                    json.dumps(
                        sanitize_log_entry(payload),
                        ensure_ascii=True,
                        default=str,
                    )
                )
        return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"), skipped

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
    "EXPORT_MEDIA_TYPE",
    "MAX_READ_LIMIT",
    "RUNTIME_LOG_CLAIM_BOUNDARY",
    "RuntimeLogExport",
    "RuntimeLogReadWindow",
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
