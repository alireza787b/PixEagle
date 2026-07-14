"""
Configuration Service - Schema-Driven Config Management
=========================================================

Provides centralized configuration management with:
- YAML persistence with backup and comment preservation
- Schema-based validation
- Diff comparison and structural validation
- Import/export functionality

Project: PixEagle
Author: Alireza Ghaderi
"""

import os
import json
import hashlib
import math
import re
import shutil
import logging
import threading
import tempfile
import copy
import csv
import subprocess
import time
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Iterator
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from urllib.parse import parse_qsl, unquote_plus, urlsplit

# Native advisory file locking on POSIX and Windows.
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# Use ruamel.yaml for round-trip YAML (comment preservation)
from ruamel.yaml import YAML

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation result status."""
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Result of parameter validation."""
    valid: bool
    status: ValidationStatus
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict:
        return {
            'valid': self.valid,
            'status': self.status.value,
            'errors': self.errors,
            'warnings': self.warnings
        }


@dataclass
class DiffEntry:
    """A single difference between two configs."""
    path: str
    section: str
    parameter: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'removed', 'changed'

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ConfigBackup:
    """Metadata for a config backup."""
    id: str
    filename: str
    timestamp: float
    size: int

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AuditEntry:
    """Audit log entry for config changes."""
    timestamp: str
    action: str  # 'update', 'import', 'restore', 'revert'
    section: str
    parameter: Optional[str]
    old_value: Any
    new_value: Any
    source: str  # 'api', 'import', 'restore'

    def to_dict(self) -> Dict:
        return asdict(self)


class PersistenceConflictError(RuntimeError):
    """A persisted file no longer matches an optimistic write precondition."""


class ConfigService:
    """
    Singleton service for schema-driven configuration management.

    Provides:
    - Schema loading and parameter metadata
    - Config CRUD operations with validation
    - Backup and restore
    - Diff comparison between configs
    - Import/export functionality
    """

    _instance = None
    _lock = threading.Lock()

    # Paths relative to project root
    SCHEMA_PATH = "configs/config_schema.yaml"
    CONFIG_PATH = "configs/config.yaml"
    DEFAULT_PATH = "configs/config_default.yaml"
    BACKUP_DIR = "configs/backups"
    AUDIT_LOG_PATH = "configs/audit_log.json"
    SYNC_META_PATH = "configs/config_sync_meta.json"
    RETIREMENTS_PATH = "configs/config_retirements.yaml"
    MAX_BACKUPS = 20
    MAX_AUDIT_ENTRIES = 1000
    SUPPORTED_RETIREMENT_REGISTRY_VERSION = 1
    LOCK_TIMEOUT_SECONDS = 10.0
    MISSING_FILE_DIGEST = hashlib.sha256(
        b"PIXEAGLE_FILE_MISSING\0"
    ).hexdigest()
    _BACKUP_ID_RE = re.compile(
        r"(?:config_\d{8}_\d{6}|config_\d{8}_\d{6}_\d{6}_[A-Za-z0-9_-]+)"
    )

    _SENSITIVE_PARAMETER_RE = re.compile(
        r"(?i)(password|passwd|secret|token|credential|api[_-]?key|"
        r"private[_-]?key|signing[_-]?key|csrf|cookie|authorization)"
    )
    _SENSITIVE_QUERY_KEY_RE = re.compile(
        r"(?i)(?:^|[_-])(?:password|passwd|secret|token|credential|auth|"
        r"authorization|api[_-]?key|private[_-]?key|signing[_-]?key|sig|"
        r"signature|key(?:[_-]?pair[_-]?id)?|policy)(?:$|[_-])"
    )
    _URL_USERINFO_RE = re.compile(
        r"(?i)(?:(?:[a-z][a-z0-9+.-]*:)?//[^\s/?#@]+@|"
        r"^[^\s/?#@:]+:[^\s/?#@]+@)"
    )
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize config state; runtime callers should use get_instance()."""
        self._mutation_lock = threading.RLock()
        self._schema: Dict = {}
        self._config: Dict = {}
        self._config_raw = None  # Raw ruamel.yaml object for round-trip
        self._default: Dict = {}
        self._audit_log: List[Dict] = []
        self._project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).parent.parent.parent
        )
        self._load_all()
        self._load_audit_log(strict=True)

    @classmethod
    def get_instance(cls) -> 'ConfigService':
        """Get singleton instance of ConfigService."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_path(self, relative_path: str) -> Path:
        """Get absolute path from relative path."""
        return self._project_root / relative_path

    @staticmethod
    def _windows_current_user_sid() -> str:
        """Resolve the current Windows SID without localized account names."""
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
        )
        rows = list(csv.reader(result.stdout.splitlines()))
        if len(rows) != 1 or len(rows[0]) < 2 or not rows[0][-1].startswith("S-"):
            raise RuntimeError("Could not resolve the current Windows user SID")
        return rows[0][-1]

    @classmethod
    def _restrict_path_permissions(cls, path: Path, *, directory: bool = False) -> None:
        """Restrict config state to the owner plus Windows recovery principals."""
        if os.name != "nt":
            os.chmod(path, 0o700 if directory else 0o600)
            return

        inheritance = "(OI)(CI)F" if directory else "F"
        current_sid = cls._windows_current_user_sid()
        result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"*{current_sid}:{inheritance}",
                "*S-1-5-18:F",
                "*S-1-5-32-544:F",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "icacls failed").strip()
            raise PermissionError(f"Could not restrict Windows ACL for {path}: {detail}")

    @staticmethod
    def _file_digest(path: Path) -> str:
        """Hash exact persisted bytes, including an explicit missing marker."""
        digest = hashlib.sha256()
        if path.is_symlink():
            raise ValueError(f"Expected a regular non-symlink file: {path}")
        if not path.exists():
            return ConfigService.MISSING_FILE_DIGEST
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Expected a regular non-symlink file: {path}")
        with open(path, "rb") as source_file:
            for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def get_source_state_digests(self) -> Dict[str, str]:
        """Return exact disk fingerprints used by config migration plans."""
        return {
            "runtime_config": self._file_digest(self._get_path(self.CONFIG_PATH)),
            "defaults": self._file_digest(self._get_path(self.DEFAULT_PATH)),
            "schema": self._file_digest(self._get_path(self.SCHEMA_PATH)),
            "retirements": self._file_digest(self._get_path(self.RETIREMENTS_PATH)),
            "sync_meta": self._file_digest(self._get_path(self.SYNC_META_PATH)),
            "audit_log": self._file_digest(self._get_path(self.AUDIT_LOG_PATH)),
        }

    def get_persistence_state_digests(self) -> Dict[str, Any]:
        """Return rollback-relevant file and managed-backup fingerprints."""
        source = self.get_source_state_digests()
        return {
            "runtime_config": source["runtime_config"],
            "sync_meta": source["sync_meta"],
            "audit_log": source["audit_log"],
            "backups": {
                backup_file.name: self._file_digest(backup_file)
                for backup_file in self._get_managed_backup_files()
            },
        }

    @contextmanager
    def mutation_guard(self, timeout: Optional[float] = None) -> Iterator[None]:
        """Serialize cooperating config writers across threads and processes."""
        timeout = self.LOCK_TIMEOUT_SECONDS if timeout is None else float(timeout)
        if timeout <= 0:
            raise ValueError("Config mutation lock timeout must be positive")
        if not self._mutation_lock.acquire(timeout=timeout):
            raise TimeoutError("Could not acquire in-process config mutation lock")

        lock_file = None
        windows_locked = False
        try:
            lock_path = self._get_path(self.CONFIG_PATH).with_suffix(".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            if lock_path.is_symlink():
                raise ValueError("Config mutation lock must be a regular non-symlink file")
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            lock_fd = os.open(lock_path, flags, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise ValueError("Config mutation lock must be a regular file")
                if lock_path.is_symlink():
                    raise ValueError(
                        "Config mutation lock must be a regular non-symlink file"
                    )
                if os.name != "nt":
                    os.fchmod(lock_fd, 0o600)
                lock_file = os.fdopen(lock_fd, "r+b", buffering=0)
                lock_fd = -1
            finally:
                if lock_fd >= 0:
                    os.close(lock_fd)
            if os.name == "nt" and os.fstat(lock_file.fileno()).st_size == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            if os.name == "nt":
                self._restrict_path_permissions(lock_path)

            deadline = time.monotonic() + timeout
            while True:
                try:
                    if HAS_FCNTL:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    elif os.name == "nt":
                        import msvcrt

                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        windows_locked = True
                    break
                except (BlockingIOError, OSError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Could not acquire config file lock")
                    time.sleep(0.1)
            yield
        finally:
            if lock_file is not None:
                try:
                    if HAS_FCNTL:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    elif os.name == "nt" and windows_locked:
                        import msvcrt

                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    lock_file.close()
            self._mutation_lock.release()

    def capture_persistence_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Capture exact config/meta and managed-backup bytes for rollback."""
        snapshot: Dict[str, Dict[str, Any]] = {}
        for name, relative_path in (
            ("runtime_config", self.CONFIG_PATH),
            ("sync_meta", self.SYNC_META_PATH),
            ("audit_log", self.AUDIT_LOG_PATH),
        ):
            path = self._get_path(relative_path)
            if path.is_symlink():
                raise ValueError(
                    f"Persisted config state must be a regular non-symlink file: {path}"
                )
            exists = path.exists()
            if exists:
                if not path.is_file() or path.is_symlink():
                    raise ValueError(
                        f"Persisted config state must be a regular non-symlink file: {path}"
                    )
                self._restrict_path_permissions(path)
            snapshot[name] = {
                "path": path,
                "exists": exists,
                "bytes": path.read_bytes() if exists else None,
            }
        backup_dir = self._get_path(self.BACKUP_DIR)
        snapshot["backups"] = {
            "path": backup_dir,
            "exists": backup_dir.is_dir() and not backup_dir.is_symlink(),
            "files": {
                backup_file.name: backup_file.read_bytes()
                for backup_file in self._get_managed_backup_files()
            },
        }
        return snapshot

    def restore_persistence_snapshot(
        self,
        snapshot: Dict[str, Dict[str, Any]],
        *,
        lock_acquired: bool = False,
        expected_current_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Restore only transaction-owned state after a failed mutation.

        When ``expected_current_state`` is supplied, an artifact is restored
        only when the caller marked it as owned and its current digest still
        matches the caller's post-write digest. This prevents rollback from
        overwriting a non-cooperating operator edit that CAS detected or that
        arrived after a transaction write.
        """
        if not lock_acquired:
            with self.mutation_guard():
                self.restore_persistence_snapshot(
                    snapshot,
                    lock_acquired=True,
                    expected_current_state=expected_current_state,
                )
            return

        conflicts: List[str] = []
        for name, item in snapshot.items():
            if name == "backups":
                continue
            path = item["path"]
            expected_digest = None
            if expected_current_state is not None:
                if name not in expected_current_state:
                    continue
                expected_digest = expected_current_state[name]
            try:
                if item["exists"]:
                    self._write_bytes_atomic(
                        path,
                        item["bytes"],
                        mode=0o600,
                        expected_digest=expected_digest,
                    )
                else:
                    self._unlink_file_if_digest(path, expected_digest)
            except PersistenceConflictError:
                conflicts.append(name)

        backups = snapshot.get("backups")
        restore_backups = backups is not None
        if expected_current_state is not None:
            restore_backups = restore_backups and "backups" in expected_current_state
            if restore_backups:
                current_backups = {
                    backup_file.name: self._file_digest(backup_file)
                    for backup_file in self._get_managed_backup_files()
                }
                if current_backups != expected_current_state["backups"]:
                    conflicts.append("backups")
                    restore_backups = False

        if restore_backups and backups is not None:
            backup_dir = backups["path"]
            original_files = backups["files"]
            expected_backups = (
                expected_current_state.get("backups", {})
                if expected_current_state is not None
                else {
                    backup_file.name: self._file_digest(backup_file)
                    for backup_file in self._get_managed_backup_files()
                }
            )
            try:
                for backup_file in self._get_managed_backup_files():
                    if backup_file.name not in original_files:
                        self._unlink_file_if_digest(
                            backup_file,
                            expected_backups.get(
                                backup_file.name,
                                self.MISSING_FILE_DIGEST,
                            ),
                        )
                for filename, payload in original_files.items():
                    self._write_bytes_atomic(
                        backup_dir / filename,
                        payload,
                        mode=0o600,
                        expected_digest=expected_backups.get(
                            filename,
                            self.MISSING_FILE_DIGEST,
                        ),
                    )
            except PersistenceConflictError:
                conflicts.append("backups")
            if backup_dir.exists():
                self._fsync_directory(backup_dir)
            if not backups["exists"] and backup_dir.is_dir():
                try:
                    backup_dir.rmdir()
                except OSError:
                    # Preserve operator-owned/unmanaged files rather than deleting them.
                    pass
            restored_backups = {
                backup_file.name: self._file_digest(backup_file)
                for backup_file in self._get_managed_backup_files()
            }
            expected_original = {
                filename: hashlib.sha256(payload).hexdigest()
                for filename, payload in original_files.items()
            }
            if restored_backups != expected_original:
                conflicts.append("backups")

        if conflicts:
            raise RuntimeError(
                "Rollback preserved externally changed persistence state: "
                + ", ".join(sorted(conflicts))
            )

    def _load_all(self):
        """Load schema, current config, and defaults as one fail-closed state."""
        yaml = YAML()
        yaml.preserve_quotes = True

        schema_path = self._get_path(self.SCHEMA_PATH)
        default_path = self._get_path(self.DEFAULT_PATH)
        config_path = self._get_path(self.CONFIG_PATH)

        if schema_path.is_symlink() or not schema_path.is_file():
            raise FileNotFoundError(f"Config schema file not found: {schema_path}")
        if default_path.is_symlink() or not default_path.is_file():
            raise FileNotFoundError(f"Default config file not found: {default_path}")

        try:
            with open(schema_path, 'r', encoding='utf-8') as schema_file:
                loaded_schema = yaml.load(schema_file)
            with open(default_path, 'r', encoding='utf-8') as default_file:
                loaded_default = yaml.load(default_file)
            if not isinstance(loaded_schema, dict):
                raise ValueError("Config schema root must be a mapping")
            if not isinstance(loaded_default, dict):
                raise ValueError("Default config root must be a mapping")

            if config_path.is_symlink():
                raise ValueError("Runtime config must be a regular non-symlink file")
            if config_path.exists():
                if not config_path.is_file() or config_path.is_symlink():
                    raise ValueError("Runtime config must be a regular non-symlink file")
                self._restrict_path_permissions(config_path)
                with open(config_path, 'r', encoding='utf-8') as config_file:
                    loaded_config = yaml.load(config_file)
                if not isinstance(loaded_config, dict):
                    raise ValueError("Runtime config root must be a mapping")
                next_config = dict(loaded_config)
                next_config_raw = loaded_config
            else:
                next_config = copy.deepcopy(dict(loaded_default))
                next_config_raw = None
        except Exception as exc:
            logger.error("Config load rejected; previous in-memory state preserved: %s", exc)
            raise RuntimeError(f"Could not load configuration safely: {exc}") from exc

        self._schema = dict(loaded_schema)
        self._default = dict(loaded_default)
        self._config = next_config
        self._config_raw = next_config_raw
        logger.info("Loaded config schema and defaults from checked-in sources")
        if config_path.exists():
            logger.info("Loaded runtime config from %s", config_path)
        else:
            logger.warning(
                "Config file not found: %s; using defaults from %s",
                config_path,
                default_path,
            )

    def reload(self):
        """Reload all config files from disk."""
        with self._mutation_lock:
            self._load_all()

    # =========================================================================
    # Audit Log Methods
    # =========================================================================

    def _load_audit_log(
        self,
        *,
        strict: bool = False,
        lock_acquired: bool = False,
    ):
        """Load audit state, optionally rejecting corruption fail-closed."""
        try:
            audit_path = self._get_path(self.AUDIT_LOG_PATH)
            if audit_path.is_symlink():
                raise ValueError(
                    "Config audit log must be a regular non-symlink file"
                )
            if audit_path.exists():
                if not audit_path.is_file() or audit_path.is_symlink():
                    raise ValueError(
                        "Config audit log must be a regular non-symlink file"
                    )
                self._restrict_path_permissions(audit_path)
                with open(audit_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError("Config audit log root must be a list")
                sanitized_entries = []
                for index, entry in enumerate(loaded):
                    if not isinstance(entry, dict):
                        raise ValueError(
                            f"Config audit log entry #{index} must be an object"
                        )
                    sanitized = copy.deepcopy(entry)
                    section = str(sanitized.get("section", ""))
                    parameter = sanitized.get("parameter")
                    if parameter is not None:
                        parameter = str(parameter)
                    sanitized["old_value"] = self._sanitize_audit_value(
                        section,
                        parameter,
                        sanitized.get("old_value"),
                    )
                    sanitized["new_value"] = self._sanitize_audit_value(
                        section,
                        parameter,
                        sanitized.get("new_value"),
                    )
                    sanitized_entries.append(sanitized)
                self._audit_log = sanitized_entries
                if sanitized_entries != loaded and not self._save_audit_log(
                    lock_acquired=lock_acquired,
                ):
                    raise RuntimeError("Could not scrub sensitive config audit values")
                logger.info(f"Loaded {len(self._audit_log)} audit entries")
            else:
                self._audit_log = []
        except Exception as e:
            logger.error(f"Error loading audit log: {e}")
            if strict:
                raise RuntimeError(f"Could not load config audit log safely: {e}") from e
            self._audit_log = []

    def reload_audit_log(
        self,
        *,
        strict: bool = False,
        lock_acquired: bool = False,
    ) -> None:
        """Refresh durable config-audit state from disk."""
        with self._mutation_lock:
            self._load_audit_log(strict=strict, lock_acquired=lock_acquired)

    def _save_audit_log(
        self,
        *,
        lock_acquired: bool = False,
        expected_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Save the redacted audit log atomically with restricted permissions."""
        if not lock_acquired:
            with self.mutation_guard():
                return self._save_audit_log(
                    lock_acquired=True,
                    expected_digest=expected_digest,
                    write_receipt=write_receipt,
                )
        try:
            audit_path = self._get_path(self.AUDIT_LOG_PATH)
            entries_to_save = self._audit_log[-self.MAX_AUDIT_ENTRIES:]
            payload = json.dumps(
                entries_to_save,
                indent=2,
                default=str,
                ensure_ascii=True,
            ).encode("utf-8")
            self._write_bytes_atomic(
                audit_path,
                payload,
                mode=0o600,
                expected_digest=expected_digest,
                write_receipt=write_receipt,
                receipt_key="audit_log",
            )
            self._audit_log = entries_to_save
            return True
        except Exception as e:
            logger.error(f"Error saving audit log: {e}")
            return False

    def _is_sensitive_parameter(self, section: str, parameter: Optional[str]) -> bool:
        """Classify secret-bearing config paths conservatively."""
        candidate = ".".join(part for part in (section, parameter) if part)
        schema = (
            self.get_parameter_schema(section, parameter)
            if parameter is not None
            else self.get_schema(section)
        )
        return bool(
            isinstance(schema, dict) and schema.get("sensitive") is True
        ) or bool(self._SENSITIVE_PARAMETER_RE.search(candidate))

    def _schema_for_path(self, path: List[str] | Tuple[str, ...]) -> Dict[str, Any]:
        """Resolve schema metadata for a root, parameter, or declared object child."""
        parts = list(path)
        if not parts:
            return {}
        schema: Any = self._schema.get("sections", {}).get(parts[0], {})
        if len(parts) >= 2:
            schema = (
                schema.get("parameters", {}).get(parts[1], {})
                if isinstance(schema, dict)
                else {}
            )
        for part in parts[2:]:
            schema = (
                schema.get("properties", {}).get(part, {})
                if isinstance(schema, dict)
                else {}
            )
        return schema if isinstance(schema, dict) else {}

    @classmethod
    def _string_contains_credentials(cls, value: str) -> bool:
        """Detect credentials embedded in otherwise non-sensitive URL settings."""
        if cls._URL_USERINFO_RE.search(value):
            return True
        raw_query = value.partition("?")[2].partition("#")[0]
        raw_fragment = value.partition("#")[2]
        for raw_component in (raw_query, raw_fragment):
            for assignment in raw_component.split("&") if raw_component else ():
                raw_key = assignment.partition("=")[0]
                try:
                    query_key = unquote_plus(raw_key)
                except (UnicodeError, ValueError):
                    return True
                if cls._SENSITIVE_QUERY_KEY_RE.search(query_key):
                    return True
        try:
            parsed = urlsplit(value)
        except ValueError:
            # Malformed authority syntax is common in partially entered URLs.
            # The conservative raw checks above are the only safe fallback.
            return False
        if parsed.netloc and (
            parsed.username is not None or parsed.password is not None
        ):
            return True
        if not parsed.query:
            return False
        try:
            query_keys = [key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
        except ValueError:
            return True
        return any(cls._SENSITIVE_QUERY_KEY_RE.search(key) for key in query_keys)

    def _sanitize_audit_value(
        self,
        section: str,
        parameter: Optional[str],
        value: Any,
    ) -> Any:
        path = [section] if parameter is None else [section, parameter]
        return self.redact_value(value, path)

    def is_sensitive_path(self, path: List[str] | Tuple[str, ...]) -> bool:
        """Return whether a config path must be redacted from logs/responses."""
        parts = list(path)
        if not parts or not all(isinstance(part, str) and part for part in parts):
            return True
        with self._mutation_lock:
            schema = self._schema_for_path(parts)
            return bool(schema.get("sensitive") is True) or bool(
                self._SENSITIVE_PARAMETER_RE.search(".".join(parts))
            )

    def redact_value(
        self,
        value: Any,
        path: List[str] | Tuple[str, ...] = (),
    ) -> Any:
        """Return a recursive response-safe copy for one config path."""
        with self._mutation_lock:
            return self._redact_value_locked(value, path)

    def _redact_value_locked(
        self,
        value: Any,
        path: List[str] | Tuple[str, ...] = (),
    ) -> Any:
        """Redact recursively while the schema generation is stable."""
        normalized_path = list(path)
        if normalized_path and self.is_sensitive_path(normalized_path):
            return "[REDACTED]"
        if isinstance(value, str) and self._string_contains_credentials(value):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                key: self._redact_value_locked(item, [*normalized_path, str(key)])
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._redact_value_locked(item, normalized_path)
                for item in value
            ]
        return copy.deepcopy(value)

    def redact_diff_entry(self, diff: DiffEntry) -> Dict[str, Any]:
        """Serialize one diff without exposing secret-bearing values."""
        payload = diff.to_dict()
        path = [diff.section, diff.parameter]
        payload["old_value"] = self.redact_value(diff.old_value, path)
        payload["new_value"] = self.redact_value(diff.new_value, path)
        return payload

    def log_audit_entry(
        self,
        action: str,
        section: str,
        parameter: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        source: str = 'api',
        *,
        lock_acquired: bool = False,
        expected_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
    ):
        """Log a config change to the audit log."""
        if not lock_acquired:
            with self.mutation_guard():
                self.log_audit_entry(
                    action,
                    section,
                    parameter,
                    old_value,
                    new_value,
                    source,
                    lock_acquired=True,
                    expected_digest=expected_digest,
                    write_receipt=write_receipt,
                )
            return

        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            section=section,
            parameter=parameter,
            old_value=self._sanitize_audit_value(section, parameter, old_value),
            new_value=self._sanitize_audit_value(section, parameter, new_value),
            source=source
        )
        self._audit_log.append(entry.to_dict())
        if not self._save_audit_log(
            lock_acquired=True,
            expected_digest=expected_digest,
            write_receipt=write_receipt,
        ):
            self._audit_log.pop()
            raise RuntimeError("Could not persist config audit entry")
        logger.debug(f"Audit: {action} {section}.{parameter}")

    def get_audit_log(
        self,
        limit: int = 100,
        offset: int = 0,
        section: Optional[str] = None,
        action: Optional[str] = None
    ) -> Dict:
        """
        Get audit log entries with optional filtering.

        Args:
            limit: Max entries to return
            offset: Skip first N entries
            section: Filter by section name
            action: Filter by action type

        Returns:
            Dict with 'entries', 'total', 'limit', 'offset'
        """
        with self._mutation_lock:
            entries = copy.deepcopy(self._audit_log)

            # Apply filters
            if section:
                entries = [e for e in entries if e.get('section') == section]
            if action:
                entries = [e for e in entries if e.get('action') == action]

            # Sort by timestamp descending (most recent first)
            entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

            total = len(entries)
            entries = entries[offset:offset + limit]

        return {
            'entries': entries,
            'total': total,
            'limit': limit,
            'offset': offset
        }

    def clear_audit_log(self):
        """Clear all audit log entries."""
        with self.mutation_guard():
            previous = self._audit_log
            self._audit_log = []
            if not self._save_audit_log(lock_acquired=True):
                self._audit_log = previous
                raise RuntimeError("Could not clear config audit log")
        logger.info("Audit log cleared")

    # =========================================================================
    # Schema Methods
    # =========================================================================

    def get_schema(self, section: Optional[str] = None) -> Dict:
        """
        Get schema definition.

        Args:
            section: Optional section name to get only that section's schema

        Returns:
            Full schema or section schema
        """
        with self._mutation_lock:
            if section:
                value = self._schema.get('sections', {}).get(section, {})
            else:
                value = self._schema
            return copy.deepcopy(value)

    def get_categories(self) -> Dict:
        """Get category definitions from schema."""
        with self._mutation_lock:
            return copy.deepcopy(self._schema.get('categories', {}))

    def get_sections(self) -> List[Dict]:
        """Get list of all sections with metadata."""
        with self._mutation_lock:
            sections = []
            for name, data in self._schema.get('sections', {}).items():
                sections.append({
                    'name': name,
                    'display_name': data.get('display_name', name),
                    'category': data.get('category', 'other'),
                    'icon': data.get('icon', 'settings'),
                    'parameter_count': len(data.get('parameters', {}))
                })
            return sections

    def get_parameter_schema(self, section: str, param: str) -> Optional[Dict]:
        """Get schema for a specific parameter."""
        with self._mutation_lock:
            value = (
                self._schema.get('sections', {})
                .get(section, {})
                .get('parameters', {})
                .get(param)
            )
            return copy.deepcopy(value)

    # =========================================================================
    # Config Read Methods
    # =========================================================================

    def get_config(self, section: Optional[str] = None) -> Dict:
        """
        Get current configuration.

        Args:
            section: Optional section name

        Returns:
            Full config or section config
        """
        with self._mutation_lock:
            if section:
                value = self._config.get(section, {})
            else:
                value = self._config
            return copy.deepcopy(value)

    def get_default(self, section: Optional[str] = None) -> Dict:
        """Get default configuration."""
        with self._mutation_lock:
            if section:
                value = self._default.get(section, {})
            else:
                value = self._default
            return copy.deepcopy(value)

    def get_effective_defaults(self) -> Dict[str, Any]:
        """Return checked-in defaults; schema supplies validation metadata only."""
        with self._mutation_lock:
            return copy.deepcopy(self._default)

    def get_default_config(self, section: Optional[str] = None) -> Dict:
        """Backward-compatible alias for default configuration retrieval."""
        return self.get_default(section)

    def get_schema_version(self) -> str:
        """Get schema version string."""
        with self._mutation_lock:
            return str(self._schema.get('schema_version', 'unknown'))

    def get_retirement_registry(self) -> Dict[str, Any]:
        """Load and validate the exact, versioned config retirement registry."""
        with self._mutation_lock:
            return self._get_retirement_registry_locked()

    def _get_retirement_registry_locked(self) -> Dict[str, Any]:
        """Validate retirements against one stable defaults/schema generation."""
        registry_path = self._get_path(self.RETIREMENTS_PATH)
        if registry_path.is_symlink() or not registry_path.is_file():
            raise FileNotFoundError(f"Config retirement registry not found: {registry_path}")

        yaml = YAML(typ="safe")
        with open(registry_path, "r", encoding="utf-8") as registry_file:
            loaded = yaml.load(registry_file) or {}

        if not isinstance(loaded, dict):
            raise ValueError("Config retirement registry root must be a mapping")
        root_keys = {"registry_version", "retirements"}
        actual_root_keys = set(loaded)
        if actual_root_keys != root_keys:
            missing_root_keys = root_keys - actual_root_keys
            unexpected_root_keys = actual_root_keys - root_keys
            details = []
            if missing_root_keys:
                details.append("missing " + ", ".join(sorted(missing_root_keys)))
            if unexpected_root_keys:
                details.append(
                    "unexpected " + ", ".join(sorted(unexpected_root_keys))
                )
            raise ValueError(
                "Invalid config retirement registry keys: " + "; ".join(details)
            )

        registry_version = loaded.get("registry_version")
        if registry_version != self.SUPPORTED_RETIREMENT_REGISTRY_VERSION:
            raise ValueError(
                "Unsupported config retirement registry_version: "
                f"{registry_version}; supported version is "
                f"{self.SUPPORTED_RETIREMENT_REGISTRY_VERSION}"
            )

        retirements = loaded.get("retirements", [])
        if not isinstance(retirements, list):
            raise ValueError("Config retirement retirements must be a list")

        normalized = []
        seen_ids = set()
        seen_paths = set()
        entry_keys = {
            "id",
            "path",
            "action",
            "retired_in_schema_version",
            "reason",
            "replacement",
        }

        schema_version = self.get_schema_version()
        if re.fullmatch(r"\d+\.\d+\.\d+", schema_version) is None:
            raise ValueError(
                "Active config schema_version must use semantic x.y.z format"
            )
        schema_version_tuple = tuple(int(part) for part in schema_version.split("."))

        for index, retirement in enumerate(retirements):
            if not isinstance(retirement, dict):
                raise ValueError(f"Config retirement #{index} must be a mapping")
            actual_entry_keys = set(retirement)
            if actual_entry_keys != entry_keys:
                missing_entry_keys = entry_keys - actual_entry_keys
                unexpected_entry_keys = actual_entry_keys - entry_keys
                details = []
                if missing_entry_keys:
                    details.append("missing " + ", ".join(sorted(missing_entry_keys)))
                if unexpected_entry_keys:
                    details.append(
                        "unexpected " + ", ".join(sorted(unexpected_entry_keys))
                    )
                raise ValueError(
                    f"Invalid keys in config retirement #{index}: " + "; ".join(details)
                )

            retirement_id = retirement.get("id")
            path = retirement.get("path")
            action = retirement.get("action")
            retired_in_schema_version = retirement.get("retired_in_schema_version")
            reason = retirement.get("reason")
            replacement = retirement.get("replacement")

            if not isinstance(retirement_id, str) or not retirement_id.strip():
                raise ValueError(f"Config retirement #{index} has an invalid id")
            if retirement_id in seen_ids:
                raise ValueError(f"Duplicate config retirement id: {retirement_id}")
            if (
                not isinstance(path, list)
                or len(path) not in {1, 2}
                or not all(isinstance(item, str) and item.strip() for item in path)
            ):
                raise ValueError(
                    f"Config retirement {retirement_id} path must contain a root key "
                    "or section and parameter"
                )
            if action != "remove":
                raise ValueError(f"Config retirement {retirement_id} action must be 'remove'")
            if (
                not isinstance(retired_in_schema_version, str)
                or re.fullmatch(r"\d+\.\d+\.\d+", retired_in_schema_version) is None
            ):
                raise ValueError(
                    f"Config retirement {retirement_id} requires a semantic retired_in_schema_version"
                )
            retirement_version_tuple = tuple(
                int(part) for part in retired_in_schema_version.split(".")
            )
            if retirement_version_tuple > schema_version_tuple:
                raise ValueError(
                    f"Config retirement {retirement_id} targets future schema "
                    f"{retired_in_schema_version}"
                )
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"Config retirement {retirement_id} requires a reason")
            if replacement is not None and (
                not isinstance(replacement, list)
                or len(replacement) not in {1, 2}
                or not all(
                    isinstance(part, str) and part.strip() == part and part
                    for part in replacement
                )
            ):
                raise ValueError(
                    f"Config retirement {retirement_id} replacement must be null "
                    "or an active canonical path array"
                )

            path_key = tuple(path)
            if path_key in seen_paths:
                raise ValueError(f"Duplicate config retirement path: {'.'.join(path)}")

            if self._path_is_active(path):
                raise ValueError(
                    f"Registered retirement {'.'.join(path)} is still active in defaults/schema"
                )

            if replacement is not None:
                if not self._path_is_active(replacement):
                    raise ValueError(
                        f"Config retirement {retirement_id} replacement "
                        f"{'.'.join(replacement)} is not active in defaults/schema"
                    )

            seen_ids.add(retirement_id)
            seen_paths.add(path_key)
            normalized.append(
                {
                    "id": retirement_id,
                    "path": list(path),
                    "action": action,
                    "retired_in_schema_version": retired_in_schema_version,
                    "reason": reason,
                    "replacement": (
                        list(replacement) if replacement is not None else None
                    ),
                }
            )

        normalized.sort(key=lambda item: (tuple(item["path"]), item["id"]))
        canonical = {
            "registry_version": registry_version,
            "retirements": normalized,
        }
        registry_digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**canonical, "registry_digest": registry_digest}

    def _path_is_active(self, path: List[str]) -> bool:
        with self._mutation_lock:
            if len(path) == 1:
                root_key = path[0]
                return root_key in self._default or root_key in self._schema.get(
                    "sections", {}
                )
            section, parameter = path
            default_section = self._default.get(section, {})
            schema_section = self._schema.get("sections", {}).get(section, {})
            schema_parameters = (
                schema_section.get("parameters", {})
                if isinstance(schema_section, dict)
                else {}
            )
            return bool(
                isinstance(default_section, dict) and parameter in default_section
            ) or parameter in schema_parameters

    def get_registered_retirement(
        self,
        path: List[str] | Tuple[str, ...] | str,
        parameter: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the exact registered retirement for a config path, if any."""
        if isinstance(path, str):
            normalized_path = [path] if parameter is None else [path, parameter]
        else:
            normalized_path = list(path)
        for retirement in self.get_retirement_registry()["retirements"]:
            if retirement["path"] == normalized_path:
                return retirement
        return None

    def get_path_value(self, path: List[str] | Tuple[str, ...], *, default: Any = None) -> Any:
        """Read a supported root or section/parameter path from runtime config."""
        with self._mutation_lock:
            parts = list(path)
            if len(parts) == 1:
                if parts[0] not in self._config:
                    return default
                value = self._config[parts[0]]
            elif len(parts) == 2:
                section = self._config.get(parts[0], {})
                if not isinstance(section, dict) or parts[1] not in section:
                    return default
                value = section[parts[1]]
            else:
                raise ValueError("Config paths must contain one or two components")
            return copy.deepcopy(value)

    def path_exists(self, path: List[str] | Tuple[str, ...]) -> bool:
        marker = object()
        return self.get_path_value(path, default=marker) is not marker

    def get_parameter(self, section: str, param: str) -> Any:
        """Get a specific parameter value."""
        with self._mutation_lock:
            section_data = self._config.get(section, {})
            value = section_data.get(param) if isinstance(section_data, dict) else None
            return copy.deepcopy(value)

    def get_default_parameter(self, section: str, param: str) -> Any:
        """Get default value for a parameter."""
        with self._mutation_lock:
            section_data = self._default.get(section, {})
            value = section_data.get(param) if isinstance(section_data, dict) else None
            return copy.deepcopy(value)

    # =========================================================================
    # Validation
    # =========================================================================

    def _validate_value_against_schema(
        self,
        path_label: str,
        value: Any,
        param_schema: Optional[Dict[str, Any]],
    ) -> ValidationResult:
        """Validate one value against an already-resolved schema entry."""
        errors = []
        warnings = []

        if not param_schema:
            warnings.append(f"No schema found for {path_label}")
            return ValidationResult(True, ValidationStatus.WARNING, errors, warnings)

        expected_type = param_schema.get('type', 'any')

        # Type validation
        if expected_type == 'integer':
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"Expected integer, got {type(value).__name__}")
            else:
                # Range validation
                if 'min' in param_schema and value < param_schema['min']:
                    errors.append(f"Value {value} is below minimum {param_schema['min']}")
                if 'max' in param_schema and value > param_schema['max']:
                    errors.append(f"Value {value} is above maximum {param_schema['max']}")

        elif expected_type == 'float':
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"Expected float, got {type(value).__name__}")
            else:
                numeric_value = float(value)
                if not math.isfinite(numeric_value):
                    errors.append("Numeric values must be finite")
                else:
                    if 'min' in param_schema and value < param_schema['min']:
                        errors.append(f"Value {value} is below minimum {param_schema['min']}")
                    if 'max' in param_schema and value > param_schema['max']:
                        errors.append(f"Value {value} is above maximum {param_schema['max']}")

        elif expected_type == 'number':
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"Expected number, got {type(value).__name__}")
            elif not math.isfinite(float(value)):
                errors.append("Numeric values must be finite")
            else:
                if 'min' in param_schema and value < param_schema['min']:
                    errors.append(f"Value {value} is below minimum {param_schema['min']}")
                if 'max' in param_schema and value > param_schema['max']:
                    errors.append(f"Value {value} is above maximum {param_schema['max']}")

        elif expected_type == 'boolean':
            if not isinstance(value, bool):
                errors.append(f"Expected boolean, got {type(value).__name__}")

        elif expected_type == 'string':
            if not isinstance(value, str):
                errors.append(f"Expected string, got {type(value).__name__}")

        elif expected_type == 'array':
            if not isinstance(value, list):
                errors.append(f"Expected array, got {type(value).__name__}")
            else:
                min_items = param_schema.get("min_items")
                max_items = param_schema.get("max_items")
                if min_items is not None and len(value) < min_items:
                    errors.append(
                        f"Array has {len(value)} items; minimum is {min_items}"
                    )
                if max_items is not None and len(value) > max_items:
                    errors.append(
                        f"Array has {len(value)} items; maximum is {max_items}"
                    )
                item_type = param_schema.get("item_type")
                if item_type:
                    for index, item in enumerate(value):
                        item_result = self._validate_value_against_schema(
                            f"{path_label}[{index}]",
                            item,
                            {"type": item_type},
                        )
                        errors.extend(item_result.errors)
                        warnings.extend(item_result.warnings)

        elif expected_type == 'object':
            if not isinstance(value, dict):
                errors.append(f"Expected object, got {type(value).__name__}")
            else:
                properties = param_schema.get("properties", {})
                if isinstance(properties, dict):
                    required = param_schema.get("required", [])
                    if isinstance(required, list):
                        missing = sorted(
                            key for key in required
                            if isinstance(key, str) and key not in value
                        )
                        if missing:
                            errors.append(
                                f"Missing required properties: {', '.join(missing)}"
                            )
                    if param_schema.get("additional_properties") is False:
                        unexpected = sorted(set(value) - set(properties))
                        if unexpected:
                            errors.append(
                                "Unexpected properties: " + ", ".join(unexpected)
                            )
                    for key, child_value in value.items():
                        child_schema = properties.get(key)
                        if child_schema is None:
                            continue
                        child_result = self._validate_value_against_schema(
                            f"{path_label}.{key}",
                            child_value,
                            child_schema,
                        )
                        errors.extend(child_result.errors)
                        warnings.extend(child_result.warnings)

        if not errors:
            options = param_schema.get("options", param_schema.get("enum"))
            if isinstance(options, list) and options:
                allowed_values = [
                    option.get("value") if isinstance(option, dict) else option
                    for option in options
                ]
                if value not in allowed_values:
                    errors.append(
                        f"Value {value!r} not in allowed set {allowed_values!r}"
                    )

        # Recommended range warnings (soft limits — do not block save)
        if expected_type in ('integer', 'float', 'number') and not errors:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                rec_min = param_schema.get('recommended_min')
                rec_max = param_schema.get('recommended_max')
                if rec_min is not None and value < rec_min:
                    warnings.append(
                        f"Value {value} is below recommended minimum {rec_min}"
                    )
                if rec_max is not None and value > rec_max:
                    warnings.append(
                        f"Value {value} is above recommended maximum {rec_max}"
                    )

        # Note: "differs from default" is informational provenance, not a warning.
        # The UI can show this via the default_value field in parameter metadata.

        # Check reboot requirement
        if param_schema.get('reboot_required', False):
            warnings.append("Restart required for this change to take effect")

        valid = len(errors) == 0
        status = ValidationStatus.ERROR if errors else (
            ValidationStatus.WARNING if warnings else ValidationStatus.VALID
        )

        return ValidationResult(valid, status, errors, warnings)

    def validate_value(self, section: str, param: str, value: Any) -> ValidationResult:
        """Validate a section/parameter value against its schema."""
        return self._validate_value_against_schema(
            f"{section}.{param}",
            value,
            self.get_parameter_schema(section, param),
        )

    def validate_path(
        self,
        path: List[str] | Tuple[str, ...],
        value: Any,
    ) -> ValidationResult:
        """Validate a root or section/parameter config path."""
        with self._mutation_lock:
            parts = list(path)
            if len(parts) == 2:
                return self.validate_value(parts[0], parts[1], value)
            if len(parts) == 1:
                schema = self._schema.get("sections", {}).get(parts[0])
                return self._validate_value_against_schema(parts[0], value, schema)
            return ValidationResult(
                False,
                ValidationStatus.ERROR,
                ["Config paths must contain one or two components"],
                [],
            )

    def validate_config_mapping(
        self,
        candidate: Dict[str, Any],
        *,
        require_safety: bool = False,
    ) -> ValidationResult:
        """Validate a mapping against one stable defaults/schema generation."""
        with self._mutation_lock:
            return self._validate_config_mapping_locked(
                candidate,
                require_safety=require_safety,
            )

    def _validate_config_mapping_locked(
        self,
        candidate: Dict[str, Any],
        *,
        require_safety: bool = False,
    ) -> ValidationResult:
        """Validate all schema-owned values in a candidate runtime mapping."""
        errors: List[str] = []
        warnings: List[str] = []
        if not isinstance(candidate, dict):
            return ValidationResult(
                False,
                ValidationStatus.ERROR,
                ["Configuration root must be a mapping"],
                [],
            )

        if require_safety:
            safety = candidate.get("Safety")
            global_limits = safety.get("GlobalLimits") if isinstance(safety, dict) else None
            if not isinstance(global_limits, dict):
                errors.append("Safety.GlobalLimits is required")
            else:
                required_limits = self._default.get("Safety", {}).get(
                    "GlobalLimits",
                    {},
                )
                if isinstance(required_limits, dict):
                    missing_limits = sorted(set(required_limits) - set(global_limits))
                    if missing_limits:
                        errors.append(
                            "Safety.GlobalLimits is missing required keys: "
                            + ", ".join(missing_limits)
                        )

        schema_sections = self._schema.get("sections", {})
        for section, section_value in candidate.items():
            section_schema = schema_sections.get(section)
            if not isinstance(section_schema, dict):
                warnings.append(f"No schema found for {section}")
                continue
            parameters = section_schema.get("parameters")
            if isinstance(parameters, dict):
                if not isinstance(section_value, dict):
                    errors.append(
                        f"{section}: expected object, got {type(section_value).__name__}"
                    )
                    continue
                for parameter, value in section_value.items():
                    parameter_schema = parameters.get(parameter)
                    if parameter_schema is None:
                        warnings.append(f"No schema found for {section}.{parameter}")
                        continue
                    result = self._validate_value_against_schema(
                        f"{section}.{parameter}",
                        value,
                        parameter_schema,
                    )
                    errors.extend(result.errors)
                    warnings.extend(result.warnings)
            else:
                result = self._validate_value_against_schema(
                    section,
                    section_value,
                    section_schema,
                )
                errors.extend(result.errors)
                warnings.extend(result.warnings)

        status = (
            ValidationStatus.ERROR
            if errors
            else (ValidationStatus.WARNING if warnings else ValidationStatus.VALID)
        )
        return ValidationResult(not errors, status, errors, warnings)

    # =========================================================================
    # Config Write Methods
    # =========================================================================

    def set_parameter(
        self,
        section: str,
        param: str,
        value: Any,
        validate: bool = True,
        *,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """Apply one in-memory parameter update without exposing partial state."""
        with self._mutation_lock:
            return self._set_parameter_locked(
                section,
                param,
                value,
                validate,
                audit=audit,
                source=source,
            )

    def _set_parameter_locked(
        self,
        section: str,
        param: str,
        value: Any,
        validate: bool = True,
        *,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """
        Set a parameter value (in memory only, call save_config to persist).

        Args:
            section: Section name
            param: Parameter name
            value: New value
            validate: Whether to validate before setting

        Returns:
            ValidationResult
        """
        if validate:
            result = self.validate_value(section, param, value)
            if not result.valid:
                return result
        else:
            result = ValidationResult(True, ValidationStatus.VALID, [], [])

        # Ensure section exists
        if section not in self._config:
            self._config[section] = {}

        # Set value
        if isinstance(self._config[section], dict):
            # Capture old value for audit
            old_value = self._config[section].get(param)
            self._config[section][param] = value
            logger.info("Set config parameter %s.%s", section, param)

            # Log to audit trail
            if audit:
                self.log_audit_entry(
                    action='update',
                    section=section,
                    parameter=param,
                    old_value=old_value,
                    new_value=value,
                    source=source,
                )
        else:
            result.errors.append(f"Section {section} is not a dictionary")
            result.valid = False
            result.status = ValidationStatus.ERROR

        return result

    def set_path(
        self,
        path: List[str] | Tuple[str, ...],
        value: Any,
        *,
        validate: bool = True,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """Apply one supported path update without exposing partial state."""
        with self._mutation_lock:
            return self._set_path_locked(
                path,
                value,
                validate=validate,
                audit=audit,
                source=source,
            )

    def _set_path_locked(
        self,
        path: List[str] | Tuple[str, ...],
        value: Any,
        *,
        validate: bool = True,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """Set a supported root or section/parameter path in memory."""
        parts = list(path)
        if len(parts) == 2:
            return self.set_parameter(
                parts[0],
                parts[1],
                value,
                validate,
                audit=audit,
                source=source,
            )
        if len(parts) != 1:
            return ValidationResult(
                False,
                ValidationStatus.ERROR,
                ["Config paths must contain one or two components"],
                [],
            )

        result = (
            self.validate_path(parts, value)
            if validate
            else ValidationResult(True, ValidationStatus.VALID, [], [])
        )
        if not result.valid:
            return result
        root_key = parts[0]
        old_value = self._config.get(root_key)
        self._config[root_key] = value
        if self._config_raw is not None:
            self._config_raw[root_key] = value
        logger.info("Set root config parameter %s", root_key)
        if audit:
            self.log_audit_entry(
                action="update",
                section=root_key,
                parameter=None,
                old_value=old_value,
                new_value=value,
                source=source,
            )
        return result

    def set_section(
        self,
        section: str,
        values: Dict,
        validate: bool = True,
        *,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """Apply a complete in-memory section update atomically for readers."""
        with self._mutation_lock:
            return self._set_section_locked(
                section,
                values,
                validate,
                audit=audit,
                source=source,
            )

    def _set_section_locked(
        self,
        section: str,
        values: Dict,
        validate: bool = True,
        *,
        audit: bool = False,
        source: str = "api",
    ) -> ValidationResult:
        """Validate a complete section update before mutating in-memory state."""
        if not isinstance(values, dict):
            return ValidationResult(
                False,
                ValidationStatus.ERROR,
                ["Section update must be an object"],
                [],
            )
        all_errors = []
        all_warnings = []

        for param, value in values.items():
            result = (
                self.validate_value(section, param, value)
                if validate
                else ValidationResult(True, ValidationStatus.VALID, [], [])
            )
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        valid = len(all_errors) == 0
        status = ValidationStatus.ERROR if all_errors else (
            ValidationStatus.WARNING if all_warnings else ValidationStatus.VALID
        )

        aggregate = ValidationResult(valid, status, all_errors, all_warnings)
        if not valid:
            return aggregate

        for param, value in values.items():
            result = self.set_parameter(
                section,
                param,
                value,
                validate=False,
                audit=audit,
                source=source,
            )
            if not result.valid:
                raise RuntimeError(
                    f"Validated section update could not set {section}.{param}"
                )
        return aggregate

    def remove_path(self, path: List[str] | Tuple[str, ...]) -> bool:
        """Remove a root or section/parameter path from round-trip config state."""
        with self._mutation_lock:
            return self._remove_path_locked(path)

    def _remove_path_locked(self, path: List[str] | Tuple[str, ...]) -> bool:
        """Remove a path while the in-process mutation lock is held."""
        parts = list(path)
        if len(parts) == 1:
            root_key = parts[0]
            if root_key not in self._config:
                return False
            del self._config[root_key]
            if self._config_raw is not None and root_key in self._config_raw:
                del self._config_raw[root_key]
            return True
        if len(parts) != 2:
            raise ValueError("Config paths must contain one or two components")

        section, param = parts
        section_data = self._config.get(section)
        if not isinstance(section_data, dict) or param not in section_data:
            return False
        del section_data[param]

        if (
            self._config_raw is not None
            and section in self._config_raw
            and isinstance(self._config_raw[section], dict)
            and param in self._config_raw[section]
        ):
            del self._config_raw[section][param]

        if not section_data:
            del self._config[section]
            if self._config_raw is not None and section in self._config_raw:
                del self._config_raw[section]
        return True

    def remove_parameter(self, section: str, param: str) -> bool:
        """Backward-compatible section/parameter removal helper."""
        return self.remove_path([section, param])

    def remove_registered_retirement(
        self,
        path: List[str] | Tuple[str, ...] | str,
        parameter: Optional[str] = None,
    ) -> bool:
        """Remove only an exact path authorized by the retirement registry."""
        if isinstance(path, str):
            normalized_path = [path] if parameter is None else [path, parameter]
            retirement = self.get_registered_retirement(path, parameter)
        else:
            normalized_path = list(path)
            retirement = self.get_registered_retirement(normalized_path)
        if retirement is None:
            return False
        return self.remove_path(normalized_path)

    def get_sync_meta(self) -> Dict[str, Any]:
        """Load persisted config sync metadata, rejecting corruption."""
        meta_path = self._get_path(self.SYNC_META_PATH)
        if meta_path.is_symlink():
            raise RuntimeError(
                "Could not load config sync metadata safely: metadata path is a symlink"
            )
        if not meta_path.exists():
            return {}
        try:
            if not meta_path.is_file() or meta_path.is_symlink():
                raise ValueError(
                    "Config sync metadata must be a regular non-symlink file"
                )
            self._restrict_path_permissions(meta_path)
            with open(meta_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("Config sync metadata root must be an object")
            snapshot = loaded.get("defaults_snapshot")
            if snapshot is not None and not isinstance(snapshot, dict):
                raise ValueError("Config sync defaults_snapshot must be an object")
            return dict(loaded)
        except Exception as e:
            logger.error("Could not load config sync metadata: %s", e)
            raise RuntimeError(f"Could not load config sync metadata safely: {e}") from e

    def save_sync_meta(
        self,
        meta: Dict[str, Any],
        *,
        lock_acquired: bool = False,
        expected_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist config sync metadata with CAS and restricted permissions."""
        if not isinstance(meta, dict):
            raise ValueError("Config sync metadata must be an object")
        if not lock_acquired:
            with self.mutation_guard():
                return self.save_sync_meta(
                    meta,
                    lock_acquired=True,
                    expected_digest=expected_digest,
                    write_receipt=write_receipt,
                )

        meta_path = self._get_path(self.SYNC_META_PATH)
        try:
            if expected_digest is not None and self._file_digest(meta_path) != expected_digest:
                raise RuntimeError("Config sync metadata changed during mutation")
            payload = json.dumps(meta, indent=2, ensure_ascii=True).encode("utf-8")
            self._write_bytes_atomic(
                meta_path,
                payload,
                mode=0o600,
                expected_digest=expected_digest,
                write_receipt=write_receipt,
                receipt_key="sync_meta",
            )
            return True
        except Exception as e:
            logger.error(f"Could not save sync metadata: {e}")
            return False

    def refresh_defaults_snapshot(self) -> bool:
        """Store current defaults as baseline for changed-default detection."""
        with self.mutation_guard():
            meta_path = self._get_path(self.SYNC_META_PATH)
            expected_digest = self._file_digest(meta_path)
            meta = self.get_sync_meta()
            meta['defaults_snapshot'] = self.get_effective_defaults()
            meta['defaults_snapshot_saved_at'] = datetime.now().isoformat()
            meta['schema_version'] = self.get_schema_version()
            meta['defaults_snapshot_mode'] = 'full'
            meta['defaults_snapshot_provenance'] = 'explicit_current_defaults_refresh'
            meta['defaults_snapshot_source_digest'] = self._file_digest(
                self._get_path(self.DEFAULT_PATH)
            )
            return self.save_sync_meta(
                meta,
                lock_acquired=True,
                expected_digest=expected_digest,
            )

    def initialize_defaults_snapshot(self) -> bool:
        """Create a defaults baseline only when one does not already exist."""
        with self.mutation_guard():
            meta_path = self._get_path(self.SYNC_META_PATH)
            expected_digest = self._file_digest(meta_path)
            meta = self.get_sync_meta()
            snapshot = meta.get('defaults_snapshot')
            if isinstance(snapshot, dict) and bool(snapshot):
                if meta_path.exists():
                    self._restrict_path_permissions(meta_path)
                return True
            meta['defaults_snapshot'] = self.get_effective_defaults()
            meta['defaults_snapshot_saved_at'] = datetime.now().isoformat()
            meta['schema_version'] = self.get_schema_version()
            meta['defaults_snapshot_mode'] = 'full'
            meta['defaults_snapshot_provenance'] = 'current_checked_in_defaults'
            meta['defaults_snapshot_source_digest'] = self._file_digest(
                self._get_path(self.DEFAULT_PATH)
            )
            return self.save_sync_meta(
                meta,
                lock_acquired=True,
                expected_digest=expected_digest,
            )

    def initialize_defaults_snapshot_from(
        self,
        defaults_snapshot: Dict[str, Any],
        *,
        provenance: str,
        source_digest: str,
    ) -> bool:
        """Initialize a missing baseline from staged pre-update defaults."""
        if not isinstance(defaults_snapshot, dict) or not defaults_snapshot:
            raise ValueError("Staged defaults baseline must be a non-empty mapping")
        if not isinstance(provenance, str) or not provenance.strip():
            raise ValueError("Defaults baseline provenance is required")
        if re.fullmatch(r"[a-f0-9]{64}", source_digest) is None:
            raise ValueError("Defaults baseline source_digest must be SHA-256")

        with self.mutation_guard():
            meta_path = self._get_path(self.SYNC_META_PATH)
            expected_digest = self._file_digest(meta_path)
            meta = self.get_sync_meta()
            existing = meta.get("defaults_snapshot")
            if isinstance(existing, dict) and existing:
                if meta_path.exists():
                    self._restrict_path_permissions(meta_path)
                return True
            meta["defaults_snapshot"] = copy.deepcopy(defaults_snapshot)
            meta["defaults_snapshot_saved_at"] = datetime.now().isoformat()
            meta["schema_version"] = self.get_schema_version()
            meta["defaults_snapshot_mode"] = "full"
            meta["defaults_snapshot_provenance"] = provenance.strip()
            meta["defaults_snapshot_source_digest"] = source_digest
            return self.save_sync_meta(
                meta,
                lock_acquired=True,
                expected_digest=expected_digest,
            )

    def revert_to_default(
        self,
        section: Optional[str] = None,
        param: Optional[str] = None
    ) -> bool:
        """Revert an in-memory scope without exposing a partial replacement."""
        with self._mutation_lock:
            return self._revert_to_default_locked(section, param)

    def _revert_to_default_locked(
        self,
        section: Optional[str] = None,
        param: Optional[str] = None
    ) -> bool:
        """
        Revert config to default values.

        Args:
            section: Optional section to revert (None = all)
            param: Optional parameter to revert (requires section)

        Returns:
            True if successful
        """
        try:
            if section and param:
                # Revert single parameter
                default_section = self._default.get(section)
                if not isinstance(default_section, dict) or param not in default_section:
                    return False
                self.set_parameter(
                    section,
                    param,
                    copy.deepcopy(default_section[param]),
                    validate=False,
                    audit=False,
                )
            elif section:
                # Revert entire section
                if section not in self._default:
                    return False
                self._config[section] = copy.deepcopy(self._default[section])
            else:
                # Revert everything
                self._config = copy.deepcopy(self._default)

            logger.info(f"Reverted to default: section={section}, param={param}")
            return True

        except Exception as e:
            logger.error(f"Error reverting to default: {e}")
            return False

    # =========================================================================
    # Persistence
    # =========================================================================

    def runtime_config_exists(self) -> bool:
        """Return whether an operator-owned runtime config exists on disk."""
        config_path = self._get_path(self.CONFIG_PATH)
        if config_path.is_symlink():
            raise ValueError("Runtime config must be a regular non-symlink file")
        if not config_path.exists():
            return False
        if not config_path.is_file():
            raise ValueError("Runtime config must be a regular non-symlink file")
        return True

    def create_backup(
        self,
        *,
        lock_acquired: bool = False,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a durable owner-only backup of the current runtime config."""
        if not self.runtime_config_exists():
            return None
        return self._create_backup(
            lock_acquired=lock_acquired,
            write_receipt=write_receipt,
        )

    def save_config(
        self,
        backup: bool = True,
        *,
        lock_acquired: bool = False,
        expected_config_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Save current config to YAML file with atomic writes and file locking.

        Uses a safe write pattern:
        1. Acquire file lock (if available)
        2. Write to temporary file
        3. Flush and sync to disk
        4. Atomic rename to target file
        5. Release lock

        Args:
            backup: Whether to create backup before saving

        Returns:
            True if successful
        """
        if not lock_acquired:
            with self.mutation_guard():
                return self.save_config(
                    backup,
                    lock_acquired=True,
                    expected_config_digest=expected_config_digest,
                    write_receipt=write_receipt,
                )

        config_path = self._get_path(self.CONFIG_PATH)
        try:
            if (
                expected_config_digest is not None
                and self._file_digest(config_path) != expected_config_digest
            ):
                raise RuntimeError("Runtime config changed during mutation")

            # A requested backup is part of the transaction, not best effort.
            if (
                backup
                and config_path.exists()
                and self._create_backup(
                    lock_acquired=True,
                    write_receipt=write_receipt,
                ) is None
            ):
                raise RuntimeError("Could not create required config backup")

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120
            yaml.default_flow_style = False

            # If we have raw config with comments, update it
            if self._config_raw is not None:
                for section in list(self._config_raw):
                    if section not in self._config:
                        del self._config_raw[section]
                # Update raw config with current values
                for section, params in self._config.items():
                    if section in self._config_raw:
                        if isinstance(params, dict) and isinstance(self._config_raw[section], dict):
                            for key in list(self._config_raw[section]):
                                if key not in params:
                                    del self._config_raw[section][key]
                            for key, value in params.items():
                                self._config_raw[section][key] = value
                        else:
                            self._config_raw[section] = params
                    else:
                        self._config_raw[section] = params
                data_to_write = self._config_raw
            else:
                data_to_write = self._config

            from io import StringIO

            output = StringIO()
            yaml.dump(data_to_write, output)
            self._write_bytes_atomic(
                config_path,
                output.getvalue().encode("utf-8"),
                mode=0o600,
                expected_digest=expected_config_digest,
                write_receipt=write_receipt,
                receipt_key="runtime_config",
            )
            logger.info(f"Saved config to {config_path} (atomic)")
            return True

        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

    def _create_backup(
        self,
        *,
        lock_acquired: bool = False,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a collision-safe, owner-only backup of current config."""
        if not lock_acquired:
            with self.mutation_guard():
                return self._create_backup(
                    lock_acquired=True,
                    write_receipt=write_receipt,
                )
        backup_path = None
        try:
            backup_dir = self._get_path(self.BACKUP_DIR)
            if backup_dir.is_symlink():
                raise ValueError("Config backup path must be a regular directory")
            backup_dir.mkdir(parents=True, exist_ok=True)
            if not backup_dir.is_dir() or backup_dir.is_symlink():
                raise ValueError("Config backup path must be a regular directory")
            self._restrict_path_permissions(backup_dir, directory=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            fd, backup_name = tempfile.mkstemp(
                suffix=".yaml",
                prefix=f"config_{timestamp}_",
                dir=backup_dir,
            )
            os.close(fd)
            backup_path = Path(backup_name)

            config_path = self._get_path(self.CONFIG_PATH)
            if config_path.is_symlink() or not config_path.is_file():
                raise ValueError("Runtime config must be a regular non-symlink file")
            shutil.copyfile(config_path, backup_path)
            self._restrict_path_permissions(backup_path)
            with open(backup_path, "rb") as backup_file:
                os.fsync(backup_file.fileno())
            self._fsync_directory(backup_dir)

            logger.info(f"Created backup: {backup_path}")

            # Establish ownership before cleanup can remove an old managed
            # backup. Refresh it afterward to describe the exact final
            # inventory. If the refresh fails, rollback will detect the
            # mismatch and preserve state for operator recovery.
            self._record_backup_inventory(write_receipt)

            # Cleanup old backups
            self._cleanup_old_backups()
            self._record_backup_inventory(write_receipt)

            return str(backup_path)

        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            if backup_path is not None:
                try:
                    backup_path.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                self._record_backup_inventory(write_receipt)
            except Exception as receipt_error:
                logger.error(
                    "Could not record failed backup inventory for rollback: %s",
                    receipt_error,
                )
            return None

    def _record_backup_inventory(
        self,
        write_receipt: Optional[Dict[str, Any]],
    ) -> None:
        """Record exact managed backup ownership when a transaction requested it."""
        if write_receipt is None:
            return
        write_receipt["backups"] = {
            backup_file.name: self._file_digest(backup_file)
            for backup_file in self._get_managed_backup_files()
        }

    def _write_bytes_atomic(
        self,
        path: Path,
        payload: bytes,
        *,
        mode: int,
        expected_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
        receipt_key: Optional[str] = None,
    ) -> str:
        """Durably replace one file after an optional final CAS check.

        The returned digest is a write receipt for the exact payload supplied
        by this call. When a mutable receipt and key are supplied, ownership is
        recorded immediately after ``os.replace`` so a later permission or
        directory-fsync failure can still be rolled back conditionally.
        """
        if write_receipt is not None and not receipt_key:
            raise ValueError("A receipt key is required for write ownership")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            fd, temp_name = tempfile.mkstemp(
                suffix=".tmp",
                dir=path.parent,
                prefix=f".{path.name}.",
            )
            temp_path = Path(temp_name)
            with os.fdopen(fd, "wb") as temp_file:
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            if os.name != "nt":
                os.chmod(temp_path, mode)
            else:
                self._restrict_path_permissions(temp_path)
            if (
                expected_digest is not None
                and self._file_digest(path) != expected_digest
            ):
                raise PersistenceConflictError(
                    f"Persisted file changed before replacement: {path}"
                )
            os.replace(temp_path, path)
            temp_path = None
            persisted_digest = hashlib.sha256(payload).hexdigest()
            if write_receipt is not None:
                write_receipt[receipt_key] = persisted_digest
            self._restrict_path_permissions(path, directory=False)
            self._fsync_directory(path.parent)
            return persisted_digest
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _unlink_file_if_digest(
        self,
        path: Path,
        expected_digest: Optional[str],
    ) -> None:
        """Remove one file after the same optimistic CAS used for writes."""
        if (
            expected_digest is not None
            and self._file_digest(path) != expected_digest
        ):
            raise PersistenceConflictError(
                f"Persisted file changed before removal: {path}"
            )
        if not path.exists():
            return
        if path.is_symlink() or not path.is_file():
            raise PersistenceConflictError(
                f"Persisted path is no longer a regular file: {path}"
            )
        path.unlink()
        self._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        """Durably persist directory entry changes where the platform supports it."""
        if not hasattr(os, "O_DIRECTORY"):
            return
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def _get_managed_backup_files(self) -> List[Path]:
        """Return owner-only, regular backup files with supported identifiers."""
        backup_dir = self._get_path(self.BACKUP_DIR)
        if backup_dir.is_symlink():
            raise ValueError("Config backup path must be a regular directory")
        if not backup_dir.exists():
            return []
        if not backup_dir.is_dir() or backup_dir.is_symlink():
            raise ValueError("Config backup path must be a regular directory")
        self._restrict_path_permissions(backup_dir, directory=True)

        managed = []
        for candidate in backup_dir.iterdir():
            if (
                candidate.suffix != ".yaml"
                or self._BACKUP_ID_RE.fullmatch(candidate.stem) is None
                or not candidate.is_file()
                or candidate.is_symlink()
            ):
                continue
            self._restrict_path_permissions(candidate)
            managed.append(candidate)
        return managed

    def _cleanup_old_backups(self):
        """Remove old backups exceeding MAX_BACKUPS."""
        try:
            backups = sorted(
                self._get_managed_backup_files(),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            for old_backup in backups[self.MAX_BACKUPS:]:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")

        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")

    def get_backup_history(self, limit: int = 20) -> List[ConfigBackup]:
        """Get list of available backups."""
        backups = []
        backup_dir = self._get_path(self.BACKUP_DIR)

        if not backup_dir.exists():
            return backups

        for backup_file in sorted(
            self._get_managed_backup_files(),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:max(0, limit)]:
            backups.append(ConfigBackup(
                id=backup_file.stem,
                filename=backup_file.name,
                timestamp=backup_file.stat().st_mtime,
                size=backup_file.stat().st_size
            ))

        return backups

    def restore_backup(
        self,
        backup_id: str,
        *,
        lock_acquired: bool = False,
        expected_config_digest: Optional[str] = None,
        write_receipt: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Restore config from a backup.

        Args:
            backup_id: Backup ID (filename without extension)

        Returns:
            True if successful
        """
        if self._BACKUP_ID_RE.fullmatch(backup_id) is None:
            logger.error("Rejected invalid config backup id")
            return False
        if not lock_acquired:
            with self.mutation_guard():
                return self.restore_backup(
                    backup_id,
                    lock_acquired=True,
                    expected_config_digest=expected_config_digest,
                    write_receipt=write_receipt,
                )

        try:
            backup_dir = self._get_path(self.BACKUP_DIR)
            backup_path = backup_dir / f"{backup_id}.yaml"

            if (
                not backup_path.is_file()
                or backup_path.is_symlink()
                or backup_path not in self._get_managed_backup_files()
            ):
                logger.error(f"Backup not found: {backup_path}")
                return False
            self._restrict_path_permissions(backup_path)

            # Load backup using ruamel.yaml
            yaml_loader = YAML()
            yaml_loader.preserve_quotes = True
            with open(backup_path, 'r', encoding='utf-8') as f:
                loaded = yaml_loader.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("Config backup root must be a mapping")
            validation = self.validate_config_mapping(
                dict(loaded),
                require_safety=True,
            )
            if not validation.valid:
                raise ValueError(
                    "Config backup failed validation: " + "; ".join(validation.errors)
                )
            self._config = copy.deepcopy(dict(loaded))
            self._config_raw = loaded

            # Save as current config
            if not self.save_config(
                backup=True,
                lock_acquired=True,
                expected_config_digest=expected_config_digest,
                write_receipt=write_receipt,
            ):
                raise RuntimeError("Could not persist restored config backup")

            logger.info(f"Restored config from backup: {backup_id}")
            return True

        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False

    # =========================================================================
    # Diff & Comparison
    # =========================================================================

    def get_diff(self, config1: Dict, config2: Dict) -> List[DiffEntry]:
        """
        Get differences between two configs.

        Args:
            config1: First config
            config2: Second config

        Returns:
            List of differences
        """
        diffs = []

        all_sections = set(config1.keys()) | set(config2.keys())

        for section in all_sections:
            section1 = config1.get(section, {})
            section2 = config2.get(section, {})

            if not isinstance(section1, dict):
                section1 = {'_value': section1} if section1 is not None else {}
            if not isinstance(section2, dict):
                section2 = {'_value': section2} if section2 is not None else {}

            all_params = set(section1.keys()) | set(section2.keys())

            for param in all_params:
                val1 = section1.get(param)
                val2 = section2.get(param)

                if val1 is None and val2 is not None:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=None,
                        new_value=val2,
                        change_type='added'
                    ))
                elif val1 is not None and val2 is None:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=val1,
                        new_value=None,
                        change_type='removed'
                    ))
                elif val1 != val2:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=val1,
                        new_value=val2,
                        change_type='changed'
                    ))

        return diffs

    def get_changed_from_default(self) -> List[DiffEntry]:
        """Get parameters that differ from defaults."""
        with self._mutation_lock:
            defaults = copy.deepcopy(self._default)
            current = copy.deepcopy(self._config)
        return self.get_diff(defaults, current)

    def diff_with_default(self, section: Optional[str] = None) -> List[DiffEntry]:
        """Get diff between current config and defaults."""
        with self._mutation_lock:
            if section:
                defaults = {section: copy.deepcopy(self._default.get(section, {}))}
                current = {section: copy.deepcopy(self._config.get(section, {}))}
            else:
                defaults = copy.deepcopy(self._default)
                current = copy.deepcopy(self._config)
        return self.get_diff(defaults, current)

    # =========================================================================
    # Import/Export
    # =========================================================================

    def export_config(
        self,
        sections: Optional[List[str]] = None,
        changes_only: bool = False
    ) -> Dict:
        """
        Export configuration.

        Args:
            sections: Optional list of sections to export (None = all)
            changes_only: Only export values that differ from defaults

        Returns:
            Config dict for export
        """
        with self._mutation_lock:
            if changes_only:
                # Build config with only changed values from one coherent snapshot.
                export_config = {}
                diffs = self.get_diff(
                    copy.deepcopy(self._default),
                    copy.deepcopy(self._config),
                )

                for diff in diffs:
                    if sections and diff.section not in sections:
                        continue
                    if diff.section not in export_config:
                        export_config[diff.section] = {}
                    export_config[diff.section][diff.parameter] = copy.deepcopy(
                        diff.new_value
                    )

                return export_config

            if sections:
                return {
                    section: copy.deepcopy(self._config.get(section, {}))
                    for section in sections
                }

            return copy.deepcopy(self._config)

    def import_config(
        self,
        data: Dict,
        merge_mode: str = 'merge'
    ) -> Tuple[bool, List[DiffEntry]]:
        """Build and install one imported in-memory candidate atomically."""
        with self._mutation_lock:
            return self._import_config_locked(data, merge_mode)

    def _import_config_locked(
        self,
        data: Dict,
        merge_mode: str = 'merge'
    ) -> Tuple[bool, List[DiffEntry]]:
        """
        Import configuration data.

        Args:
            data: Config data to import
            merge_mode: 'merge' (update existing) or 'replace' (full replacement)

        Returns:
            Tuple of (success, list of changes made)
        """
        try:
            if not isinstance(data, dict):
                raise ValueError("Imported config root must be an object")
            if merge_mode not in {'merge', 'replace'}:
                raise ValueError("Import merge_mode must be 'merge' or 'replace'")

            candidate = (
                self._deep_merge_mapping(self._default, data)
                if merge_mode == 'replace'
                else copy.deepcopy(self._config)
            )
            if merge_mode == 'merge':
                candidate = self._deep_merge_mapping(candidate, data)

            validation = self.validate_config_mapping(
                candidate,
                require_safety=merge_mode == 'replace',
            )
            if not validation.valid:
                raise ValueError(
                    "Imported config failed validation: " + "; ".join(validation.errors)
                )

            diffs = self.get_diff(self._config, candidate)
            self._config = candidate
            self._config_raw = None

            logger.info(f"Imported config with mode={merge_mode}, changes={len(diffs)}")
            return True, diffs

        except Exception as e:
            logger.error(f"Error importing config: {e}")
            return False, []

    @classmethod
    def _deep_merge_mapping(
        cls,
        base: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Recursively merge mappings without dropping untouched nested siblings."""
        merged = copy.deepcopy(base)
        for key, value in updates.items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = cls._deep_merge_mapping(existing, value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_reload_tier(self, section: str, param: str) -> str:
        """
        Get the reload tier for a parameter.

        Tiers:
        - 'immediate': Takes effect immediately after Parameters.reload_config()
        - 'follower_restart': Requires follower restart to take effect
        - 'tracker_restart': Requires tracker restart to take effect
        - 'system_restart': Requires full system restart

        Returns:
            Reload tier string, defaults to 'system_restart' for safety
        """
        param_schema = self.get_parameter_schema(section, param)
        if param_schema:
            return param_schema.get('reload_tier', 'system_restart')
        return 'system_restart'

    def is_reboot_required(self, section: str, param: str) -> bool:
        """
        Check if a parameter requires system restart.

        DEPRECATED: Use get_reload_tier() for more granular control.
        This method is kept for backward compatibility.
        """
        tier = self.get_reload_tier(section, param)
        return tier == 'system_restart'

    def get_reload_message(self, reload_tier: str) -> str:
        """Get user-friendly message for reload tier."""
        messages = {
            'immediate': 'Changes applied immediately',
            'follower_restart': 'Restart follower to apply changes',
            'tracker_restart': 'Restart tracker to apply changes',
            'system_restart': 'System restart required to apply changes'
        }
        return messages.get(reload_tier, 'Unknown reload tier')

    def search_parameters(
        self,
        query: str,
        section: Optional[str] = None,
        param_type: Optional[str] = None,
        modified_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """Search one coherent config/default/schema generation."""
        with self._mutation_lock:
            return self._search_parameters_locked(
                query,
                section,
                param_type,
                modified_only,
                limit,
                offset,
            )

    def _search_parameters_locked(
        self,
        query: str,
        section: Optional[str] = None,
        param_type: Optional[str] = None,
        modified_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        Search for parameters matching a query with filtering and pagination.

        Args:
            query: Search string
            section: Filter by section name
            param_type: Filter by parameter type (integer, float, boolean, etc.)
            modified_only: Only return parameters that differ from default
            limit: Max results to return
            offset: Skip first N results

        Returns:
            Dict with 'results', 'total', 'limit', 'offset'
        """
        all_results = []
        query_lower = query.lower() if query else ''

        for section_name, section_data in self._schema.get('sections', {}).items():
            # Section filter
            if section and section_name != section:
                continue

            for param_name, param_data in section_data.get('parameters', {}).items():
                # Type filter
                if param_type and param_data.get('type') != param_type:
                    continue

                current_value = self.get_parameter(section_name, param_name)
                default_value = self.get_default_parameter(section_name, param_name)

                # Modified-only filter
                if modified_only and current_value == default_value:
                    continue

                # Search in param name and description
                if query_lower and not (
                    query_lower in param_name.lower() or
                    query_lower in param_data.get('description', '').lower()
                ):
                    continue

                all_results.append({
                    'section': section_name,
                    'parameter': param_name,
                    'description': param_data.get('description', ''),
                    'type': param_data.get('type', 'any'),
                    'current_value': self.redact_value(
                        current_value,
                        [section_name, param_name],
                    ),
                    'default_value': self.redact_value(
                        default_value,
                        [section_name, param_name],
                    ),
                    'is_modified': current_value != default_value
                })

        total = len(all_results)
        paginated = all_results[offset:offset + limit]

        return {
            'results': paginated,
            'total': total,
            'limit': limit,
            'offset': offset
        }
