"""Owner-only atomic file primitives for external authentication records."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, TypeVar


MAX_AUTH_RECORD_FILE_BYTES = 1024 * 1024

ErrorT = TypeVar("ErrorT", bound=Exception)


def read_owner_only_bytes(
    path: Path,
    *,
    label: str,
    error_type: type[ErrorT],
    max_bytes: int = MAX_AUTH_RECORD_FILE_BYTES,
) -> bytes:
    """Read one regular, owner-only record file without following links."""
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    if no_follow:
        flags |= no_follow
    else:
        try:
            if path.is_symlink():
                raise error_type(f"{label} must not be a symbolic link: {path}")
        except OSError as exc:
            raise error_type(f"{label} could not be inspected safely: {path}") from exc

    try:
        descriptor = os.open(path, flags)
        file_status = os.fstat(descriptor)
        validate_open_file_status(
            file_status,
            path,
            label=label,
            error_type=error_type,
            max_bytes=max_bytes,
        )
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise error_type(f"{label} exceeds the {max_bytes} byte limit: {path}")
        return raw
    except FileNotFoundError:
        raise
    except error_type:
        raise
    except OSError as exc:
        raise error_type(f"{label} could not be read safely: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def validate_open_file_status(
    file_status: os.stat_result,
    path: Path,
    *,
    label: str,
    error_type: type[ErrorT],
    max_bytes: int = MAX_AUTH_RECORD_FILE_BYTES,
) -> None:
    if not stat.S_ISREG(file_status.st_mode):
        raise error_type(f"{label} must be a regular file: {path}")
    if file_status.st_nlink != 1:
        raise error_type(f"{label} must not have multiple hard links: {path}")
    if os.name == "posix":
        if file_status.st_uid != os.geteuid():
            raise error_type(f"{label} must be owned by the PixEagle process user: {path}")
        permissions = stat.S_IMODE(file_status.st_mode)
        if not permissions & stat.S_IRUSR or permissions & 0o077:
            raise error_type(
                f"{label} must be owner-readable and inaccessible to group/other users: {path}"
            )
    if file_status.st_size > max_bytes:
        raise error_type(f"{label} exceeds the {max_bytes} byte limit: {path}")


def ensure_owner_only_parent(
    parent: Path,
    *,
    label: str,
    error_type: type[ErrorT],
) -> None:
    try:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_status = os.lstat(parent)
    except OSError as exc:
        raise error_type(f"{label} directory could not be prepared safely: {parent}") from exc
    if stat.S_ISLNK(parent_status.st_mode) or not stat.S_ISDIR(parent_status.st_mode):
        raise error_type(f"{label} parent must be a real directory: {parent}")
    if os.name == "posix":
        if parent_status.st_uid != os.geteuid():
            raise error_type(
                f"{label} directory must be owned by the PixEagle process user: {parent}"
            )
        if stat.S_IMODE(parent_status.st_mode) & 0o022:
            raise error_type(
                f"{label} directory must not be writable by group or other users: {parent}"
            )


def atomic_replace_owner_only_bytes(
    path: Path,
    payload: bytes,
    *,
    label: str,
    error_type: type[ErrorT],
    require_missing: bool = False,
    max_bytes: int = MAX_AUTH_RECORD_FILE_BYTES,
    fsync_directory_fn: Callable[[Path], None] | None = None,
) -> None:
    """Atomically publish bytes as an owner-only regular file."""
    if len(payload) > max_bytes:
        raise error_type(f"{label} payload exceeds the {max_bytes} byte limit")

    parent = path.parent
    ensure_owner_only_parent(parent, label=label, error_type=error_type)
    if require_missing:
        try:
            os.lstat(path)
        except FileNotFoundError:
            pass
        else:
            raise error_type(f"Refusing to replace existing {label} backup: {path}")

    temp_path: Path | None = None
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
        (fsync_directory_fn or fsync_directory)(parent)
        if os.name == "posix" and stat.S_IMODE(os.lstat(path).st_mode) != 0o600:
            raise error_type(f"Committed {label} is not owner-only 0600: {path}")
    except error_type:
        raise
    except OSError as exc:
        raise error_type(f"Failed to atomically write {label}: {path}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def next_backup_path(path: Path) -> Path:
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = path.with_name(f"{path.name}.backup.{stamp}")
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = path.with_name(f"{path.name}.backup.{stamp}.{suffix}")
    return candidate


__all__ = [
    "MAX_AUTH_RECORD_FILE_BYTES",
    "atomic_replace_owner_only_bytes",
    "ensure_owner_only_parent",
    "fsync_directory",
    "next_backup_path",
    "read_owner_only_bytes",
    "validate_open_file_status",
]
