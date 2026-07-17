"""Secure external browser-session user storage for PixEagle.

This module is the sole authority for browser-user record validation and JSON
serialization. Runtime and setup callers share one process-level mutation lock
so a successful file commit can be published as one immutable runtime snapshot.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional

from classes.api_security_types import ROLE_SCOPES


PBKDF2_SHA256_SCHEME = "pbkdf2_sha256"
DEFAULT_PBKDF2_ITERATIONS = 310_000
MIN_PBKDF2_ITERATIONS = 210_000
MAX_PBKDF2_ITERATIONS = 1_200_000
MIN_PASSWORD_SALT_BYTES = 16
MAX_PASSWORD_SALT_BYTES = 64
PASSWORD_DIGEST_BYTES = 32
MAX_AUTH_RECORD_FILE_BYTES = 1024 * 1024
MAX_BROWSER_PASSWORD_CHARS = 4096
MAX_BROWSER_USERNAME_CHARS = 120
_USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,118}[a-z0-9])?$")
_PROCESS_MUTATION_LOCK = threading.RLock()


class BrowserUserStoreError(ValueError):
    """Base error for invalid records, unsafe files, and failed persistence."""

    code = "browser_user_store_error"


class BrowserUserValidationError(BrowserUserStoreError):
    """Raised when user input or stored records are invalid."""

    code = "browser_user_validation_failed"


class BrowserUserNotFoundError(BrowserUserStoreError):
    """Raised when a requested browser user does not exist."""

    code = "browser_user_not_found"


class BrowserUserConflictError(BrowserUserStoreError):
    """Raised when a requested mutation conflicts with current state."""

    code = "browser_user_conflict"


class BrowserUserInvariantError(BrowserUserConflictError):
    """Raised when a mutation would remove the final enabled user or admin."""

    code = "browser_user_invariant_violation"


class BrowserUserPersistenceError(BrowserUserStoreError):
    """Raised when the external user file cannot be read or committed safely."""

    code = "browser_user_persistence_failed"


@dataclass(frozen=True)
class BrowserUserRecord:
    """One validated credential record; the password hash is internal-only."""

    username: str
    role: str
    password_pbkdf2_sha256: str = field(repr=False)
    enabled: bool = True

    def public(self) -> "BrowserUserPublicRecord":
        return BrowserUserPublicRecord(
            username=self.username,
            role=self.role,
            enabled=self.enabled,
        )


@dataclass(frozen=True)
class BrowserUserPublicRecord:
    """Credential-free user metadata safe for CLI and API responses."""

    username: str
    role: str
    enabled: bool


@dataclass(frozen=True)
class BrowserUserSnapshot:
    """Immutable internal credential snapshot plus a credential-free view."""

    records_by_username: Mapping[str, BrowserUserRecord] = field(repr=False)

    @classmethod
    def from_records(cls, records: Iterable[BrowserUserRecord]) -> "BrowserUserSnapshot":
        normalized_records = validate_user_records(records)
        return cls(
            records_by_username=MappingProxyType(
                {record.username: record for record in normalized_records}
            )
        )

    @property
    def records(self) -> tuple[BrowserUserRecord, ...]:
        return tuple(self.records_by_username.values())

    @property
    def public_records(self) -> tuple[BrowserUserPublicRecord, ...]:
        return tuple(record.public() for record in self.records_by_username.values())


@dataclass(frozen=True)
class BrowserUserMutationResult:
    """Committed immutable snapshot and optional owner-only backup path."""

    snapshot: BrowserUserSnapshot = field(repr=False)
    record: Optional[BrowserUserPublicRecord] = None
    backup_path: Optional[Path] = None


def normalize_username(value: Any) -> str:
    username = str(value or "").strip().lower()
    if not username:
        raise BrowserUserValidationError("Username must not be empty")
    if len(username) > MAX_BROWSER_USERNAME_CHARS or not _USERNAME_PATTERN.fullmatch(
        username
    ):
        raise BrowserUserValidationError(
            "Username must use 1-120 lowercase letters, numbers, dots, underscores, "
            "or hyphens, and must start and end with a letter or number"
        )
    return username


def normalize_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    if role not in ROLE_SCOPES:
        allowed = ", ".join(sorted(ROLE_SCOPES))
        raise BrowserUserValidationError(
            f"Unsupported browser-user role {value!r}; expected one of: {allowed}"
        )
    return role


def normalize_plaintext_password(value: Any) -> str:
    if not isinstance(value, str):
        raise BrowserUserValidationError("Password must be a string")
    if not value:
        raise BrowserUserValidationError("Password must not be empty")
    if len(value) > MAX_BROWSER_PASSWORD_CHARS:
        raise BrowserUserValidationError(
            f"Password must not exceed {MAX_BROWSER_PASSWORD_CHARS} characters"
        )
    return value


def hash_password_pbkdf2_sha256(
    password: str,
    *,
    salt: Optional[bytes] = None,
    iterations: int = DEFAULT_PBKDF2_ITERATIONS,
) -> str:
    """Return a Django-style PBKDF2-SHA256 browser-user password hash."""
    raw_password = normalize_plaintext_password(password)
    normalized_iterations = _normalize_bounded_int(
        iterations,
        "password iterations",
        minimum=MIN_PBKDF2_ITERATIONS,
        maximum=MAX_PBKDF2_ITERATIONS,
    )
    raw_salt = salt or secrets.token_bytes(16)
    _validate_password_salt(raw_salt)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        raw_salt,
        normalized_iterations,
    )
    return "$".join(
        (
            PBKDF2_SHA256_SCHEME,
            str(normalized_iterations),
            base64.b64encode(raw_salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password_pbkdf2_sha256(*, password: str, encoded: str) -> bool:
    """Verify a supplied password against one validated PBKDF2-SHA256 hash."""
    try:
        iterations, salt, expected = _parse_pbkdf2_sha256_hash(encoded)
    except BrowserUserStoreError:
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def make_user_record(
    *,
    username: str,
    plaintext_password: str,
    role: str = "operator",
    enabled: bool = True,
) -> dict[str, Any]:
    """Build a serialized user record without retaining plaintext."""
    record = make_browser_user_record(
        username=username,
        plaintext_password=plaintext_password,
        role=role,
        enabled=enabled,
    )
    return _record_to_payload(record)


def make_browser_user_record(
    *,
    username: str,
    plaintext_password: str,
    role: str = "operator",
    enabled: bool = True,
) -> BrowserUserRecord:
    return BrowserUserRecord(
        username=normalize_username(username),
        role=normalize_role(role),
        password_pbkdf2_sha256=hash_password_pbkdf2_sha256(plaintext_password),
        enabled=_parse_json_bool(enabled, "Browser-user enabled"),
    )


def validate_user_records(
    records: Iterable[BrowserUserRecord],
) -> tuple[BrowserUserRecord, ...]:
    normalized: list[BrowserUserRecord] = []
    usernames: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, BrowserUserRecord):
            raise BrowserUserValidationError(
                f"Browser-user record {index} must be a BrowserUserRecord"
            )
        checked = _parse_user_record(_record_to_payload(record), index)
        if checked.username in usernames:
            raise BrowserUserValidationError(
                "Duplicate API session usernames are not allowed"
            )
        usernames.add(checked.username)
        normalized.append(checked)
    return tuple(normalized)


def validate_required_invariants(
    records: Iterable[BrowserUserRecord],
    *,
    require_enabled_admin: bool = False,
) -> None:
    """Validate availability plus an optional enabled-admin requirement.

    Existing advanced deployments may intentionally contain only operator or
    viewer accounts and use the host CLI for administration. Mutations preserve
    an enabled administrator once one exists, while runtime admin APIs can
    require the stronger invariant explicitly.
    """
    checked = validate_user_records(records)
    if not any(record.enabled for record in checked):
        raise BrowserUserInvariantError(
            "At least one enabled browser-session user is required"
        )
    if require_enabled_admin and not _has_enabled_admin(checked):
        raise BrowserUserInvariantError(
            "At least one enabled browser-session administrator is required"
        )


def _has_enabled_admin(records: Iterable[BrowserUserRecord]) -> bool:
    return any(record.enabled and record.role == "admin" for record in records)


def _admin_required_after_mutation(
    current: Iterable[BrowserUserRecord],
    explicit: Optional[bool],
) -> bool:
    if explicit is not None:
        return bool(explicit)
    return _has_enabled_admin(current)


class BrowserUserStore:
    """Validate and atomically mutate one external browser-user JSON file."""

    def __init__(self, path: Path | str) -> None:
        raw_path = Path(path).expanduser()
        self.path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path

    @property
    def mutation_lock(self) -> threading.RLock:
        return _PROCESS_MUTATION_LOCK

    def load_snapshot(self, *, allow_missing: bool = False) -> BrowserUserSnapshot:
        with self.mutation_lock:
            return BrowserUserSnapshot.from_records(
                self._load_records_unlocked(allow_missing=allow_missing)
            )

    def public_snapshot(self) -> tuple[BrowserUserPublicRecord, ...]:
        return self.load_snapshot().public_records

    def replace_all(
        self,
        records: Iterable[BrowserUserRecord],
        *,
        create_if_missing: bool,
        backup: bool = True,
        require_enabled_admin: bool = False,
    ) -> BrowserUserMutationResult:
        with self.mutation_lock:
            snapshot = BrowserUserSnapshot.from_records(records)
            validate_required_invariants(
                snapshot.records,
                require_enabled_admin=require_enabled_admin,
            )
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=create_if_missing,
                backup=backup,
            )
            return BrowserUserMutationResult(
                snapshot=snapshot,
                backup_path=backup_path,
            )

    def create_user(
        self,
        *,
        username: str,
        plaintext_password: str,
        role: str,
        enabled: bool = True,
        create_if_missing: bool = False,
        backup: bool = True,
        require_enabled_admin: Optional[bool] = None,
    ) -> BrowserUserMutationResult:
        with self.mutation_lock:
            current = list(
                self._load_records_unlocked(allow_missing=create_if_missing)
            )
            record = make_browser_user_record(
                username=username,
                plaintext_password=plaintext_password,
                role=role,
                enabled=enabled,
            )
            if any(item.username == record.username for item in current):
                raise BrowserUserConflictError(
                    f"Browser-session user already exists: {record.username}"
                )
            previous = tuple(current)
            current.append(record)
            snapshot = BrowserUserSnapshot.from_records(current)
            validate_required_invariants(
                snapshot.records,
                require_enabled_admin=_admin_required_after_mutation(
                    previous,
                    require_enabled_admin,
                ),
            )
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=create_if_missing,
                backup=backup,
            )
            return BrowserUserMutationResult(
                snapshot=snapshot,
                record=record.public(),
                backup_path=backup_path,
            )

    def update_user(
        self,
        username: str,
        *,
        role: Optional[str] = None,
        enabled: Optional[bool] = None,
        plaintext_password: Optional[str] = None,
        backup: bool = True,
        require_enabled_admin: Optional[bool] = None,
    ) -> BrowserUserMutationResult:
        with self.mutation_lock:
            normalized_username = normalize_username(username)
            current = list(self._load_records_unlocked())
            index = self._find_index(current, normalized_username)
            existing = current[index]
            updated = BrowserUserRecord(
                username=existing.username,
                role=normalize_role(role) if role is not None else existing.role,
                password_pbkdf2_sha256=(
                    hash_password_pbkdf2_sha256(plaintext_password)
                    if plaintext_password is not None
                    else existing.password_pbkdf2_sha256
                ),
                enabled=(
                    _parse_json_bool(enabled, "Browser-user enabled")
                    if enabled is not None
                    else existing.enabled
                ),
            )
            previous = tuple(current)
            current[index] = updated
            snapshot = BrowserUserSnapshot.from_records(current)
            validate_required_invariants(
                snapshot.records,
                require_enabled_admin=_admin_required_after_mutation(
                    previous,
                    require_enabled_admin,
                ),
            )
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=False,
                backup=backup,
            )
            return BrowserUserMutationResult(
                snapshot=snapshot,
                record=updated.public(),
                backup_path=backup_path,
            )

    def delete_user(
        self,
        username: str,
        *,
        backup: bool = True,
        require_enabled_admin: Optional[bool] = None,
    ) -> BrowserUserMutationResult:
        with self.mutation_lock:
            normalized_username = normalize_username(username)
            current = list(self._load_records_unlocked())
            index = self._find_index(current, normalized_username)
            previous = tuple(current)
            removed = current.pop(index)
            snapshot = BrowserUserSnapshot.from_records(current)
            validate_required_invariants(
                snapshot.records,
                require_enabled_admin=_admin_required_after_mutation(
                    previous,
                    require_enabled_admin,
                ),
            )
            backup_path = self._commit_unlocked(
                snapshot.records,
                create_if_missing=False,
                backup=backup,
            )
            return BrowserUserMutationResult(
                snapshot=snapshot,
                record=removed.public(),
                backup_path=backup_path,
            )

    @staticmethod
    def _find_index(records: list[BrowserUserRecord], username: str) -> int:
        for index, record in enumerate(records):
            if record.username == username:
                return index
        raise BrowserUserNotFoundError(f"Browser-session user not found: {username}")

    def _load_records_unlocked(
        self,
        *,
        allow_missing: bool = False,
    ) -> tuple[BrowserUserRecord, ...]:
        try:
            payload = _load_user_json(self.path)
        except FileNotFoundError:
            if allow_missing:
                return ()
            raise BrowserUserPersistenceError(
                f"API session user file does not exist: {self.path}"
            ) from None

        raw_records = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(raw_records, list):
            raise BrowserUserValidationError(
                "API session user file must contain a users list"
            )
        records = tuple(
            _parse_user_record(item, index)
            for index, item in enumerate(raw_records)
        )
        return validate_user_records(records)

    def _commit_unlocked(
        self,
        records: tuple[BrowserUserRecord, ...],
        *,
        create_if_missing: bool,
        backup: bool,
    ) -> Optional[Path]:
        existing_bytes: Optional[bytes] = None
        try:
            existing_bytes = _read_user_file_bytes(self.path)
        except FileNotFoundError:
            if not create_if_missing:
                raise BrowserUserPersistenceError(
                    f"API session user file does not exist: {self.path}"
                ) from None

        parent = self.path.parent
        _ensure_safe_parent(parent)
        backup_path: Optional[Path] = None
        if existing_bytes is not None and backup:
            backup_path = _next_backup_path(self.path)
            _atomic_replace_bytes(
                backup_path,
                existing_bytes,
                require_missing=True,
            )

        serialized = _serialize_records(records)
        # Retain a completed backup on every write failure. In particular,
        # directory fsync can fail after os.replace() has already changed the
        # live credential file, making the commit outcome ambiguous.
        _atomic_replace_bytes(self.path, serialized)
        return backup_path


def load_user_records(path: Path) -> tuple[BrowserUserRecord, ...]:
    """Compatibility loader backed by the canonical browser-user store."""
    return BrowserUserStore(path).load_snapshot().records


def _load_user_json(path: Path) -> Any:
    try:
        raw = _read_user_file_bytes(path)
        return json.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        raise
    except UnicodeDecodeError as exc:
        raise BrowserUserPersistenceError(
            f"API session user file could not be read safely: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise BrowserUserValidationError(
            f"Invalid API session user file JSON: {path}"
        ) from exc


def _read_user_file_bytes(path: Path) -> bytes:
    descriptor: Optional[int] = None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if no_follow:
        flags |= no_follow
    else:
        try:
            if path.is_symlink():
                raise BrowserUserPersistenceError(
                    f"API session user file must not be a symbolic link: {path}"
                )
        except OSError as exc:
            raise BrowserUserPersistenceError(
                f"API session user file could not be inspected safely: {path}"
            ) from exc

    try:
        descriptor = os.open(path, flags)
        file_status = os.fstat(descriptor)
        _validate_open_file_status(file_status, path)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(MAX_AUTH_RECORD_FILE_BYTES + 1)
        if len(raw) > MAX_AUTH_RECORD_FILE_BYTES:
            raise BrowserUserPersistenceError(
                f"API session user file exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit: {path}"
            )
        return raw
    except FileNotFoundError:
        raise
    except BrowserUserStoreError:
        raise
    except OSError as exc:
        raise BrowserUserPersistenceError(
            f"API session user file could not be read safely: {path}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_open_file_status(file_status: os.stat_result, path: Path) -> None:
    if not stat.S_ISREG(file_status.st_mode):
        raise BrowserUserPersistenceError(
            f"API session user file must be a regular file: {path}"
        )
    if file_status.st_nlink != 1:
        raise BrowserUserPersistenceError(
            f"API session user file must not have multiple hard links: {path}"
        )
    if os.name == "posix":
        if file_status.st_uid != os.geteuid():
            raise BrowserUserPersistenceError(
                f"API session user file must be owned by the PixEagle process user: {path}"
            )
        permissions = stat.S_IMODE(file_status.st_mode)
        if not permissions & stat.S_IRUSR or permissions & 0o077:
            raise BrowserUserPersistenceError(
                "API session user file must be owner-readable and inaccessible "
                f"to group/other users: {path}"
            )
    if file_status.st_size > MAX_AUTH_RECORD_FILE_BYTES:
        raise BrowserUserPersistenceError(
            f"API session user file exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit: {path}"
        )


def _ensure_safe_parent(parent: Path) -> None:
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_status = os.lstat(parent)
    except OSError as exc:
        raise BrowserUserPersistenceError(
            f"API session user directory could not be prepared safely: {parent}"
        ) from exc
    if stat.S_ISLNK(parent_status.st_mode) or not stat.S_ISDIR(parent_status.st_mode):
        raise BrowserUserPersistenceError(
            f"API session user parent must be a real directory: {parent}"
        )
    if os.name == "posix":
        if parent_status.st_uid != os.geteuid():
            raise BrowserUserPersistenceError(
                "API session user directory must be owned by the PixEagle "
                f"process user: {parent}"
            )
        if stat.S_IMODE(parent_status.st_mode) & 0o022:
            raise BrowserUserPersistenceError(
                "API session user directory must not be writable by group or "
                f"other users: {parent}"
            )


def _atomic_replace_bytes(
    path: Path,
    payload: bytes,
    *,
    require_missing: bool = False,
) -> None:
    parent = path.parent
    _ensure_safe_parent(parent)
    if require_missing:
        try:
            os.lstat(path)
        except FileNotFoundError:
            pass
        else:
            raise BrowserUserPersistenceError(
                f"Refusing to replace existing browser-user backup: {path}"
            )

    temp_path: Optional[Path] = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temp_path = Path(temp_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
        _fsync_directory(parent)
        if os.name == "posix" and stat.S_IMODE(os.lstat(path).st_mode) != 0o600:
            raise BrowserUserPersistenceError(
                f"Committed browser-user file is not owner-only 0600: {path}"
            )
    except BrowserUserStoreError:
        raise
    except OSError as exc:
        raise BrowserUserPersistenceError(
            f"Failed to atomically write browser-user file: {path}"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _next_backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = path.with_name(f"{path.name}.backup.{stamp}")
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = path.with_name(f"{path.name}.backup.{stamp}.{suffix}")
    return candidate


def _serialize_records(records: Iterable[BrowserUserRecord]) -> bytes:
    checked = validate_user_records(records)
    payload = {"users": [_record_to_payload(record) for record in checked]}
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > MAX_AUTH_RECORD_FILE_BYTES:
        raise BrowserUserValidationError(
            f"API session user payload exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit"
        )
    return raw


def _record_to_payload(record: BrowserUserRecord) -> dict[str, Any]:
    return {
        "username": record.username,
        "role": record.role,
        "password_pbkdf2_sha256": record.password_pbkdf2_sha256,
        "enabled": record.enabled,
    }


def _parse_user_record(raw: Any, index: int) -> BrowserUserRecord:
    if not isinstance(raw, dict):
        raise BrowserUserValidationError(f"User record {index} must be an object")
    if "password" in raw or "plaintext_password" in raw:
        raise BrowserUserValidationError(
            f"User record {index} must not contain plaintext password fields"
        )
    username = normalize_username(raw.get("username"))
    role = normalize_role(raw.get("role", "operator"))
    password_hash = str(raw.get("password_pbkdf2_sha256") or "").strip()
    enabled = _parse_json_bool(
        raw.get("enabled", True),
        f"User record {username!r} enabled",
    )
    if not _is_valid_pbkdf2_sha256_hash(password_hash):
        raise BrowserUserValidationError(
            f"User record {username!r} has invalid password_pbkdf2_sha256"
        )
    return BrowserUserRecord(
        username=username,
        role=role,
        password_pbkdf2_sha256=password_hash,
        enabled=enabled,
    )


def _is_valid_pbkdf2_sha256_hash(encoded: str) -> bool:
    try:
        _parse_pbkdf2_sha256_hash(encoded)
    except BrowserUserStoreError:
        return False
    return True


def _parse_pbkdf2_sha256_hash(encoded: str) -> tuple[int, bytes, bytes]:
    try:
        scheme, iterations_text, salt_text, digest_text = str(encoded or "").split(
            "$", 3
        )
    except ValueError as exc:
        raise BrowserUserValidationError(
            "Invalid PBKDF2-SHA256 hash format"
        ) from exc
    if scheme != PBKDF2_SHA256_SCHEME:
        raise BrowserUserValidationError("Unsupported password hash scheme")
    iterations = _normalize_bounded_int(
        iterations_text,
        "password iterations",
        minimum=MIN_PBKDF2_ITERATIONS,
        maximum=MAX_PBKDF2_ITERATIONS,
    )
    try:
        salt = base64.b64decode(salt_text.encode("ascii"), validate=True)
        digest = base64.b64decode(digest_text.encode("ascii"), validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise BrowserUserValidationError(
            "Invalid PBKDF2-SHA256 hash encoding"
        ) from exc
    _validate_password_salt(salt)
    if len(digest) != PASSWORD_DIGEST_BYTES:
        raise BrowserUserValidationError(
            f"PBKDF2-SHA256 digest must be {PASSWORD_DIGEST_BYTES} bytes"
        )
    return iterations, salt, digest


def _validate_password_salt(salt: bytes) -> None:
    if not isinstance(salt, bytes):
        raise BrowserUserValidationError("Password salt must be bytes")
    if len(salt) < MIN_PASSWORD_SALT_BYTES or len(salt) > MAX_PASSWORD_SALT_BYTES:
        raise BrowserUserValidationError(
            "Password salt must be between "
            f"{MIN_PASSWORD_SALT_BYTES} and {MAX_PASSWORD_SALT_BYTES} bytes"
        )


def _normalize_bounded_int(
    value: Any,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserUserValidationError(f"{name} must be an integer") from exc
    if normalized < minimum or normalized > maximum:
        raise BrowserUserValidationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return normalized


def _parse_json_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise BrowserUserValidationError(f"{name} must be a JSON boolean")


__all__ = [
    "BrowserUserConflictError",
    "BrowserUserInvariantError",
    "BrowserUserMutationResult",
    "BrowserUserNotFoundError",
    "BrowserUserPersistenceError",
    "BrowserUserPublicRecord",
    "BrowserUserRecord",
    "BrowserUserSnapshot",
    "BrowserUserStore",
    "BrowserUserStoreError",
    "BrowserUserValidationError",
    "DEFAULT_PBKDF2_ITERATIONS",
    "MAX_AUTH_RECORD_FILE_BYTES",
    "MAX_BROWSER_PASSWORD_CHARS",
    "MAX_BROWSER_USERNAME_CHARS",
    "MAX_PASSWORD_SALT_BYTES",
    "MAX_PBKDF2_ITERATIONS",
    "MIN_PASSWORD_SALT_BYTES",
    "MIN_PBKDF2_ITERATIONS",
    "PASSWORD_DIGEST_BYTES",
    "PBKDF2_SHA256_SCHEME",
    "hash_password_pbkdf2_sha256",
    "load_user_records",
    "make_browser_user_record",
    "make_user_record",
    "normalize_plaintext_password",
    "normalize_role",
    "normalize_username",
    "validate_required_invariants",
    "validate_user_records",
    "verify_password_pbkdf2_sha256",
]
