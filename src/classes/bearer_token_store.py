"""Secure external bearer-token storage and lifecycle mutations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional

from classes.api_security_types import APIPrincipal
from classes.browser_user_store import BrowserUserStoreError
from classes.secure_record_file import (
    MAX_AUTH_RECORD_FILE_BYTES,
    atomic_replace_owner_only_bytes,
    ensure_owner_only_parent,
    next_backup_path,
    read_owner_only_bytes,
)


MAX_TOKEN_ID_CHARS = 160
MAX_TOKEN_DISPLAY_NAME_CHARS = 120
MAX_TOKEN_SUBJECT_CHARS = 200
_TOKEN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_PROCESS_MUTATION_LOCK = threading.RLock()


class BearerTokenStoreError(BrowserUserStoreError):
    """Base error for invalid records, unsafe files, and failed persistence."""

    code = "bearer_token_store_error"


class BearerTokenValidationError(BearerTokenStoreError):
    """Raised when token input or stored records are invalid."""

    code = "bearer_token_validation_failed"


class BearerTokenNotFoundError(BearerTokenStoreError):
    """Raised when a requested token ID does not exist."""

    code = "bearer_token_not_found"


class BearerTokenConflictError(BearerTokenStoreError):
    """Raised when a requested token mutation conflicts with current state."""

    code = "bearer_token_conflict"


class BearerTokenPersistenceError(BearerTokenStoreError):
    """Raised when the token file cannot be read or committed safely."""

    code = "bearer_token_persistence_failed"


@dataclass(frozen=True)
class BearerTokenRecord:
    """One hashed, revocable machine-token record."""

    token_id: str
    subject: str
    token_sha256: str = field(repr=False)
    scopes: frozenset[str]
    enabled: bool = True
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

    def is_active(self, *, now: Optional[datetime] = None) -> bool:
        if not self.enabled or self.revoked_at is not None:
            return False
        if self.expires_at is None:
            return True
        current = _utc_now(now)
        return current < self.expires_at

    def state(self, *, now: Optional[datetime] = None) -> str:
        if self.revoked_at is not None:
            return "revoked"
        if not self.enabled:
            return "inactive"
        if self.expires_at is not None and _utc_now(now) >= self.expires_at:
            return "expired"
        return "active"

    def public(self, *, now: Optional[datetime] = None) -> "BearerTokenPublicRecord":
        return BearerTokenPublicRecord(
            token_id=self.token_id,
            display_name=self.display_name or self.token_id,
            subject=self.subject,
            scopes=self.scopes,
            enabled=self.enabled,
            created_at=self.created_at,
            expires_at=self.expires_at,
            revoked_at=self.revoked_at,
            last_used_at=None,
            state=self.state(now=now),
        )


@dataclass(frozen=True)
class BearerTokenPublicRecord:
    """Hash-free token metadata safe for APIs and operator interfaces."""

    token_id: str
    display_name: str
    subject: str
    scopes: frozenset[str]
    enabled: bool
    created_at: Optional[datetime]
    expires_at: Optional[datetime]
    revoked_at: Optional[datetime]
    last_used_at: Optional[datetime]
    state: str


@dataclass(frozen=True)
class BearerTokenSnapshot:
    """Immutable lookup maps for authentication and lifecycle APIs."""

    records_by_hash: Mapping[str, BearerTokenRecord] = field(repr=False)
    records_by_id: Mapping[str, BearerTokenRecord] = field(repr=False)

    @classmethod
    def from_records(cls, records: Iterable[BearerTokenRecord]) -> "BearerTokenSnapshot":
        checked = validate_token_records(records)
        return cls(
            records_by_hash=MappingProxyType(
                {record.token_sha256: record for record in checked}
            ),
            records_by_id=MappingProxyType({record.token_id: record for record in checked}),
        )

    @property
    def records(self) -> tuple[BearerTokenRecord, ...]:
        return tuple(self.records_by_id.values())

    @property
    def public_records(self) -> tuple[BearerTokenPublicRecord, ...]:
        return tuple(record.public() for record in self.records_by_id.values())


@dataclass(frozen=True)
class BearerTokenMutationResult:
    """Committed snapshot plus optional one-time credential and backup."""

    snapshot: BearerTokenSnapshot = field(repr=False)
    record: BearerTokenPublicRecord
    plaintext_token: Optional[str] = field(default=None, repr=False)
    backup_path: Optional[Path] = None
    changed: bool = True


def hash_bearer_token(token: str) -> str:
    """Hash a high-entropy bearer token for storage and lookup."""
    raw = str(token or "").strip()
    if not raw:
        raise BearerTokenValidationError("Bearer token must not be empty")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_token_record(
    *,
    token_id: str,
    plaintext_token: str,
    scopes: Iterable[str],
    subject: str = "machine-client",
    enabled: bool = True,
) -> dict[str, Any]:
    """Build a backward-compatible hashed token record for tools and tests."""
    record = BearerTokenRecord(
        token_id=_normalize_token_id(token_id),
        subject=_normalize_subject(subject),
        token_sha256=hash_bearer_token(plaintext_token),
        scopes=_normalize_scopes(scopes, token_id=token_id),
        enabled=_parse_json_bool(enabled, f"Token record {token_id!r} enabled"),
    )
    return _record_to_payload(record)


def validate_token_records(
    records: Iterable[BearerTokenRecord],
) -> tuple[BearerTokenRecord, ...]:
    checked: list[BearerTokenRecord] = []
    token_ids: set[str] = set()
    token_hashes: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, BearerTokenRecord):
            raise BearerTokenValidationError(
                f"Token record {index} must be a BearerTokenRecord"
            )
        normalized = _parse_bearer_token_record(_record_to_payload(record), index)
        if normalized.token_id in token_ids:
            raise BearerTokenValidationError(
                "Duplicate API bearer token IDs are not allowed"
            )
        if normalized.token_sha256 in token_hashes:
            raise BearerTokenValidationError(
                "Duplicate API bearer token hashes are not allowed"
            )
        token_ids.add(normalized.token_id)
        token_hashes.add(normalized.token_sha256)
        checked.append(normalized)
    return tuple(checked)


class BearerTokenStore:
    """Validate and atomically mutate one external bearer-token JSON file."""

    def __init__(self, path: Path | str) -> None:
        raw_path = Path(path).expanduser()
        self.path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path

    @property
    def mutation_lock(self) -> threading.RLock:
        return _PROCESS_MUTATION_LOCK

    def load_snapshot(self, *, allow_missing: bool = False) -> BearerTokenSnapshot:
        with self.mutation_lock:
            return BearerTokenSnapshot.from_records(
                self._load_records_unlocked(allow_missing=allow_missing)
            )

    def create_token(
        self,
        *,
        display_name: str,
        scopes: Iterable[str],
        subject: str = "qgc-video",
        expires_at: Optional[datetime] = None,
        create_if_missing: bool = True,
        backup: bool = True,
    ) -> BearerTokenMutationResult:
        with self.mutation_lock:
            current = list(
                self._load_records_unlocked(allow_missing=create_if_missing)
            )
            token_id = _new_unique_token_id(record.token_id for record in current)
            plaintext_token = f"pxe_{secrets.token_urlsafe(32)}"
            now = _utc_now()
            normalized_expiry = _normalize_optional_datetime_value(
                expires_at,
                field_name="expires_at",
            )
            if normalized_expiry is not None and normalized_expiry <= now:
                raise BearerTokenValidationError(
                    "Bearer token expiration must be in the future"
                )
            record = BearerTokenRecord(
                token_id=token_id,
                display_name=_normalize_display_name(display_name),
                subject=_normalize_subject(subject),
                token_sha256=hash_bearer_token(plaintext_token),
                scopes=_normalize_scopes(scopes, token_id=token_id),
                enabled=True,
                created_at=now,
                expires_at=normalized_expiry,
            )
            current.append(record)
            snapshot = BearerTokenSnapshot.from_records(current)
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=create_if_missing,
                backup=backup,
            )
            return BearerTokenMutationResult(
                snapshot=snapshot,
                record=record.public(now=now),
                plaintext_token=plaintext_token,
                backup_path=backup_path,
            )

    def revoke_token(
        self,
        token_id: str,
        *,
        backup: bool = True,
    ) -> BearerTokenMutationResult:
        with self.mutation_lock:
            normalized_id = _normalize_token_id(token_id)
            current = list(self._load_records_unlocked())
            index = next(
                (
                    item_index
                    for item_index, record in enumerate(current)
                    if record.token_id == normalized_id
                ),
                None,
            )
            if index is None:
                raise BearerTokenNotFoundError(
                    f"API bearer token not found: {normalized_id}"
                )
            existing = current[index]
            if existing.revoked_at is not None:
                snapshot = BearerTokenSnapshot.from_records(current)
                return BearerTokenMutationResult(
                    snapshot=snapshot,
                    record=existing.public(),
                    changed=False,
                )

            revoked_at = _utc_now()
            revoked = replace(existing, enabled=False, revoked_at=revoked_at)
            current[index] = revoked
            snapshot = BearerTokenSnapshot.from_records(current)
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=False,
                backup=backup,
            )
            return BearerTokenMutationResult(
                snapshot=snapshot,
                record=revoked.public(now=revoked_at),
                backup_path=backup_path,
            )

    def _load_records_unlocked(
        self,
        *,
        allow_missing: bool = False,
    ) -> tuple[BearerTokenRecord, ...]:
        try:
            raw = read_owner_only_bytes(
                self.path,
                label="API bearer token file",
                error_type=BearerTokenPersistenceError,
            )
        except FileNotFoundError:
            if allow_missing:
                return ()
            raise BearerTokenPersistenceError(
                f"API bearer token file does not exist: {self.path}"
            ) from None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise BearerTokenPersistenceError(
                f"API bearer token file could not be read safely: {self.path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise BearerTokenValidationError(
                f"Invalid API bearer token file JSON: {self.path}"
            ) from exc

        raw_records = payload.get("tokens") if isinstance(payload, dict) else payload
        if not isinstance(raw_records, list):
            raise BearerTokenValidationError(
                "API bearer token file must contain a tokens list"
            )
        records = tuple(
            _parse_bearer_token_record(item, index)
            for index, item in enumerate(raw_records)
        )
        return validate_token_records(records)

    def _commit_unlocked(
        self,
        records: tuple[BearerTokenRecord, ...],
        *,
        create_if_missing: bool,
        backup: bool,
    ) -> Optional[Path]:
        existing_bytes: Optional[bytes] = None
        try:
            existing_bytes = read_owner_only_bytes(
                self.path,
                label="API bearer token file",
                error_type=BearerTokenPersistenceError,
            )
        except FileNotFoundError:
            if not create_if_missing:
                raise BearerTokenPersistenceError(
                    f"API bearer token file does not exist: {self.path}"
                ) from None

        ensure_owner_only_parent(
            self.path.parent,
            label="API bearer token",
            error_type=BearerTokenPersistenceError,
        )
        backup_path: Optional[Path] = None
        if existing_bytes is not None and backup:
            backup_path = next_backup_path(self.path)
            atomic_replace_owner_only_bytes(
                backup_path,
                existing_bytes,
                label="API bearer token backup",
                error_type=BearerTokenPersistenceError,
                require_missing=True,
            )

        atomic_replace_owner_only_bytes(
            self.path,
            _serialize_records(records),
            label="API bearer token file",
            error_type=BearerTokenPersistenceError,
        )
        return backup_path


def load_bearer_token_records(path: Path) -> tuple[BearerTokenRecord, ...]:
    """Compatibility loader backed by the canonical bearer-token store."""
    return BearerTokenStore(path).load_snapshot().records


def _parse_bearer_token_record(raw: Any, index: int) -> BearerTokenRecord:
    if not isinstance(raw, dict):
        raise BearerTokenValidationError(f"Token record {index} must be an object")
    if any(key in raw for key in ("token", "plaintext_token", "access_token")):
        raise BearerTokenValidationError(
            f"Token record {index} must not contain plaintext token fields"
        )

    token_id = _normalize_token_id(raw.get("token_id"), index=index)
    subject = _normalize_subject(raw.get("subject") or token_id)
    token_sha256 = str(raw.get("token_sha256") or "").strip().lower()
    if len(token_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in token_sha256
    ):
        raise BearerTokenValidationError(
            f"Token record {token_id!r} has invalid token_sha256"
        )
    scopes = _normalize_scopes(raw.get("scopes"), token_id=token_id)
    enabled = _parse_json_bool(
        raw.get("enabled", True),
        f"Token record {token_id!r} enabled",
    )
    display_name = _normalize_optional_display_name(raw.get("display_name"))
    created_at = _parse_optional_datetime(raw.get("created_at"), index, "created_at")
    expires_at = _parse_optional_datetime(raw.get("expires_at"), index, "expires_at")
    revoked_at = _parse_optional_datetime(raw.get("revoked_at"), index, "revoked_at")
    if revoked_at is not None and enabled:
        raise BearerTokenValidationError(
            f"Token record {token_id!r} cannot be enabled after revocation"
        )

    return BearerTokenRecord(
        token_id=token_id,
        display_name=display_name,
        subject=subject,
        token_sha256=token_sha256,
        scopes=scopes,
        enabled=enabled,
        created_at=created_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def _serialize_records(records: Iterable[BearerTokenRecord]) -> bytes:
    checked = validate_token_records(records)
    payload = {"tokens": [_record_to_payload(record) for record in checked]}
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_AUTH_RECORD_FILE_BYTES:
        raise BearerTokenValidationError(
            f"API bearer token payload exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit"
        )
    return raw


def _record_to_payload(record: BearerTokenRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "token_id": record.token_id,
        "subject": record.subject,
        "token_sha256": record.token_sha256,
        "scopes": sorted(record.scopes),
        "enabled": record.enabled,
    }
    if record.display_name is not None:
        payload["display_name"] = record.display_name
    for field_name in ("created_at", "expires_at", "revoked_at"):
        value = getattr(record, field_name)
        if value is not None:
            payload[field_name] = _format_datetime(value)
    return payload


def _normalize_token_id(value: Any, *, index: Optional[int] = None) -> str:
    token_id = str(value or "").strip()
    if not token_id:
        prefix = f"Token record {index}" if index is not None else "Bearer token"
        raise BearerTokenValidationError(f"{prefix} missing token_id")
    if len(token_id) > MAX_TOKEN_ID_CHARS or not _TOKEN_ID_PATTERN.fullmatch(token_id):
        raise BearerTokenValidationError(
            "Bearer token ID must use 1-160 letters, numbers, dots, underscores, "
            "colons, or hyphens"
        )
    return token_id


def _normalize_display_name(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise BearerTokenValidationError("Token name must not be empty")
    if len(normalized) > MAX_TOKEN_DISPLAY_NAME_CHARS or _has_control_chars(normalized):
        raise BearerTokenValidationError(
            f"Token name must be printable and at most {MAX_TOKEN_DISPLAY_NAME_CHARS} characters"
        )
    return normalized


def _normalize_optional_display_name(value: Any) -> Optional[str]:
    if value in {None, ""}:
        return None
    return _normalize_display_name(value)


def _normalize_subject(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise BearerTokenValidationError("Bearer token subject must not be empty")
    if len(normalized) > MAX_TOKEN_SUBJECT_CHARS or _has_control_chars(normalized):
        raise BearerTokenValidationError(
            f"Bearer token subject must be printable and at most {MAX_TOKEN_SUBJECT_CHARS} characters"
        )
    return normalized


def _normalize_scopes(value: Any, *, token_id: str) -> frozenset[str]:
    if not isinstance(value, (list, tuple, set, frozenset)) or not value:
        raise BearerTokenValidationError(
            f"Token record {token_id!r} must declare scopes"
        )
    try:
        return APIPrincipal.bearer(
            token_id=token_id,
            subject="scope-validation",
            scopes=value,
        ).scopes
    except ValueError as exc:
        raise BearerTokenValidationError(str(exc)) from exc


def _parse_optional_datetime(
    value: Any,
    index: int,
    field_name: str,
) -> Optional[datetime]:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise BearerTokenValidationError(
            f"Token record {index} {field_name} must be a string"
        )
    try:
        return _normalize_optional_datetime_value(value, field_name=field_name)
    except BearerTokenValidationError as exc:
        raise BearerTokenValidationError(
            f"Token record {index} has invalid {field_name}"
        ) from exc


def _normalize_optional_datetime_value(
    value: Any,
    *,
    field_name: str,
) -> Optional[datetime]:
    if value in {None, ""}:
        return None
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise BearerTokenValidationError(f"Invalid {field_name}") from exc
    if not isinstance(value, datetime):
        raise BearerTokenValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return _utc_now(value).isoformat().replace("+00:00", "Z")


def _utc_now(value: Optional[datetime] = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_json_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise BearerTokenValidationError(f"{name} must be a JSON boolean")


def _new_unique_token_id(existing_ids: Iterable[str]) -> str:
    existing = set(existing_ids)
    for _attempt in range(16):
        candidate = f"ptk_{secrets.token_urlsafe(9)}"
        if candidate not in existing:
            return candidate
    raise BearerTokenConflictError("Could not allocate a unique bearer token ID")


def _has_control_chars(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


__all__ = [
    "BearerTokenConflictError",
    "BearerTokenMutationResult",
    "BearerTokenNotFoundError",
    "BearerTokenPersistenceError",
    "BearerTokenPublicRecord",
    "BearerTokenRecord",
    "BearerTokenSnapshot",
    "BearerTokenStore",
    "BearerTokenStoreError",
    "BearerTokenValidationError",
    "hash_bearer_token",
    "load_bearer_token_records",
    "make_token_record",
    "validate_token_records",
]
