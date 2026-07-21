"""Trust, containment, and transaction policy for executable model artifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import threading
import time
import unicodedata
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple


MODEL_PROVENANCE_SCHEMA_VERSION = 1
MODEL_REGISTRATION_RECEIPT_SCHEMA_VERSION = 1
MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION = 1
NCNN_MANIFEST_SCHEMA_VERSION = 2
NCNN_MANIFEST_DIGEST_DOMAIN = "pixeagle-ncnn-manifest-v2"
NCNN_DIRECTORY_DIGEST_DOMAIN = "pixeagle-ncnn-directory-v2"
MODEL_PROVENANCE_FILENAME = ".model-provenance.json"
MODEL_STORE_LOCK_FILENAME = ".model-mutation.lock"
MODEL_INGEST_LOCK_FILENAME = ".model-ingest.lock"
DEFAULT_MODELS_ROOT = Path(__file__).resolve().parents[2] / "models"
DEFAULT_MAX_MODEL_BYTES = 256 * 1024 * 1024
HARD_MAX_MODEL_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_EXPORT_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_EXPORT_FILES = 128
DEFAULT_MAX_EXPORT_ENTRIES = 256
DEFAULT_MAX_NCNN_MANIFEST_BYTES = 512 * 1024
DEFAULT_MAX_NCNN_RELATIVE_PATH_BYTES = 4096
MAX_MODEL_DISPLAY_NAME_LENGTH = 80
MODEL_FILENAME_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,122}\.pt$"
)
NCNN_DIRECTORY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,111}_ncnn_model$"
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


_ACTIVE_LEASES_LOCK = threading.RLock()
_ACTIVE_LEASES: Dict[
    Tuple[int, int, str, str],
    List[weakref.ReferenceType],
] = {}
_LIVE_LEASES: "weakref.WeakSet[ModelStoreLease]" = weakref.WeakSet()


class ModelArtifactPolicyError(ValueError):
    """Raised when an artifact violates the model trust policy."""


class ModelRegistryCorruptionError(ModelArtifactPolicyError):
    """Raised when the executable-model provenance registry is unreadable or unsafe."""


class ModelStoreBusyError(ModelArtifactPolicyError):
    """Raised when another process or loaded runtime owns an incompatible lease."""


class ModelArtifactNotFoundError(ModelArtifactPolicyError):
    """Raised when a requested artifact has no trusted store entry or file."""


@dataclass(frozen=True)
class ModelLoaderBinding:
    """Format-preserving path bound to one descriptor owned by an active lease."""

    path: Path
    artifact_name: str
    descriptor: int
    directory: bool
    _lease_ref: weakref.ReferenceType
    _lease_generation: object

    def verified_path(self) -> Path:
        lease = self._lease_ref()
        if lease is None:
            raise ModelArtifactPolicyError("Model loader binding lease is unavailable")
        return lease.assert_loader_binding(self)


def normalize_sha256(value: Optional[str], *, required: bool = False) -> Optional[str]:
    """Normalize and validate a SHA-256 digest."""
    normalized = str(value or "").strip().lower()
    if not normalized:
        if required:
            raise ModelArtifactPolicyError("An expected SHA-256 digest is required")
        return None
    if not SHA256_PATTERN.fullmatch(normalized):
        raise ModelArtifactPolicyError(
            "SHA-256 must contain exactly 64 hexadecimal characters"
        )
    return normalized


def validate_model_filename(filename: str) -> str:
    """Return a safe direct-child `.pt` filename or raise."""
    candidate = str(filename or "").strip()
    if not MODEL_FILENAME_PATTERN.fullmatch(candidate):
        raise ModelArtifactPolicyError(
            "Model filename must be a simple .pt name using letters, numbers, '.', "
            "'_' or '-' (maximum 126 characters)"
        )
    if Path(candidate).name != candidate:
        raise ModelArtifactPolicyError("Model filename must not contain a path")
    return candidate


def validate_ncnn_directory_name(name: str) -> str:
    """Return a canonical direct-child NCNN export directory name."""
    candidate = str(name or "").strip()
    if not NCNN_DIRECTORY_PATTERN.fullmatch(candidate) or Path(candidate).name != candidate:
        raise ModelArtifactPolicyError("NCNN export directory name is not canonical")
    return candidate


def validate_models_root(models_root: Path, *, create: bool = False) -> Path:
    """Resolve an owner-only model root, optionally tightening its mode to 0700."""
    candidate = Path(models_root).expanduser()
    if candidate.is_symlink():
        raise ModelArtifactPolicyError("Models root must not be a symbolic link")
    if not candidate.exists():
        if not create:
            raise ModelArtifactPolicyError(f"Models root does not exist: {candidate}")
        candidate.mkdir(parents=True, mode=0o700)
    root = candidate.resolve(strict=True)
    root_stat = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ModelArtifactPolicyError("Models root must be a directory")
    expected_uid = getattr(os, "geteuid", lambda: root_stat.st_uid)()
    if root_stat.st_uid != expected_uid:
        raise ModelArtifactPolicyError("Models root must be owned by the PixEagle user")
    root_mode = stat.S_IMODE(root_stat.st_mode)
    if create and root_mode != 0o700:
        os.chmod(root, 0o700)
        root_stat = os.stat(root, follow_symlinks=False)
        root_mode = stat.S_IMODE(root_stat.st_mode)
    if root_mode != 0o700:
        raise ModelArtifactPolicyError(
            "Models root must be owner-only with mode 0700; "
            f"run: chmod 700 {root}"
        )
    return root


def resolve_model_path(models_root: Path, filename: str) -> Path:
    """Resolve a model as a non-symlink direct child of the models root."""
    safe_name = validate_model_filename(filename)
    root = validate_models_root(models_root)
    candidate = root / safe_name
    if candidate.is_symlink():
        raise ModelArtifactPolicyError("Symbolic-link model artifacts are not allowed")
    if candidate.resolve(strict=False).parent != root:
        raise ModelArtifactPolicyError("Model path escapes the configured models folder")
    return candidate


def _validate_regular_descriptor(
    descriptor: int,
    *,
    expected_uid: int,
    max_bytes: int,
) -> os.stat_result:
    artifact_stat = os.fstat(descriptor)
    if not stat.S_ISREG(artifact_stat.st_mode):
        raise ModelArtifactPolicyError("Model artifact must be a regular file")
    if artifact_stat.st_uid != expected_uid:
        raise ModelArtifactPolicyError("Model artifact must be owned by the PixEagle user")
    if artifact_stat.st_nlink != 1:
        raise ModelArtifactPolicyError("Hard-linked model artifacts are not allowed")
    if stat.S_IMODE(artifact_stat.st_mode) & 0o022:
        raise ModelArtifactPolicyError(
            "Model artifact must not be writable by group or other users"
        )
    if artifact_stat.st_size <= 0:
        raise ModelArtifactPolicyError("Model artifact is empty")
    if artifact_stat.st_size > max_bytes:
        raise ModelArtifactPolicyError(
            f"Model artifact exceeds the {max_bytes} byte safety limit"
        )
    return artifact_stat


def _stat_identity(value: os.stat_result) -> Tuple[int, ...]:
    """Return fields that must stay stable across a verified descriptor read."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _assert_descriptor_matches_stat(
    descriptor: int,
    expected: os.stat_result,
    *,
    message: str,
) -> os.stat_result:
    observed = os.fstat(descriptor)
    if _stat_identity(observed) != _stat_identity(expected):
        raise ModelArtifactPolicyError(message)
    return observed


def sha256_descriptor(
    descriptor: int,
    *,
    expected_uid: int,
    max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
) -> tuple[str, os.stat_result]:
    """Hash a held regular-file descriptor and rewind it before returning."""
    artifact_stat = _validate_regular_descriptor(
        descriptor,
        expected_uid=expected_uid,
        max_bytes=max_bytes,
    )
    digest = hashlib.sha256()
    consumed = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while consumed < artifact_stat.st_size:
        chunk = os.read(
            descriptor,
            min(1024 * 1024, artifact_stat.st_size - consumed),
        )
        if not chunk:
            raise ModelArtifactPolicyError(
                "Model artifact became shorter while it was hashed"
            )
        consumed += len(chunk)
        if consumed > max_bytes:
            raise ModelArtifactPolicyError(
                f"Model artifact exceeds the {max_bytes} byte safety limit"
            )
        digest.update(chunk)
    if os.read(descriptor, 1):
        raise ModelArtifactPolicyError(
            "Model artifact became larger while it was hashed"
        )
    _assert_descriptor_matches_stat(
        descriptor,
        artifact_stat,
        message="Model artifact mutated while it was hashed",
    )
    os.lseek(descriptor, 0, os.SEEK_SET)
    if consumed != artifact_stat.st_size:
        raise ModelArtifactPolicyError("Model artifact changed while it was hashed")
    return digest.hexdigest(), artifact_stat


def sha256_file(path: Path, *, max_bytes: int = DEFAULT_MAX_MODEL_BYTES) -> str:
    """Hash one bounded regular file through a no-follow descriptor."""
    artifact = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(artifact, flags)
    except OSError as exc:
        raise ModelArtifactPolicyError(
            f"Model artifact could not be opened safely: {exc}"
        ) from exc
    try:
        expected_uid = getattr(os, "geteuid", lambda: os.fstat(descriptor).st_uid)()
        digest, _ = sha256_descriptor(
            descriptor,
            expected_uid=expected_uid,
            max_bytes=max_bytes,
        )
        return digest
    finally:
        os.close(descriptor)


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _normalize_registration_source(source: Any) -> str:
    return str(source or "operator").strip()[:160] or "operator"


def normalize_model_display_name(value: Any) -> Optional[str]:
    """Return one bounded human label suitable for trusted model metadata."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ModelArtifactPolicyError("Model display name must be text")
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized:
        return None
    if len(normalized) > MAX_MODEL_DISPLAY_NAME_LENGTH:
        raise ModelArtifactPolicyError(
            f"Model display name must be at most {MAX_MODEL_DISPLAY_NAME_LENGTH} characters"
        )
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise ModelArtifactPolicyError("Model display name contains control characters")
    return normalized


def _registration_action_id(
    *,
    artifact_name: str,
    observed_sha256: str,
    publisher_sha256: Optional[str],
    source: str,
    trust_method: str,
    publisher_digest_evidence_version: Optional[int],
) -> str:
    descriptor = {
        "artifact_name": validate_model_filename(artifact_name),
        "observed_sha256": normalize_sha256(observed_sha256, required=True),
        "publisher_digest_evidence_version": publisher_digest_evidence_version,
        "publisher_sha256": normalize_sha256(publisher_sha256),
        "schema_version": MODEL_REGISTRATION_RECEIPT_SCHEMA_VERSION,
        "source": _normalize_registration_source(source),
        "trust_method": trust_method,
    }
    return "model-registration-v1:" + hashlib.sha256(
        _canonical_json_bytes(descriptor)
    ).hexdigest()


def validate_pt_provenance_record(
    record: Dict[str, Any],
    *,
    artifact_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a PT trust record, including its deterministic evidence receipt."""
    if not isinstance(record, dict) or record.get("trusted") is not True:
        raise ModelArtifactPolicyError("Model has no valid trusted provenance record")
    digest = normalize_sha256(record.get("sha256"), required=True)
    observed = normalize_sha256(record.get("observed_sha256"), required=True)
    if observed != digest:
        raise ModelArtifactPolicyError("Model provenance observed digest is inconsistent")

    trust_method = record.get("trust_method")
    publisher = normalize_sha256(record.get("publisher_sha256"))
    evidence_version = record.get("publisher_digest_evidence_version")
    if trust_method == "expected_sha256":
        if (
            publisher != digest
            or evidence_version != MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION
        ):
            raise ModelArtifactPolicyError(
                "Model publisher-digest evidence is incomplete; re-register required"
            )
    elif trust_method == "operator_assertion":
        if publisher is not None or evidence_version is not None:
            raise ModelArtifactPolicyError(
                "Operator-assertion provenance contains contradictory publisher evidence"
            )
    else:
        raise ModelArtifactPolicyError("Model provenance trust method is invalid")

    receipt = record.get("registration_receipt")
    if not isinstance(receipt, dict):
        raise ModelArtifactPolicyError(
            "Model registration receipt is missing; re-register required"
        )
    receipt_name = validate_model_filename(receipt.get("artifact_name"))
    safe_name = validate_model_filename(artifact_name or receipt_name)
    source = _normalize_registration_source(record.get("source"))
    display_name = normalize_model_display_name(record.get("display_name"))
    if "display_name" in record and display_name != record.get("display_name"):
        raise ModelArtifactPolicyError("Model display name is not canonical")
    recorded_at = record.get("recorded_at")
    if (
        receipt_name != safe_name
        or receipt.get("schema_version") != MODEL_REGISTRATION_RECEIPT_SCHEMA_VERSION
        or receipt.get("observed_sha256") != digest
        or receipt.get("publisher_sha256") != publisher
        or receipt.get("publisher_digest_evidence_version") != evidence_version
        or receipt.get("trust_method") != trust_method
        or receipt.get("source") != source
        or not isinstance(recorded_at, str)
        or not recorded_at
        or receipt.get("recorded_at") != recorded_at
    ):
        raise ModelArtifactPolicyError(
            "Model registration receipt is inconsistent; re-register required"
        )
    expected_action_id = _registration_action_id(
        artifact_name=safe_name,
        observed_sha256=digest,
        publisher_sha256=publisher,
        source=source,
        trust_method=trust_method,
        publisher_digest_evidence_version=evidence_version,
    )
    if receipt.get("action_id") != expected_action_id:
        raise ModelArtifactPolicyError(
            "Model registration receipt action is invalid; re-register required"
        )
    return {
        "artifact_name": safe_name,
        "observed_sha256": digest,
        "publisher_digest_evidence_version": evidence_version,
        "publisher_sha256": publisher,
        "registration_action_id": expected_action_id,
        "display_name": display_name,
        "source": source,
        "trust_method": trust_method,
    }


def _validate_legacy_pt_replacement_record(
    record: Dict[str, Any],
    *,
    artifact_name: str,
    observed_sha256: str,
    publisher_sha256: str,
    size_bytes: int,
) -> Dict[str, Any]:
    """Validate the narrow legacy shape eligible for explicit replacement."""
    safe_name = validate_model_filename(artifact_name)
    observed = normalize_sha256(observed_sha256, required=True)
    publisher = normalize_sha256(publisher_sha256, required=True)
    if publisher != observed:
        raise ModelArtifactPolicyError(
            "Legacy re-registration publisher digest does not match the artifact"
        )
    if not isinstance(record, dict) or record.get("trusted") is not True:
        raise ModelArtifactPolicyError(
            "Only an incomplete trusted legacy record can be re-registered"
        )
    try:
        validate_pt_provenance_record(record, artifact_name=safe_name)
    except ModelArtifactPolicyError:
        pass
    else:
        raise ModelArtifactPolicyError(
            "Existing provenance is complete and is not a legacy replacement"
        )

    recorded_digest = normalize_sha256(record.get("sha256"), required=True)
    if recorded_digest != observed:
        raise ModelArtifactPolicyError(
            "Legacy provenance digest contradicts the observed artifact"
        )
    for field in ("observed_sha256", "publisher_sha256"):
        value = record.get(field)
        if value not in (None, "") and normalize_sha256(value, required=True) != observed:
            raise ModelArtifactPolicyError(
                f"Legacy provenance {field} contradicts the observed artifact"
            )
    recorded_size = record.get("size_bytes")
    if (
        not isinstance(recorded_size, int)
        or isinstance(recorded_size, bool)
        or recorded_size != size_bytes
    ):
        raise ModelArtifactPolicyError(
            "Legacy provenance size contradicts the observed artifact"
        )
    source = record.get("source")
    recorded_at = record.get("recorded_at")
    if (
        not isinstance(source, str)
        or not source
        or _normalize_registration_source(source) != source
        or not isinstance(recorded_at, str)
        or not recorded_at
    ):
        raise ModelArtifactPolicyError(
            "Legacy provenance identity fields are incomplete or invalid"
        )
    trust_method = record.get("trust_method")
    if trust_method not in {None, "expected_sha256", "operator_assertion"}:
        raise ModelArtifactPolicyError(
            "Legacy provenance trust method is contradictory"
        )
    evidence_version = record.get("publisher_digest_evidence_version")
    if evidence_version not in {None, MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION}:
        raise ModelArtifactPolicyError(
            "Legacy provenance publisher evidence version is contradictory"
        )

    receipt = record.get("registration_receipt")
    incomplete = (
        record.get("publisher_sha256") in (None, "")
        or evidence_version is None
        or trust_method != "expected_sha256"
    )
    if receipt is None:
        incomplete = True
    elif not isinstance(receipt, dict):
        raise ModelArtifactPolicyError("Legacy registration receipt is invalid")
    else:
        receipt_name = receipt.get("artifact_name")
        if receipt_name not in (None, safe_name):
            raise ModelArtifactPolicyError(
                "Legacy registration receipt names a different artifact"
            )
        receipt_schema = receipt.get("schema_version")
        if receipt_schema not in (None, MODEL_REGISTRATION_RECEIPT_SCHEMA_VERSION):
            raise ModelArtifactPolicyError(
                "Legacy registration receipt schema is contradictory"
            )
        for field in ("observed_sha256", "publisher_sha256"):
            value = receipt.get(field)
            if value not in (None, "") and normalize_sha256(
                value,
                required=True,
            ) != observed:
                raise ModelArtifactPolicyError(
                    f"Legacy registration receipt {field} is contradictory"
                )
        receipt_source = receipt.get("source")
        if receipt_source not in (None, source):
            raise ModelArtifactPolicyError(
                "Legacy registration receipt source is contradictory"
            )
        receipt_time = receipt.get("recorded_at")
        if receipt_time not in (None, recorded_at):
            raise ModelArtifactPolicyError(
                "Legacy registration receipt timestamp is contradictory"
            )
        receipt_method = receipt.get("trust_method")
        if receipt_method not in {None, "expected_sha256", "operator_assertion"}:
            raise ModelArtifactPolicyError(
                "Legacy registration receipt trust method is contradictory"
            )
        receipt_evidence = receipt.get("publisher_digest_evidence_version")
        if receipt_evidence not in {
            None,
            MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION,
        }:
            raise ModelArtifactPolicyError(
                "Legacy registration receipt publisher evidence is contradictory"
            )
        action_id = receipt.get("action_id")
        if action_id is not None and (
            not isinstance(action_id, str)
            or not action_id.startswith("model-registration-v1:")
        ):
            raise ModelArtifactPolicyError(
                "Legacy registration receipt action is contradictory"
            )
        incomplete = incomplete or any(
            receipt.get(field) in (None, "")
            for field in (
                "action_id",
                "artifact_name",
                "observed_sha256",
                "publisher_sha256",
                "publisher_digest_evidence_version",
                "schema_version",
                "source",
                "trust_method",
            )
        )
    if not incomplete:
        raise ModelArtifactPolicyError(
            "Invalid provenance is not an incomplete legacy publisher record"
        )
    return {
        "artifact_name": safe_name,
        "observed_sha256": observed,
        "publisher_sha256": publisher,
        "size_bytes": size_bytes,
    }


def publisher_digest_provenance_verified(record: Dict[str, Any]) -> bool:
    """Return whether a fully validated record binds an explicit publisher digest."""
    try:
        validated = validate_pt_provenance_record(record)
    except ModelArtifactPolicyError:
        return False
    return bool(
        validated["trust_method"] == "expected_sha256"
        and validated["publisher_sha256"] == validated["observed_sha256"]
        and validated["publisher_digest_evidence_version"]
        == MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION
    )


def _normalize_ncnn_relative_path(parts: Tuple[str, ...]) -> str:
    normalized_parts: List[str] = []
    for part in parts:
        if not isinstance(part, str) or part in {"", ".", ".."}:
            raise ModelArtifactPolicyError(
                "NCNN export contains a non-canonical relative path"
            )
        if "/" in part or "\\" in part or "\x00" in part:
            raise ModelArtifactPolicyError(
                "NCNN export contains a structurally ambiguous path"
            )
        normalized = unicodedata.normalize("NFC", part)
        if normalized != part:
            raise ModelArtifactPolicyError(
                "NCNN export paths must use canonical NFC spelling"
            )
        try:
            normalized.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise ModelArtifactPolicyError(
                "NCNN export contains a path that is not valid UTF-8"
            ) from exc
        normalized_parts.append(normalized)
    relative = "/".join(normalized_parts)
    if len(relative.encode("utf-8")) > DEFAULT_MAX_NCNN_RELATIVE_PATH_BYTES:
        raise ModelArtifactPolicyError("NCNN export relative path is too long")
    return relative


def _directory_content_digest(
    children: List[Dict[str, Any]],
    *,
    directory_path: str,
) -> str:
    """Hash one directory with explicit path, type, and child boundaries."""
    summaries = [
        {
            "entry_type": child["entry_type"],
            "path": child["path"],
            "sha256": child["sha256"],
            "size_bytes": child["size_bytes"],
        }
        for child in sorted(
            children,
            key=lambda item: item["path"].encode("utf-8"),
        )
    ]
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "child_count": len(summaries),
                "children": summaries,
                "digest_domain": NCNN_DIRECTORY_DIGEST_DOMAIN,
                "directory_path": directory_path,
                "schema_version": NCNN_MANIFEST_SCHEMA_VERSION,
            }
        )
    ).hexdigest()


def validate_ncnn_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Validate one canonical NCNN manifest and reject structural aliases."""
    if not isinstance(manifest, dict) or set(manifest) != {
        "digest_domain",
        "entries",
        "hash_algorithm",
        "root",
        "schema_version",
    }:
        raise ModelArtifactPolicyError("NCNN manifest shape is not canonical")
    if manifest.get("schema_version") != NCNN_MANIFEST_SCHEMA_VERSION:
        raise ModelArtifactPolicyError(
            "NCNN provenance uses an unsupported manifest version; re-export required"
        )
    if manifest.get("hash_algorithm") != "sha256":
        raise ModelArtifactPolicyError("NCNN manifest hash algorithm is unsupported")
    if manifest.get("digest_domain") != NCNN_MANIFEST_DIGEST_DOMAIN:
        raise ModelArtifactPolicyError("NCNN manifest digest domain is unsupported")
    entries = manifest.get("entries")
    root = manifest.get("root")
    if not isinstance(entries, list) or not isinstance(root, dict):
        raise ModelArtifactPolicyError("NCNN manifest entries are invalid")
    if len(entries) > DEFAULT_MAX_EXPORT_ENTRIES:
        raise ModelArtifactPolicyError("NCNN manifest exceeds its entry limit")

    expected_order: List[bytes] = []
    by_path: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "entry_type",
            "path",
            "sha256",
            "size_bytes",
        }:
            raise ModelArtifactPolicyError("NCNN manifest entry shape is not canonical")
        entry_type = entry.get("entry_type")
        path = entry.get("path")
        digest = entry.get("sha256")
        size_bytes = entry.get("size_bytes")
        if entry_type not in {"directory", "file"}:
            raise ModelArtifactPolicyError("NCNN manifest entry type is invalid")
        if not isinstance(path, str) or _normalize_ncnn_relative_path(
            tuple(path.split("/"))
        ) != path:
            raise ModelArtifactPolicyError("NCNN manifest path is not normalized")
        if path in by_path:
            raise ModelArtifactPolicyError("NCNN manifest contains a path collision")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise ModelArtifactPolicyError("NCNN manifest byte size is invalid")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise ModelArtifactPolicyError("NCNN manifest content digest is invalid")
        for parent_index in range(1, len(path.split("/"))):
            parent = "/".join(path.split("/")[:parent_index])
            parent_entry = by_path.get(parent)
            if parent_entry is not None and parent_entry["entry_type"] != "directory":
                raise ModelArtifactPolicyError(
                    "NCNN manifest contains a file/directory structural collision"
                )
        by_path[path] = entry
        expected_order.append(path.encode("utf-8"))

    if expected_order != sorted(expected_order):
        raise ModelArtifactPolicyError("NCNN manifest entries are not canonically ordered")
    for path, entry in by_path.items():
        parts = path.split("/")
        if len(parts) > 1:
            parent = "/".join(parts[:-1])
            if by_path.get(parent, {}).get("entry_type") != "directory":
                raise ModelArtifactPolicyError(
                    "NCNN manifest omits a required parent directory"
                )
        if entry["entry_type"] == "file" and any(
            candidate.startswith(f"{path}/") for candidate in by_path
        ):
            raise ModelArtifactPolicyError(
                "NCNN manifest contains a file/directory structural collision"
            )

    for path in sorted(by_path, key=lambda value: value.count("/"), reverse=True):
        entry = by_path[path]
        if entry["entry_type"] != "directory":
            continue
        children = [
            candidate
            for candidate_path, candidate in by_path.items()
            if "/" in candidate_path
            and candidate_path.rsplit("/", 1)[0] == path
        ]
        expected_size = sum(child["size_bytes"] for child in children)
        if entry["size_bytes"] != expected_size:
            raise ModelArtifactPolicyError("NCNN directory byte size is inconsistent")
        if entry["sha256"] != _directory_content_digest(
            children,
            directory_path=path,
        ):
            raise ModelArtifactPolicyError("NCNN directory content digest is inconsistent")

    top_level = [entry for path, entry in by_path.items() if "/" not in path]
    if set(root) != {"entry_type", "path", "sha256", "size_bytes"}:
        raise ModelArtifactPolicyError("NCNN manifest root entry is invalid")
    if root.get("entry_type") != "directory" or root.get("path") != ".":
        raise ModelArtifactPolicyError("NCNN manifest root path is invalid")
    root_size = sum(entry["size_bytes"] for entry in top_level)
    if root.get("size_bytes") != root_size:
        raise ModelArtifactPolicyError("NCNN manifest root byte size is inconsistent")
    if root.get("sha256") != _directory_content_digest(
        top_level,
        directory_path=".",
    ):
        raise ModelArtifactPolicyError("NCNN manifest root digest is inconsistent")
    encoded = _canonical_json_bytes(manifest)
    if len(encoded) > DEFAULT_MAX_NCNN_MANIFEST_BYTES:
        raise ModelArtifactPolicyError("NCNN manifest is oversized")
    return manifest


def ncnn_manifest_sha256(manifest: Dict[str, Any]) -> str:
    validate_ncnn_manifest(manifest)
    return hashlib.sha256(
        NCNN_MANIFEST_DIGEST_DOMAIN.encode("ascii")
        + b"\x00"
        + _canonical_json_bytes(manifest)
    ).hexdigest()


def canonical_ncnn_manifest_descriptor(
    directory_fd: int,
    *,
    expected_uid: int,
    max_files: int = DEFAULT_MAX_EXPORT_FILES,
    max_bytes: int = DEFAULT_MAX_EXPORT_BYTES,
    max_entries: int = DEFAULT_MAX_EXPORT_ENTRIES,
) -> Dict[str, Any]:
    """Build a stable, versioned manifest from one held NCNN directory."""
    file_count = 0
    entry_count = 0
    total_bytes = 0
    has_bin = False
    has_param = False

    def validate_directory(descriptor: int) -> os.stat_result:
        directory_stat = os.fstat(descriptor)
        if not stat.S_ISDIR(directory_stat.st_mode) or directory_stat.st_uid != expected_uid:
            raise ModelArtifactPolicyError("Model export must be an owned directory")
        if stat.S_IMODE(directory_stat.st_mode) & 0o022:
            raise ModelArtifactPolicyError(
                "Model export must not be writable by group or other users"
            )
        return directory_stat

    def walk(descriptor: int, parts: Tuple[str, ...]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        nonlocal entry_count, file_count, total_bytes, has_bin, has_param
        before = validate_directory(descriptor)
        raw_names = os.listdir(descriptor)
        normalized_names: Dict[str, str] = {}
        for raw_name in raw_names:
            normalized = _normalize_ncnn_relative_path((raw_name,))
            if normalized in normalized_names:
                raise ModelArtifactPolicyError(
                    "NCNN export contains a normalized path collision"
                )
            normalized_names[normalized] = raw_name

        direct_children: List[Dict[str, Any]] = []
        descendants: List[Dict[str, Any]] = []
        for normalized_name in sorted(normalized_names, key=lambda value: value.encode("utf-8")):
            raw_name = normalized_names[normalized_name]
            relative_parts = parts + (normalized_name,)
            relative = _normalize_ncnn_relative_path(relative_parts)
            initial = os.stat(raw_name, dir_fd=descriptor, follow_symlinks=False)
            entry_count += 1
            if entry_count > max_entries:
                raise ModelArtifactPolicyError("NCNN export exceeds its entry limit")

            if stat.S_ISDIR(initial.st_mode):
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                )
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                child_fd = os.open(raw_name, flags, dir_fd=descriptor)
                try:
                    _assert_descriptor_matches_stat(
                        child_fd,
                        initial,
                        message="NCNN directory changed while its manifest was built",
                    )
                    child_entry, child_descendants = walk(child_fd, relative_parts)
                finally:
                    os.close(child_fd)
                current = os.stat(raw_name, dir_fd=descriptor, follow_symlinks=False)
                if _stat_identity(current) != _stat_identity(initial):
                    raise ModelArtifactPolicyError(
                        "NCNN directory binding changed while its manifest was built"
                    )
                direct_children.append(child_entry)
                descendants.extend(child_descendants)
                descendants.append(child_entry)
                continue

            if not stat.S_ISREG(initial.st_mode):
                raise ModelArtifactPolicyError(
                    "NCNN export contains a link or special file"
                )
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            file_fd = os.open(raw_name, flags, dir_fd=descriptor)
            try:
                _assert_descriptor_matches_stat(
                    file_fd,
                    initial,
                    message="NCNN file changed before it could be read",
                )
                digest, file_stat = sha256_descriptor(
                    file_fd,
                    expected_uid=expected_uid,
                    max_bytes=max_bytes,
                )
            finally:
                os.close(file_fd)
            current = os.stat(raw_name, dir_fd=descriptor, follow_symlinks=False)
            if _stat_identity(current) != _stat_identity(file_stat):
                raise ModelArtifactPolicyError(
                    "NCNN file binding changed while its manifest was built"
                )
            file_count += 1
            total_bytes += file_stat.st_size
            if file_count > max_files or total_bytes > max_bytes:
                raise ModelArtifactPolicyError(
                    "NCNN export exceeds its file-count or aggregate-byte limit"
                )
            has_bin = has_bin or normalized_name.lower().endswith(".bin")
            has_param = has_param or normalized_name.lower().endswith(".param")
            file_entry = {
                "entry_type": "file",
                "path": relative,
                "sha256": digest,
                "size_bytes": file_stat.st_size,
            }
            direct_children.append(file_entry)
            descendants.append(file_entry)

        after_names = os.listdir(descriptor)
        if sorted(raw_names) != sorted(after_names):
            raise ModelArtifactPolicyError(
                "NCNN directory entries changed while its manifest was built"
            )
        _assert_descriptor_matches_stat(
            descriptor,
            before,
            message="NCNN directory mutated while its manifest was built",
        )
        directory_entry = {
            "entry_type": "directory",
            "path": _normalize_ncnn_relative_path(parts) if parts else ".",
            "sha256": _directory_content_digest(
                direct_children,
                directory_path=(
                    _normalize_ncnn_relative_path(parts) if parts else "."
                ),
            ),
            "size_bytes": sum(child["size_bytes"] for child in direct_children),
        }
        return directory_entry, descendants

    root_entry, entries = walk(directory_fd, ())
    if file_count == 0:
        raise ModelArtifactPolicyError("Model export directory is empty")
    if not has_bin or not has_param:
        raise ModelArtifactPolicyError(
            "NCNN export must contain at least one .bin and one .param file"
        )
    entries.sort(key=lambda item: item["path"].encode("utf-8"))
    manifest = {
        "digest_domain": NCNN_MANIFEST_DIGEST_DOMAIN,
        "entries": entries,
        "hash_algorithm": "sha256",
        "root": root_entry,
        "schema_version": NCNN_MANIFEST_SCHEMA_VERSION,
    }
    validate_ncnn_manifest(manifest)
    return {
        "file_count": file_count,
        "manifest": manifest,
        "manifest_sha256": ncnn_manifest_sha256(manifest),
        "size_bytes": total_bytes,
    }


def sha256_directory_descriptor(
    directory_fd: int,
    *,
    expected_uid: int,
    max_files: int = DEFAULT_MAX_EXPORT_FILES,
    max_bytes: int = DEFAULT_MAX_EXPORT_BYTES,
) -> tuple[str, int, int]:
    """Return the digest and bounds from the canonical NCNN manifest."""
    result = canonical_ncnn_manifest_descriptor(
        directory_fd,
        expected_uid=expected_uid,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    return result["manifest_sha256"], result["file_count"], result["size_bytes"]


def sha256_directory(
    path: Path,
    *,
    max_files: int = DEFAULT_MAX_EXPORT_FILES,
    max_bytes: int = DEFAULT_MAX_EXPORT_BYTES,
) -> str:
    """Hash a bounded export directory without following its final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(Path(path), flags)
    except OSError as exc:
        raise ModelArtifactPolicyError(
            f"Model export could not be opened safely: {exc}"
        ) from exc
    try:
        expected_uid = getattr(os, "geteuid", lambda: os.fstat(descriptor).st_uid)()
        digest, _, _ = sha256_directory_descriptor(
            descriptor,
            expected_uid=expected_uid,
            max_files=max_files,
            max_bytes=max_bytes,
        )
        return digest
    finally:
        os.close(descriptor)


class ModelStoreLease:
    """Cross-thread-safe process lease for one canonical model store."""

    def __init__(
        self,
        models_root: Path,
        *,
        exclusive: bool,
        timeout_seconds: float = 30.0,
        _lock_filename: str = MODEL_STORE_LOCK_FILENAME,
    ) -> None:
        self.models_root = validate_models_root(models_root)
        self.exclusive = bool(exclusive)
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        if _lock_filename not in {
            MODEL_STORE_LOCK_FILENAME,
            MODEL_INGEST_LOCK_FILENAME,
        }:
            raise ValueError("Unsupported model-store lock filename")
        self._lock_filename = _lock_filename
        self._state: Optional[SimpleNamespace] = None
        self._depth = 0
        self._owner_key: Optional[Tuple[int, int, str, str]] = None
        self._state_lock = threading.RLock()

    def __enter__(self) -> "ModelStoreLease":
        with self._state_lock:
            if self._state is not None and not self._state.closed:
                if self._state.owner_thread_id != threading.get_ident():
                    raise ModelStoreBusyError(
                        "An active model-store lease cannot be re-entered by another thread"
                    )
                self._depth += 1
                return self

            owner_key = (
                os.getpid(),
                threading.get_ident(),
                str(self.models_root),
                self._lock_filename,
            )
            with _ACTIVE_LEASES_LOCK:
                active_refs = _ACTIVE_LEASES.get(owner_key, [])
                active_leases = [
                    lease
                    for lease in (reference() for reference in active_refs)
                    if lease is not None
                    and lease._state is not None
                    and not lease._state.closed
                ]
                if active_leases and self.exclusive and all(
                    not lease.exclusive for lease in active_leases
                ):
                    raise ModelStoreBusyError(
                        "Model store is busy with an active shared runtime lease"
                    )
                if any(lease.exclusive for lease in active_leases):
                    raise ModelArtifactPolicyError(
                        "Nested model-store leases must reuse the caller's active "
                        "lease instead of acquiring an independent lock"
                    )
                if active_leases:
                    _ACTIVE_LEASES[owner_key] = [
                        weakref.ref(lease) for lease in active_leases
                    ]
                else:
                    _ACTIVE_LEASES.pop(owner_key, None)

            root_flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            if hasattr(os, "O_NOFOLLOW"):
                root_flags |= os.O_NOFOLLOW
            root_fd = os.open(self.models_root, root_flags)
            lock_fd = -1
            try:
                lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
                if hasattr(os, "O_NOFOLLOW"):
                    lock_flags |= os.O_NOFOLLOW
                lock_fd = os.open(
                    self._lock_filename,
                    lock_flags,
                    0o600,
                    dir_fd=root_fd,
                )
                lock_stat = os.fstat(lock_fd)
                expected_uid = getattr(os, "geteuid", lambda: lock_stat.st_uid)()
                if (
                    not stat.S_ISREG(lock_stat.st_mode)
                    or lock_stat.st_uid != expected_uid
                    or lock_stat.st_nlink != 1
                ):
                    raise ModelArtifactPolicyError("Model-store lock file is unsafe")
                os.fchmod(lock_fd, 0o600)

                operation = fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
                deadline = time.monotonic() + self.timeout_seconds
                while True:
                    try:
                        fcntl.flock(lock_fd, operation | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as exc:
                        if time.monotonic() >= deadline:
                            raise ModelStoreBusyError(
                                "Model store is busy with another runtime or transaction"
                            ) from exc
                        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

                self._state = SimpleNamespace(
                    root_fd=root_fd,
                    lock_fd=lock_fd,
                    expected_uid=expected_uid,
                    exclusive=self.exclusive,
                    owner_thread_id=threading.get_ident(),
                    pinned_fds=set(),
                    loader_aliases={},
                    loader_generation=object(),
                    closed=False,
                )
                self._depth = 1
                self._owner_key = owner_key
                with _ACTIVE_LEASES_LOCK:
                    _ACTIVE_LEASES.setdefault(owner_key, []).append(weakref.ref(self))
                    _LIVE_LEASES.add(self)
                return self
            except BaseException:
                if lock_fd >= 0:
                    os.close(lock_fd)
                os.close(root_fd)
                raise

    @property
    def root_fd(self) -> int:
        if self._state is None or self._state.closed:
            raise RuntimeError("Model-store lease is not active")
        return int(self._state.root_fd)

    @property
    def expected_uid(self) -> int:
        if self._state is None or self._state.closed:
            raise RuntimeError("Model-store lease is not active")
        return int(self._state.expected_uid)

    def open_model(self, filename: str) -> int:
        safe_name = validate_model_filename(filename)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(safe_name, flags, dir_fd=self.root_fd)
        except FileNotFoundError as exc:
            raise ModelArtifactNotFoundError(
                "Trusted model artifact does not exist"
            ) from exc
        except OSError as exc:
            raise ModelArtifactPolicyError(
                f"Model artifact could not be opened safely: {exc}"
            ) from exc

    def open_ncnn_directory(self, name: str) -> int:
        safe_name = validate_ncnn_directory_name(name)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.open(safe_name, flags, dir_fd=self.root_fd)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                f"NCNN export could not be opened safely: {exc}"
            ) from exc

    def _pin_descriptor(self, descriptor: int) -> int:
        with self._state_lock:
            if self._state is None or self._state.closed:
                os.close(descriptor)
                raise RuntimeError("Model-store lease is not active")
            self._state.pinned_fds.add(descriptor)
        return descriptor

    def pin_descriptor_copy(self, descriptor: int) -> int:
        """Retain a close-on-exec duplicate of a caller-owned descriptor."""
        try:
            duplicate = os.dup(descriptor)
            os.set_inheritable(duplicate, False)
        except OSError as exc:
            raise ModelArtifactPolicyError(
                "Model descriptor could not be duplicated safely"
            ) from exc
        return self._pin_descriptor(duplicate)

    def pin_model(self, filename: str) -> int:
        """Open and retain one model descriptor until lease release."""
        return self._pin_descriptor(self.open_model(filename))

    def pin_ncnn_directory(self, name: str) -> int:
        """Open and retain one NCNN directory descriptor until lease release."""
        return self._pin_descriptor(self.open_ncnn_directory(name))

    def loader_binding(
        self,
        descriptor: int,
        artifact_name: str,
        *,
        directory: bool = False,
    ) -> ModelLoaderBinding:
        """Create a private format-correct alias to one pinned procfs descriptor."""
        safe_name = (
            validate_ncnn_directory_name(artifact_name)
            if directory
            else validate_model_filename(artifact_name)
        )
        with self._state_lock:
            state = self._state
            if (
                state is None
                or state.closed
                or descriptor not in state.pinned_fds
            ):
                raise ModelArtifactPolicyError(
                    "Model loader binding requires a descriptor pinned to the active lease"
                )
            descriptor_stat = os.fstat(descriptor)
            expected_type = stat.S_ISDIR if directory else stat.S_ISREG
            if not expected_type(descriptor_stat.st_mode):
                raise ModelArtifactPolicyError(
                    "Model loader binding descriptor has the wrong artifact type"
                )
            descriptor_path = self.descriptor_path(descriptor)
            alias_root = Path(tempfile.mkdtemp(prefix="pixeagle-model-loader-"))
            alias_path = alias_root / safe_name
            try:
                os.chmod(alias_root, 0o700)
                os.symlink(
                    str(descriptor_path),
                    alias_path,
                    target_is_directory=directory,
                )
                binding = ModelLoaderBinding(
                    path=alias_path,
                    artifact_name=safe_name,
                    descriptor=descriptor,
                    directory=directory,
                    _lease_ref=weakref.ref(self),
                    _lease_generation=state.loader_generation,
                )
                state.loader_aliases.setdefault(descriptor, []).append(binding)
                self.assert_loader_binding(binding)
                return binding
            except BaseException:
                bindings = state.loader_aliases.get(descriptor, [])
                state.loader_aliases[descriptor] = [
                    candidate for candidate in bindings if candidate.path != alias_path
                ]
                if not state.loader_aliases[descriptor]:
                    state.loader_aliases.pop(descriptor, None)
                try:
                    os.unlink(alias_path)
                except FileNotFoundError:
                    pass
                try:
                    os.rmdir(alias_root)
                except OSError:
                    pass
                raise

    def assert_loader_binding(self, binding: ModelLoaderBinding) -> Path:
        """Prove that a format alias still resolves to its pinned descriptor."""
        with self._state_lock:
            state = self._state
            if (
                not isinstance(binding, ModelLoaderBinding)
                or binding._lease_ref() is not self
                or state is None
                or state.closed
                or binding._lease_generation is not state.loader_generation
                or binding.descriptor not in state.pinned_fds
                or not any(
                    candidate is binding
                    for candidate in state.loader_aliases.get(binding.descriptor, [])
                )
            ):
                raise ModelArtifactPolicyError(
                    "Model loader binding is not owned by the active lease"
                )
            safe_name = (
                validate_ncnn_directory_name(binding.artifact_name)
                if binding.directory
                else validate_model_filename(binding.artifact_name)
            )
            if binding.path.name != safe_name:
                raise ModelArtifactPolicyError(
                    "Model loader binding lost its format-correct artifact name"
                )
            try:
                root_stat = os.stat(binding.path.parent, follow_symlinks=False)
                alias_stat = os.stat(binding.path, follow_symlinks=False)
                target = os.readlink(binding.path)
                resolved_stat = os.stat(binding.path)
                descriptor_stat = os.fstat(binding.descriptor)
            except OSError as exc:
                raise ModelArtifactPolicyError(
                    "Model loader binding is unavailable or unsafe"
                ) from exc
            if (
                not stat.S_ISDIR(root_stat.st_mode)
                or root_stat.st_uid != state.expected_uid
                or stat.S_IMODE(root_stat.st_mode) != 0o700
                or not stat.S_ISLNK(alias_stat.st_mode)
                or alias_stat.st_uid != state.expected_uid
                or target != f"/proc/self/fd/{binding.descriptor}"
                or _stat_identity(resolved_stat) != _stat_identity(descriptor_stat)
            ):
                raise ModelArtifactPolicyError(
                    "Model loader binding no longer resolves to its pinned descriptor"
                )
            expected_type = stat.S_ISDIR if binding.directory else stat.S_ISREG
            if not expected_type(resolved_stat.st_mode):
                raise ModelArtifactPolicyError(
                    "Model loader binding resolved to the wrong artifact type"
                )
            return binding.path

    @staticmethod
    def _remove_loader_alias(binding: ModelLoaderBinding) -> None:
        try:
            os.unlink(binding.path)
        except OSError:
            pass
        try:
            os.rmdir(binding.path.parent)
        except OSError:
            pass

    def _remove_loader_aliases_locked(
        self,
        state: SimpleNamespace,
        descriptor: Optional[int] = None,
    ) -> None:
        descriptors = (
            (descriptor,)
            if descriptor is not None
            else tuple(state.loader_aliases)
        )
        for current in descriptors:
            for binding in state.loader_aliases.pop(current, []):
                self._remove_loader_alias(binding)

    def release_descriptor(self, descriptor: int) -> None:
        """Release one descriptor previously pinned to this lease."""
        should_close = False
        with self._state_lock:
            if self._state is not None and not self._state.closed:
                should_close = descriptor in self._state.pinned_fds
                self._remove_loader_aliases_locked(self._state, descriptor)
                self._state.pinned_fds.discard(descriptor)
        if should_close:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def descriptor_path(self, descriptor: int) -> Path:
        """Return a procfs path that resolves to the exact pinned descriptor."""
        if (
            self._state is None
            or self._state.closed
            or descriptor not in self._state.pinned_fds
        ):
            raise ModelArtifactPolicyError(
                "Verified model descriptor is not owned by the active lease"
            )
        descriptor_path = Path(f"/proc/self/fd/{descriptor}")
        if os.name != "posix" or not descriptor_path.exists():
            raise ModelArtifactPolicyError(
                "Exact verified model loading requires procfs descriptor paths"
            )
        return descriptor_path

    def assert_descriptor_binding(
        self,
        direct_child_name: str,
        descriptor: int,
        *,
        directory: bool = False,
    ) -> os.stat_result:
        """Prove a canonical store name still refers to the pinned inode."""
        safe_name = (
            validate_ncnn_directory_name(direct_child_name)
            if directory
            else validate_model_filename(direct_child_name)
        )
        descriptor_stat = os.fstat(descriptor)
        try:
            path_stat = os.stat(
                safe_name,
                dir_fd=self.root_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError as exc:
            raise ModelArtifactPolicyError(
                "Verified model artifact lost its canonical store binding"
            ) from exc
        if _stat_identity(path_stat) != _stat_identity(descriptor_stat):
            raise ModelArtifactPolicyError(
                "Verified model artifact changed its canonical store binding"
            )
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected_type(path_stat.st_mode):
            raise ModelArtifactPolicyError(
                "Verified model artifact has the wrong canonical entry type"
            )
        return descriptor_stat

    def bound_path(self, direct_child_name: str) -> Path:
        """Return a path bound to the held root descriptor when procfs is available."""
        name = str(direct_child_name or "")
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ModelArtifactPolicyError("Model-store path must be a direct child")
        proc_root = Path(f"/proc/self/fd/{self.root_fd}")
        if proc_root.exists():
            return proc_root / name
        return self.models_root / name

    def close(self) -> None:
        with self._state_lock:
            state = self._state
            if state is None or state.closed:
                return
            self._depth -= 1
            if self._depth > 0:
                return
            state.closed = True
            try:
                self._remove_loader_aliases_locked(state)
                for descriptor in tuple(state.pinned_fds):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                state.pinned_fds.clear()
                try:
                    fcntl.flock(state.lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            finally:
                for descriptor in (state.lock_fd, state.root_fd):
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
                owner_key = self._owner_key
                if owner_key is not None:
                    with _ACTIVE_LEASES_LOCK:
                        remaining = [
                            reference
                            for reference in _ACTIVE_LEASES.get(owner_key, [])
                            if reference() is not None and reference() is not self
                        ]
                        if remaining:
                            _ACTIVE_LEASES[owner_key] = remaining
                        else:
                            _ACTIVE_LEASES.pop(owner_key, None)
                        _LIVE_LEASES.discard(self)
                self._state = None
                self._depth = 0
                self._owner_key = None

    def _drop_after_fork_child(self) -> None:
        """Close inherited descriptors without unlocking the parent's flock."""
        state = self._state
        if state is not None and not state.closed:
            state.closed = True
            state.loader_aliases.clear()
            for descriptor in tuple(state.pinned_fds):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            state.pinned_fds.clear()
            for descriptor in (state.lock_fd, state.root_fd):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        self._state = None
        self._depth = 0
        self._owner_key = None
        self._state_lock = threading.RLock()

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def __del__(self) -> None:
        """Defensively release a leaked lease without raising during GC."""
        try:
            with self._state_lock:
                if self._state is not None and not self._state.closed:
                    self._depth = 1
            self.close()
        except Exception:
            pass


def _before_model_lease_fork() -> None:
    _ACTIVE_LEASES_LOCK.acquire()


def _after_model_lease_fork_parent() -> None:
    _ACTIVE_LEASES_LOCK.release()


def _after_model_lease_fork_child() -> None:
    try:
        for lease in tuple(_LIVE_LEASES):
            lease._drop_after_fork_child()
        _ACTIVE_LEASES.clear()
        _LIVE_LEASES.clear()
    finally:
        _ACTIVE_LEASES_LOCK.release()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        before=_before_model_lease_fork,
        after_in_parent=_after_model_lease_fork_parent,
        after_in_child=_after_model_lease_fork_child,
    )


class ModelIngestLease(ModelStoreLease):
    """Cross-process admission lease held from multipart parse through commit."""

    def __init__(self, models_root: Path, *, timeout_seconds: float = 0.0) -> None:
        super().__init__(
            models_root,
            exclusive=True,
            timeout_seconds=timeout_seconds,
            _lock_filename=MODEL_INGEST_LOCK_FILENAME,
        )


class ModelProvenanceStore:
    """Owner-only registry proving which local artifacts an operator trusted."""

    def __init__(self, models_root: Path):
        self.models_root = validate_models_root(models_root)
        self.registry_path = self.models_root / MODEL_PROVENANCE_FILENAME

    @staticmethod
    def _empty_registry() -> Dict[str, Any]:
        return {
            "schema_version": MODEL_PROVENANCE_SCHEMA_VERSION,
            "artifacts": {},
        }

    def _load_locked(self, lease: ModelStoreLease) -> Dict[str, Any]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(
                MODEL_PROVENANCE_FILENAME,
                flags,
                dir_fd=lease.root_fd,
            )
        except FileNotFoundError:
            return self._empty_registry()
        except OSError as exc:
            raise ModelRegistryCorruptionError(
                f"Model provenance registry is unreadable: {exc}"
            ) from exc

        try:
            registry_stat = os.fstat(descriptor)
            if (
                not stat.S_ISREG(registry_stat.st_mode)
                or registry_stat.st_uid != lease.expected_uid
                or registry_stat.st_nlink != 1
                or stat.S_IMODE(registry_stat.st_mode) & 0o077
                or registry_stat.st_size > 1024 * 1024
            ):
                raise ModelRegistryCorruptionError(
                    "Model provenance registry permissions or shape are unsafe"
                )
            chunks = []
            remaining = registry_stat.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if remaining != 0:
                raise ModelRegistryCorruptionError(
                    "Model provenance registry changed while it was read"
                )
            payload = json.loads(b"".join(chunks).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ModelRegistryCorruptionError(
                f"Model provenance registry is unreadable: {exc}"
            ) from exc
        finally:
            os.close(descriptor)

        if not isinstance(payload, dict):
            raise ModelRegistryCorruptionError(
                "Model provenance registry must be an object"
            )
        if payload.get("schema_version") != MODEL_PROVENANCE_SCHEMA_VERSION:
            raise ModelRegistryCorruptionError(
                "Unsupported model provenance registry schema version"
            )
        if not isinstance(payload.get("artifacts"), dict):
            raise ModelRegistryCorruptionError(
                "Model provenance registry artifacts must be an object"
            )
        return payload

    def load(self) -> Dict[str, Any]:
        with ModelStoreLease(self.models_root, exclusive=False) as lease:
            return self._load_locked(lease)

    def load_locked(self, lease: ModelStoreLease) -> Dict[str, Any]:
        """Read and validate the registry while the caller holds a store lease."""
        return self._load_locked(lease)

    def _write_locked(self, payload: Dict[str, Any], lease: ModelStoreLease) -> None:
        temporary_name = f".{MODEL_PROVENANCE_FILENAME}.{secrets.token_hex(12)}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
        )
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=lease.root_fd)
        try:
            encoded = (
                json.dumps(payload, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            offset = 0
            while offset < len(encoded):
                offset += os.write(descriptor, encoded[offset:])
            os.fsync(descriptor)
            os.rename(
                temporary_name,
                MODEL_PROVENANCE_FILENAME,
                src_dir_fd=lease.root_fd,
                dst_dir_fd=lease.root_fd,
            )
            os.fsync(lease.root_fd)
        finally:
            os.close(descriptor)
            try:
                os.unlink(temporary_name, dir_fd=lease.root_fd)
            except FileNotFoundError:
                pass

    def _path_name_inside_root(self, path: Path) -> str:
        safe_name = validate_model_filename(Path(path).name)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate != self.models_root / safe_name:
            raise ModelArtifactPolicyError(
                "Model path must use the canonical models-root spelling; "
                "lexical aliases are refused"
            )
        return safe_name

    def _ncnn_path_name_inside_root(self, path: Path) -> str:
        safe_name = validate_ncnn_directory_name(Path(path).name)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate != self.models_root / safe_name:
            raise ModelArtifactPolicyError(
                "NCNN path must use the canonical models-root spelling; "
                "lexical aliases are refused"
            )
        return safe_name

    def _verified_pt_descriptor_locked(
        self,
        path: Path,
        lease: ModelStoreLease,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> tuple[Dict[str, Any], os.stat_result, int]:
        safe_name = self._path_name_inside_root(path)
        payload = self._load_locked(lease)
        record = payload["artifacts"].get(safe_name)
        if not isinstance(record, dict) or record.get("trusted") is not True:
            raise ModelArtifactNotFoundError(
                "Model is not trusted; register its source and digest before loading"
            )
        validated_record = validate_pt_provenance_record(
            record,
            artifact_name=safe_name,
        )
        expected = validated_record["observed_sha256"]
        descriptor = lease.pin_model(safe_name)
        try:
            observed, artifact_stat = sha256_descriptor(
                descriptor,
                expected_uid=lease.expected_uid,
                max_bytes=max_bytes,
            )
            lease.assert_descriptor_binding(safe_name, descriptor)
        except BaseException:
            lease.release_descriptor(descriptor)
            raise
        if observed != expected:
            lease.release_descriptor(descriptor)
            raise ModelArtifactPolicyError(
                "Model digest changed after trust was recorded; execution refused"
            )
        return {
            **record,
            "sha256": observed,
            "size_bytes": artifact_stat.st_size,
        }, artifact_stat, descriptor

    def _verified_pt_locked(
        self,
        path: Path,
        lease: ModelStoreLease,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> tuple[Dict[str, Any], os.stat_result]:
        record, artifact_stat, descriptor = self._verified_pt_descriptor_locked(
            path,
            lease,
            max_bytes=max_bytes,
        )
        try:
            return record, artifact_stat
        finally:
            lease.release_descriptor(descriptor)

    def trust_pt(
        self,
        path: Path,
        *,
        sha256: str,
        source: str,
        expected_digest_verified: bool,
        publisher_sha256: Optional[str] = None,
        operator_observed_sha256: Optional[str] = None,
        display_name: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        with ModelStoreLease(self.models_root, exclusive=True) as lease:
            return self.trust_pt_locked(
                path,
                sha256=sha256,
                source=source,
                expected_digest_verified=expected_digest_verified,
                publisher_sha256=publisher_sha256,
                operator_observed_sha256=operator_observed_sha256,
                display_name=display_name,
                lease=lease,
                max_bytes=max_bytes,
            )

    def trust_pt_locked(
        self,
        path: Path,
        *,
        sha256: str,
        source: str,
        expected_digest_verified: bool,
        lease: ModelStoreLease,
        publisher_sha256: Optional[str] = None,
        operator_observed_sha256: Optional[str] = None,
        display_name: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        if not lease.exclusive:
            raise ModelArtifactPolicyError("Model trust requires an exclusive store lease")
        safe_name = self._path_name_inside_root(path)
        normalized_digest = normalize_sha256(sha256, required=True)
        descriptor = lease.pin_model(safe_name)
        try:
            return self.trust_pt_descriptor_locked(
                path,
                descriptor=descriptor,
                sha256=normalized_digest,
                source=source,
                expected_digest_verified=expected_digest_verified,
                lease=lease,
                publisher_sha256=publisher_sha256,
                operator_observed_sha256=operator_observed_sha256,
                display_name=display_name,
                max_bytes=max_bytes,
            )
        finally:
            lease.release_descriptor(descriptor)

    def trust_pt_descriptor_locked(
        self,
        path: Path,
        *,
        descriptor: int,
        sha256: str,
        source: str,
        expected_digest_verified: bool,
        lease: ModelStoreLease,
        publisher_sha256: Optional[str] = None,
        operator_observed_sha256: Optional[str] = None,
        display_name: Optional[str] = None,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        """Record trust for the exact descriptor already observed by the caller."""
        if not lease.exclusive:
            raise ModelArtifactPolicyError("Model trust requires an exclusive store lease")
        safe_name = self._path_name_inside_root(path)
        normalized_digest = normalize_sha256(sha256, required=True)
        normalized_publisher = normalize_sha256(publisher_sha256)
        if expected_digest_verified and normalized_publisher is None:
            raise ModelArtifactPolicyError(
                "Verified publisher provenance requires the explicitly supplied "
                "publisher SHA-256"
            )
        if not expected_digest_verified and normalized_publisher is not None:
            raise ModelArtifactPolicyError(
                "Publisher digest cannot be recorded as unverified"
            )
        normalized_observed = normalize_sha256(
            operator_observed_sha256 or normalized_digest,
            required=True,
        )
        normalized_display_name = normalize_model_display_name(display_name)
        observed, artifact_stat = sha256_descriptor(
            descriptor,
            expected_uid=lease.expected_uid,
            max_bytes=max_bytes,
        )
        lease.assert_descriptor_binding(safe_name, descriptor)
        if observed != normalized_digest or observed != normalized_observed:
            raise ModelArtifactPolicyError(
                "Model changed before trust provenance could be committed"
            )
        if normalized_publisher is not None and observed != normalized_publisher:
            raise ModelArtifactPolicyError(
                "Observed model digest does not match the publisher digest"
            )
        normalized_source = _normalize_registration_source(source)
        trust_method = (
            "expected_sha256" if expected_digest_verified else "operator_assertion"
        )
        evidence_version = (
            MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION
            if expected_digest_verified
            else None
        )
        action_id = _registration_action_id(
            artifact_name=safe_name,
            observed_sha256=observed,
            publisher_sha256=normalized_publisher,
            source=normalized_source,
            trust_method=trust_method,
            publisher_digest_evidence_version=evidence_version,
        )
        payload = self._load_locked(lease)
        previous = payload["artifacts"].get(safe_name)
        if previous is not None and not isinstance(previous, dict):
            raise ModelRegistryCorruptionError(
                "Model provenance record must be an object"
            )
        if isinstance(previous, dict):
            try:
                previous_evidence = validate_pt_provenance_record(
                    previous,
                    artifact_name=safe_name,
                )
            except ModelArtifactPolicyError:
                _validate_legacy_pt_replacement_record(
                    previous,
                    artifact_name=safe_name,
                    observed_sha256=observed,
                    publisher_sha256=normalized_publisher or "",
                    size_bytes=artifact_stat.st_size,
                )
                previous_evidence = None
            if (
                previous_evidence is not None
                and previous_evidence["registration_action_id"] == action_id
                and previous.get("size_bytes") == artifact_stat.st_size
            ):
                return {**previous, "idempotent_replay": True}

        recorded_at = datetime.now(timezone.utc).isoformat()
        record = {
            "trusted": True,
            "sha256": observed,
            "observed_sha256": observed,
            "publisher_digest_evidence_version": evidence_version,
            "publisher_sha256": normalized_publisher,
            "size_bytes": artifact_stat.st_size,
            "source": normalized_source,
            "trust_method": trust_method,
            "recorded_at": recorded_at,
            "registration_receipt": {
                "action_id": action_id,
                "artifact_name": safe_name,
                "observed_sha256": observed,
                "publisher_digest_evidence_version": evidence_version,
                "publisher_sha256": normalized_publisher,
                "recorded_at": recorded_at,
                "schema_version": MODEL_REGISTRATION_RECEIPT_SCHEMA_VERSION,
                "source": normalized_source,
                "trust_method": trust_method,
            },
        }
        if normalized_display_name is not None:
            record["display_name"] = normalized_display_name
        elif isinstance(previous, dict):
            previous_display_name = normalize_model_display_name(
                previous.get("display_name")
            )
            if previous_display_name is not None:
                record["display_name"] = previous_display_name
        if (
            isinstance(previous, dict)
            and previous_evidence is not None
            and previous.get("sha256") == observed
            and isinstance(previous.get("ncnn"), dict)
        ):
            record["ncnn"] = previous["ncnn"]
        payload["artifacts"][safe_name] = record
        self._write_locked(payload, lease)
        return {**record, "idempotent_replay": False}

    def require_legacy_pt_reregistration_locked(
        self,
        path: Path,
        *,
        observed_sha256: str,
        publisher_sha256: str,
        size_bytes: int,
        lease: ModelStoreLease,
    ) -> Dict[str, Any]:
        """Authorize only a same-artifact incomplete-record replacement."""
        if not lease.exclusive:
            raise ModelArtifactPolicyError(
                "Legacy model re-registration requires an exclusive store lease"
            )
        safe_name = self._path_name_inside_root(path)
        payload = self._load_locked(lease)
        previous = payload["artifacts"].get(safe_name)
        if previous is None:
            raise ModelArtifactNotFoundError(
                "Model has no legacy provenance record to replace"
            )
        return _validate_legacy_pt_replacement_record(
            previous,
            artifact_name=safe_name,
            observed_sha256=observed_sha256,
            publisher_sha256=publisher_sha256,
            size_bytes=size_bytes,
        )

    def find_registration_replay_locked(
        self,
        path: Path,
        *,
        observed_sha256: str,
        source: str,
        publisher_sha256: Optional[str],
        lease: ModelStoreLease,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Optional[Dict[str, Any]]:
        """Return an exact prior registration without executing the checkpoint."""
        safe_name = self._path_name_inside_root(path)
        observed = normalize_sha256(observed_sha256, required=True)
        publisher = normalize_sha256(publisher_sha256)
        record = self.verify_pt_locked(path, lease, max_bytes=max_bytes)
        if record.get("sha256") != observed:
            return None
        trust_method = "expected_sha256" if publisher is not None else "operator_assertion"
        evidence_version = (
            MODEL_PUBLISHER_DIGEST_EVIDENCE_VERSION
            if publisher is not None
            else None
        )
        action_id = _registration_action_id(
            artifact_name=safe_name,
            observed_sha256=observed,
            publisher_sha256=publisher,
            source=_normalize_registration_source(source),
            trust_method=trust_method,
            publisher_digest_evidence_version=evidence_version,
        )
        evidence = validate_pt_provenance_record(record, artifact_name=safe_name)
        if evidence["registration_action_id"] != action_id:
            return None
        return {**record, "idempotent_replay": True}

    def verify_pt(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        with ModelStoreLease(self.models_root, exclusive=False) as lease:
            record, _ = self._verified_pt_locked(
                path,
                lease,
                max_bytes=max_bytes,
            )
            return record

    def verify_pt_locked(
        self,
        path: Path,
        lease: ModelStoreLease,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        record, _ = self._verified_pt_locked(path, lease, max_bytes=max_bytes)
        return record

    def verify_pt_stat_locked(
        self,
        path: Path,
        lease: ModelStoreLease,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> tuple[Dict[str, Any], os.stat_result]:
        return self._verified_pt_locked(path, lease, max_bytes=max_bytes)

    def verify_pt_pinned_locked(
        self,
        path: Path,
        lease: ModelStoreLease,
        *,
        max_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> tuple[Dict[str, Any], os.stat_result, int]:
        """Verify and retain the exact artifact descriptor on the active lease."""
        return self._verified_pt_descriptor_locked(path, lease, max_bytes=max_bytes)

    def trust_ncnn(
        self,
        pt_path: Path,
        ncnn_path: Path,
        *,
        max_source_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        with ModelStoreLease(self.models_root, exclusive=True) as lease:
            return self.trust_ncnn_locked(
                pt_path,
                ncnn_path,
                lease,
                max_source_bytes=max_source_bytes,
            )

    def trust_ncnn_locked(
        self,
        pt_path: Path,
        ncnn_path: Path,
        lease: ModelStoreLease,
        *,
        max_source_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        if not lease.exclusive:
            raise ModelArtifactPolicyError("NCNN trust requires an exclusive store lease")
        pt_record = self.verify_pt_locked(
            pt_path,
            lease,
            max_bytes=max_source_bytes,
        )
        export_name = self._ncnn_path_name_inside_root(ncnn_path)
        expected_name = f"{Path(pt_path).stem}_ncnn_model"
        if export_name != expected_name:
            raise ModelArtifactPolicyError("NCNN export is outside its canonical folder")
        directory_fd = lease.open_ncnn_directory(export_name)
        try:
            manifest_result = canonical_ncnn_manifest_descriptor(
                directory_fd,
                expected_uid=lease.expected_uid,
            )
            lease.assert_descriptor_binding(
                export_name,
                directory_fd,
                directory=True,
            )
        finally:
            os.close(directory_fd)
        recorded_at = datetime.now(timezone.utc).isoformat()
        action_descriptor = {
            "export_name": export_name,
            "manifest_sha256": manifest_result["manifest_sha256"],
            "manifest_schema_version": NCNN_MANIFEST_SCHEMA_VERSION,
            "source_pt_sha256": pt_record["sha256"],
        }
        action_id = "model-ncnn-export-v1:" + hashlib.sha256(
            _canonical_json_bytes(action_descriptor)
        ).hexdigest()
        ncnn_record = {
            "sha256": manifest_result["manifest_sha256"],
            "manifest_sha256": manifest_result["manifest_sha256"],
            "manifest_schema_version": NCNN_MANIFEST_SCHEMA_VERSION,
            "manifest": manifest_result["manifest"],
            "source_pt_sha256": pt_record["sha256"],
            "file_count": manifest_result["file_count"],
            "size_bytes": manifest_result["size_bytes"],
            "recorded_at": recorded_at,
            "export_receipt": {
                "action_id": action_id,
                "export_name": export_name,
                "manifest_sha256": manifest_result["manifest_sha256"],
                "recorded_at": recorded_at,
                "schema_version": 1,
                "source_pt_sha256": pt_record["sha256"],
            },
        }
        payload = self._load_locked(lease)
        current = payload["artifacts"].get(Path(pt_path).name)
        if not isinstance(current, dict) or current.get("sha256") != pt_record.get(
            "sha256"
        ):
            raise ModelArtifactPolicyError(
                "Model provenance changed while NCNN export was being recorded"
            )
        current["ncnn"] = ncnn_record
        self._write_locked(payload, lease)
        return dict(ncnn_record)

    def verify_ncnn(
        self,
        ncnn_path: Path,
        *,
        max_source_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        with ModelStoreLease(self.models_root, exclusive=False) as lease:
            return self.verify_ncnn_locked(
                ncnn_path,
                lease,
                max_source_bytes=max_source_bytes,
            )

    def verify_ncnn_locked(
        self,
        ncnn_path: Path,
        lease: ModelStoreLease,
        *,
        max_source_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> Dict[str, Any]:
        record, descriptor = self.verify_ncnn_pinned_locked(
            ncnn_path,
            lease,
            max_source_bytes=max_source_bytes,
        )
        try:
            return record
        finally:
            lease.release_descriptor(descriptor)

    def verify_ncnn_pinned_locked(
        self,
        ncnn_path: Path,
        lease: ModelStoreLease,
        *,
        max_source_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> tuple[Dict[str, Any], int]:
        """Verify and retain the exact NCNN directory descriptor on a lease."""
        export_name = self._ncnn_path_name_inside_root(ncnn_path)
        pt_name = f"{export_name[:-len('_ncnn_model')]}.pt"
        pt_path = self.models_root / pt_name
        pt_record = self.verify_pt_locked(
            pt_path,
            lease,
            max_bytes=max_source_bytes,
        )
        ncnn_record = pt_record.get("ncnn")
        if not isinstance(ncnn_record, dict):
            raise ModelArtifactPolicyError("NCNN export has no trusted provenance")
        if ncnn_record.get("source_pt_sha256") != pt_record.get("sha256"):
            raise ModelArtifactPolicyError("NCNN export provenance is stale")
        if ncnn_record.get("manifest_schema_version") != NCNN_MANIFEST_SCHEMA_VERSION:
            raise ModelArtifactPolicyError(
                "NCNN provenance uses an unsupported manifest version; re-export required"
            )
        recorded_manifest = ncnn_record.get("manifest")
        if not isinstance(recorded_manifest, dict):
            raise ModelArtifactPolicyError(
                "NCNN provenance has no canonical manifest; re-export required"
            )
        recorded_manifest_digest = ncnn_manifest_sha256(recorded_manifest)
        if recorded_manifest_digest != normalize_sha256(
            ncnn_record.get("manifest_sha256"),
            required=True,
        ):
            raise ModelArtifactPolicyError("NCNN provenance manifest digest is invalid")

        directory_fd = lease.pin_ncnn_directory(export_name)
        try:
            observed = canonical_ncnn_manifest_descriptor(
                directory_fd,
                expected_uid=lease.expected_uid,
            )
            lease.assert_descriptor_binding(
                export_name,
                directory_fd,
                directory=True,
            )
            expected_digest = normalize_sha256(ncnn_record.get("sha256"), required=True)
            if observed["manifest_sha256"] != expected_digest:
                raise ModelArtifactPolicyError(
                    "NCNN export manifest digest changed; execution refused"
                )
            if observed["manifest"] != recorded_manifest:
                raise ModelArtifactPolicyError(
                    "NCNN export manifest changed; execution refused"
                )
            if ncnn_record.get("file_count") != observed["file_count"]:
                raise ModelArtifactPolicyError("NCNN export file count changed")
            if ncnn_record.get("size_bytes") != observed["size_bytes"]:
                raise ModelArtifactPolicyError("NCNN export size changed")
            return {
                **ncnn_record,
                "sha256": observed["manifest_sha256"],
                "file_count": observed["file_count"],
                "size_bytes": observed["size_bytes"],
                "trust_method": pt_record.get("trust_method"),
                "observed_sha256": pt_record.get("observed_sha256"),
                "publisher_sha256": pt_record.get("publisher_sha256"),
                "registration_receipt": pt_record.get("registration_receipt"),
            }, directory_fd
        except BaseException:
            lease.release_descriptor(directory_fd)
            raise

    def remove(self, model_filename: str) -> None:
        with ModelStoreLease(self.models_root, exclusive=True) as lease:
            self.remove_locked(model_filename, lease)

    def remove_locked(self, model_filename: str, lease: ModelStoreLease) -> None:
        if not lease.exclusive:
            raise ModelArtifactPolicyError(
                "Model provenance removal requires an exclusive store lease"
            )
        safe_name = validate_model_filename(model_filename)
        payload = self._load_locked(lease)
        if payload["artifacts"].pop(safe_name, None) is not None:
            self._write_locked(payload, lease)
