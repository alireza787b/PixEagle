"""Durable API security audit events for PixEagle auth boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Mapping, Optional
from uuid import uuid4

from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
)


logger = logging.getLogger(__name__)

DEFAULT_SECURITY_AUDIT_ENABLED = True
DEFAULT_SECURITY_AUDIT_LOG_PATH = "logs/security_audit.jsonl"
DEFAULT_SECURITY_AUDIT_MAX_BYTES = 5_000_000
DEFAULT_SECURITY_AUDIT_BACKUP_COUNT = 5
MAX_SECURITY_AUDIT_MAX_BYTES = 100_000_000
MAX_SECURITY_AUDIT_BACKUP_COUNT = 20


class APISecurityAuditError(RuntimeError):
    """Raised when a durable security audit event cannot be written."""


@dataclass(frozen=True)
class APISecurityAuditLogger:
    """Append-only JSONL security audit writer with bounded local rotation."""

    enabled: bool = DEFAULT_SECURITY_AUDIT_ENABLED
    log_path: Path = Path(DEFAULT_SECURITY_AUDIT_LOG_PATH)
    max_bytes: int = DEFAULT_SECURITY_AUDIT_MAX_BYTES
    backup_count: int = DEFAULT_SECURITY_AUDIT_BACKUP_COUNT

    def __post_init__(self) -> None:
        object.__setattr__(self, "log_path", _resolve_log_path(self.log_path))
        object.__setattr__(
            self,
            "max_bytes",
            _bounded_int(
                self.max_bytes,
                "API_SECURITY_AUDIT_MAX_BYTES",
                minimum=1024,
                maximum=MAX_SECURITY_AUDIT_MAX_BYTES,
            ),
        )
        object.__setattr__(
            self,
            "backup_count",
            _bounded_int(
                self.backup_count,
                "API_SECURITY_AUDIT_BACKUP_COUNT",
                minimum=0,
                maximum=MAX_SECURITY_AUDIT_BACKUP_COUNT,
            ),
        )
        object.__setattr__(self, "_lock", threading.RLock())

    def should_record(
        self,
        *,
        audit_policy: APIAuditPolicy | str,
        outcome: str,
    ) -> bool:
        if not self.enabled:
            return False
        normalized_audit = _audit_value(audit_policy)
        normalized_outcome = _clean_token(outcome)
        return normalized_outcome != "allowed" or normalized_audit != APIAuditPolicy.NONE.value

    def record_event(
        self,
        *,
        event_type: str,
        outcome: str,
        reason: str,
        transport: str,
        method: Optional[str],
        path: str,
        status_code: Optional[int],
        principal: APIPrincipal,
        audit_policy: APIAuditPolicy | str,
        sensitivity: APISensitivity | str,
        client_host: Optional[str] = None,
        host_header: Optional[str] = None,
        origin: Optional[str] = None,
        sec_fetch_site: Optional[str] = None,
        missing_scopes: tuple[str, ...] = (),
        request_id: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Record one sanitized JSONL audit event.

        Returns False only when audit is disabled or an event does not meet the
        recording policy. Write errors raise APISecurityAuditError so callers can
        fail closed for security-critical mutations.
        """
        if not self.should_record(audit_policy=audit_policy, outcome=outcome):
            return False

        event = {
            "schema_version": 1,
            "event_id": uuid4().hex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": _clean_token(event_type),
            "outcome": _clean_token(outcome),
            "reason": _clean_token(reason),
            "transport": _clean_token(transport),
            "method": _clean_token(method) if method is not None else None,
            "path": _clean_string(path),
            "status_code": int(status_code) if status_code is not None else None,
            "audit_policy": _audit_value(audit_policy),
            "sensitivity": _sensitivity_value(sensitivity),
            "actor": _actor_payload(principal),
            "client": {
                "host": _clean_string(client_host),
                "host_header": _clean_string(host_header),
                "origin": _clean_string(origin),
                "sec_fetch_site": _clean_string(sec_fetch_site),
            },
            "missing_scopes": sorted(_clean_token(scope) for scope in missing_scopes),
            "request_id": _clean_string(request_id),
            "metadata": _sanitize_metadata(metadata or {}),
        }

        self._write_event(event)
        return True

    def _write_event(self, event: Mapping[str, Any]) -> None:
        line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with self._lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_if_needed(len(line.encode("utf-8")))
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
        except OSError as exc:
            raise APISecurityAuditError(
                f"Could not write API security audit event to {self.log_path}"
            ) from exc

    def _rotate_if_needed(self, pending_bytes: int) -> None:
        if self.backup_count <= 0 or self.max_bytes <= 0 or not self.log_path.exists():
            return
        current_size = self.log_path.stat().st_size
        if current_size + pending_bytes <= self.max_bytes:
            return

        oldest = self.log_path.with_name(f"{self.log_path.name}.{self.backup_count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(self.backup_count - 1, 0, -1):
            source = self.log_path.with_name(f"{self.log_path.name}.{index}")
            if source.exists():
                source.rename(self.log_path.with_name(f"{self.log_path.name}.{index + 1}"))
        self.log_path.rename(self.log_path.with_name(f"{self.log_path.name}.1"))


def resolve_api_security_audit_logger_from_parameters(parameters) -> APISecurityAuditLogger:
    """Build the security audit writer from flattened Parameters safely."""
    raw_config = getattr(parameters, "_raw_config", {})
    raw_streaming = raw_config.get("Streaming", {}) if isinstance(raw_config, dict) else {}
    if not isinstance(raw_streaming, dict):
        raw_streaming = {}

    enabled = _coerce_bool(
        raw_streaming.get(
            "API_SECURITY_AUDIT_ENABLED",
            getattr(parameters, "API_SECURITY_AUDIT_ENABLED", DEFAULT_SECURITY_AUDIT_ENABLED),
        ),
        "API_SECURITY_AUDIT_ENABLED",
    )
    log_path = raw_streaming.get(
        "API_SECURITY_AUDIT_LOG_PATH",
        getattr(parameters, "API_SECURITY_AUDIT_LOG_PATH", DEFAULT_SECURITY_AUDIT_LOG_PATH),
    )
    max_bytes = raw_streaming.get(
        "API_SECURITY_AUDIT_MAX_BYTES",
        getattr(parameters, "API_SECURITY_AUDIT_MAX_BYTES", DEFAULT_SECURITY_AUDIT_MAX_BYTES),
    )
    backup_count = raw_streaming.get(
        "API_SECURITY_AUDIT_BACKUP_COUNT",
        getattr(parameters, "API_SECURITY_AUDIT_BACKUP_COUNT", DEFAULT_SECURITY_AUDIT_BACKUP_COUNT),
    )
    return APISecurityAuditLogger(
        enabled=enabled,
        log_path=Path(str(log_path or DEFAULT_SECURITY_AUDIT_LOG_PATH)),
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def audit_failure_must_block(
    *,
    audit_policy: APIAuditPolicy | str,
    outcome: str,
) -> bool:
    """Return whether an audit write failure should fail closed."""
    if _clean_token(outcome) != "allowed":
        return False
    return _audit_value(audit_policy) in {
        APIAuditPolicy.MUTATION.value,
        APIAuditPolicy.SECURITY_CRITICAL.value,
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_log_path(path: Path) -> Path:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return expanded
    return _project_root() / expanded


def _bounded_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise APISecurityAuditError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise APISecurityAuditError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _coerce_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise APISecurityAuditError(f"{name} must be a boolean")


def _audit_value(value: APIAuditPolicy | str) -> str:
    try:
        return APIAuditPolicy(value).value
    except ValueError:
        return _clean_token(value)


def _sensitivity_value(value: APISensitivity | str) -> str:
    try:
        return APISensitivity(value).value
    except ValueError:
        return _clean_token(value)


def _actor_payload(principal: APIPrincipal) -> dict[str, Any]:
    credential_id = None
    if principal.kind == APIPrincipalKind.BEARER:
        credential_id = _clean_string(principal.credential_id)
    return {
        "kind": principal.kind.value,
        "subject": _clean_string(principal.subject),
        "role": _clean_string(principal.role),
        "credential_id": credential_id,
        "scopes": sorted(_clean_token(scope) for scope in principal.scopes),
    }


def _sanitize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        clean_key = _clean_token(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[clean_key] = _clean_string(value) if isinstance(value, str) else value
        elif isinstance(value, (list, tuple)):
            sanitized[clean_key] = [
                _clean_string(item) if isinstance(item, str) else item
                for item in value
                if isinstance(item, (str, int, float, bool)) or item is None
            ][:20]
        else:
            sanitized[clean_key] = _clean_string(str(value))
    return sanitized


def _clean_token(value: Any) -> str:
    cleaned = _clean_string(value, limit=128) or "unknown"
    return cleaned.replace(" ", "_").lower()


def _clean_string(value: Any, *, limit: int = 512) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not cleaned:
        return None
    return cleaned[:limit]


__all__ = [
    "APISecurityAuditError",
    "APISecurityAuditLogger",
    "DEFAULT_SECURITY_AUDIT_BACKUP_COUNT",
    "DEFAULT_SECURITY_AUDIT_ENABLED",
    "DEFAULT_SECURITY_AUDIT_LOG_PATH",
    "DEFAULT_SECURITY_AUDIT_MAX_BYTES",
    "audit_failure_must_block",
    "resolve_api_security_audit_logger_from_parameters",
]
