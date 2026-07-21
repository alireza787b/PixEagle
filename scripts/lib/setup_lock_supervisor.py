#!/usr/bin/env python3
"""Supervise commands under secure, non-inheritable resource locks."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import secrets
import signal
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


LEASE_VERSION = 2
LEASE_MODE = 0o600
LOCK_MODE = 0o600
LOCK_DIRECTORY_MODE = 0o700
LOCK_ROOT = Path("/var/tmp")
LOCK_DIRECTORY_PREFIX = "pixeagle-locks-"
LOCK_FILE_PREFIX = "setup-"
LIFECYCLE_RESOURCE_SUFFIX = "/scripts/lib/runtime_ownership.sh"
TOKEN_BYTES = 32
TERM_GRACE_SECONDS = 5.0
KILL_GRACE_SECONDS = 2.0
MAX_LEASE_BYTES = 64 * 1024
MAX_LEASE_FILES = 1024

RESOURCE_CONTEXT_NAMES = (
    "PIXEAGLE_RESOURCE_LOCK_MODE",
    "PIXEAGLE_RESOURCE_LOCK_SET",
    "PIXEAGLE_RESOURCE_LOCK_STATE_PATH",
    "PIXEAGLE_RESOURCE_LOCK_TOKEN",
    "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID",
    "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN",
    "PIXEAGLE_RESOURCE_LOCK_SESSION_ID",
    "PIXEAGLE_ENVIRONMENT_LOCK_MODE",
    "PIXEAGLE_ENVIRONMENT_LOCK_PATH",
    "PIXEAGLE_ENVIRONMENT_LOCK_PATHS",
    "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID",
    "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN",
    "PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID",
    "PIXEAGLE_SETUP_LOCK_PATH",
    "PIXEAGLE_SETUP_LOCK_STATE_PATH",
    "PIXEAGLE_SETUP_LOCK_TOKEN",
    "PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID",
    "PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN",
    "PIXEAGLE_SETUP_LOCK_SESSION_ID",
)


class LockError(RuntimeError):
    """Raised when the lock or supervised process contract is unsafe."""


@dataclass(frozen=True)
class ResourceLock:
    """A canonical resource and its deployment-owner lock identity."""

    resource_path: str | None
    lock_path: Path
    owner_uid: int

    def payload(self) -> dict[str, object]:
        return {
            "resource_path": self.resource_path,
            "lock_path": str(self.lock_path),
            "owner_uid": self.owner_uid,
        }


def _acquisition_key(resource: ResourceLock) -> tuple[int, str]:
    """Keep lifecycle serialization ahead of resources acquired during startup."""
    is_lifecycle = bool(
        resource.resource_path
        and resource.resource_path.endswith(LIFECYCLE_RESOURCE_SUFFIX)
    )
    return (0 if is_lifecycle else 1, str(resource.lock_path))


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


def _close_quietly(descriptor: int | None) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        pass


def _process_start_token(pid: int) -> str:
    try:
        line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        token = line.rsplit(") ", 1)[1].split()[19]
    except (IndexError, OSError, ValueError) as exc:
        raise LockError(f"cannot read process identity for PID {pid}") from exc
    if not token.isdecimal():
        raise LockError(f"invalid process identity for PID {pid}")
    return token


def _authorize(owner_uid: int) -> None:
    caller_uid = os.geteuid()
    if caller_uid not in (0, owner_uid):
        raise LockError(
            f"caller UID {caller_uid} is neither root nor deployment owner UID {owner_uid}"
        )


def _canonical_resource_path(raw_path: str) -> str:
    if not raw_path or not os.path.isabs(raw_path):
        raise LockError(f"resource path must be absolute: {raw_path!r}")
    try:
        canonical = os.path.realpath(raw_path, strict=False)
    except (OSError, ValueError) as exc:
        raise LockError(f"cannot canonicalize resource path {raw_path}: {exc}") from exc
    canonical = os.path.normpath(canonical)
    if not os.path.isabs(canonical):
        raise LockError(f"resource path did not resolve absolutely: {raw_path}")
    return canonical


def _deployment_owner(canonical_path: str) -> int:
    candidate = canonical_path
    while True:
        try:
            return os.stat(candidate, follow_symlinks=True).st_uid
        except (FileNotFoundError, NotADirectoryError):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                raise LockError(
                    f"cannot find an existing owner anchor for resource {canonical_path}"
                )
            candidate = parent
        except OSError as exc:
            raise LockError(f"cannot derive deployment owner for {canonical_path}: {exc}") from exc


def _lock_directory(owner_uid: int) -> Path:
    return LOCK_ROOT / f"{LOCK_DIRECTORY_PREFIX}{owner_uid}"


def _resolve_resource(raw_path: str) -> ResourceLock:
    canonical = _canonical_resource_path(raw_path)
    owner_uid = _deployment_owner(canonical)
    _authorize(owner_uid)
    digest = hashlib.sha256(canonical.encode("utf-8", "surrogateescape")).hexdigest()
    lock_path = _lock_directory(owner_uid) / f"{LOCK_FILE_PREFIX}{digest}.lock"
    return ResourceLock(canonical, lock_path, owner_uid)


def _parse_lock_path(raw_path: str) -> ResourceLock:
    if not raw_path or not os.path.isabs(raw_path):
        raise LockError(f"lock path must be absolute: {raw_path!r}")
    path = Path(os.path.normpath(raw_path))
    directory = path.parent
    if directory.parent != LOCK_ROOT or not directory.name.startswith(LOCK_DIRECTORY_PREFIX):
        raise LockError(f"lock path is outside the stable PixEagle lock root: {path}")
    owner_text = directory.name.removeprefix(LOCK_DIRECTORY_PREFIX)
    if not owner_text.isdecimal():
        raise LockError(f"lock directory has no deployment owner identity: {directory}")
    suffix = path.name.removeprefix(LOCK_FILE_PREFIX).removesuffix(".lock")
    if (
        not path.name.startswith(LOCK_FILE_PREFIX)
        or not path.name.endswith(".lock")
        or len(suffix) != hashlib.sha256().digest_size * 2
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise LockError(f"lock path does not contain a full SHA-256 identity: {path}")
    owner_uid = int(owner_text)
    _authorize(owner_uid)
    return ResourceLock(None, path, owner_uid)


def _verify_lock_root() -> tuple[int, os.stat_result]:
    try:
        before = LOCK_ROOT.lstat()
    except OSError as exc:
        raise LockError(f"cannot inspect stable lock root {LOCK_ROOT}: {exc}") from exc
    mode = stat.S_IMODE(before.st_mode)
    if (
        not stat.S_ISDIR(before.st_mode)
        or LOCK_ROOT.is_symlink()
        or before.st_uid != 0
        or (mode & 0o022 and not mode & stat.S_ISVTX)
    ):
        raise LockError(f"refusing unsafe stable lock root: {LOCK_ROOT}")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(LOCK_ROOT, flags)
    except OSError as exc:
        raise LockError(f"cannot open stable lock root {LOCK_ROOT}: {exc}") from exc
    after = os.fstat(descriptor)
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        os.close(descriptor)
        raise LockError(f"stable lock root changed while opening: {LOCK_ROOT}")
    return descriptor, after


def _entry_stat(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise LockError(f"cannot inspect lock entry {name}: {exc}") from exc


def _validate_directory_metadata(
    metadata: os.stat_result, owner_uid: int, path: Path
) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != owner_uid
        or stat.S_IMODE(metadata.st_mode) != LOCK_DIRECTORY_MODE
    ):
        raise LockError(f"refusing unsafe owner-controlled lock directory: {path}")


def _open_owner_directory(owner_uid: int, *, create: bool) -> tuple[int, Path]:
    _authorize(owner_uid)
    root_fd, _root_metadata = _verify_lock_root()
    directory = _lock_directory(owner_uid)
    name = directory.name
    created = False
    try:
        before = _entry_stat(root_fd, name)
        if before is None:
            if not create:
                raise LockError(f"owner-controlled lock directory does not exist: {directory}")
            try:
                os.mkdir(name, LOCK_DIRECTORY_MODE, dir_fd=root_fd)
                created = True
            except FileExistsError:
                before = _entry_stat(root_fd, name)
            except OSError as exc:
                raise LockError(f"cannot create owner-controlled lock directory {directory}: {exc}") from exc

        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            directory_fd = os.open(name, flags, dir_fd=root_fd)
        except OSError as exc:
            raise LockError(f"cannot open owner-controlled lock directory {directory}: {exc}") from exc
        try:
            if created:
                if os.geteuid() == 0 and owner_uid != 0:
                    os.fchown(directory_fd, owner_uid, -1)
                os.fchmod(directory_fd, LOCK_DIRECTORY_MODE)
            opened = os.fstat(directory_fd)
            current = _entry_stat(root_fd, name)
            if current is None or (opened.st_dev, opened.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise LockError(f"owner-controlled lock directory changed while opening: {directory}")
            if before is not None and (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise LockError(f"owner-controlled lock directory was replaced: {directory}")
            _validate_directory_metadata(opened, owner_uid, directory)
            os.set_inheritable(directory_fd, False)
            return directory_fd, directory
        except Exception:
            os.close(directory_fd)
            raise
    finally:
        os.close(root_fd)


def _validate_regular_metadata(
    metadata: os.stat_result,
    *,
    owner_uid: int,
    expected_mode: int,
    path: Path,
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise LockError(f"refusing non-regular lock data path: {path}")
    if metadata.st_uid != owner_uid:
        raise LockError(f"refusing lock data path with unexpected owner: {path}")
    if metadata.st_nlink != 1:
        raise LockError(f"refusing hard-linked lock data path: {path}")
    if stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise LockError(f"refusing lock data path with mode other than {expected_mode:04o}: {path}")


def _open_lock(resource: ResourceLock, *, create: bool) -> int:
    directory_fd, directory = _open_owner_directory(resource.owner_uid, create=create)
    if resource.lock_path.parent != directory:
        os.close(directory_fd)
        raise LockError(f"lock path does not match its deployment owner: {resource.lock_path}")
    name = resource.lock_path.name
    descriptor: int | None = None
    try:
        before = _entry_stat(directory_fd, name)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        created = False
        if before is None:
            if not create:
                raise LockError(f"expected resource lock does not exist: {resource.lock_path}")
            try:
                descriptor = os.open(
                    name,
                    flags | os.O_CREAT | os.O_EXCL,
                    LOCK_MODE,
                    dir_fd=directory_fd,
                )
                created = True
            except FileExistsError:
                before = _entry_stat(directory_fd, name)
        if descriptor is None:
            try:
                descriptor = os.open(name, flags, dir_fd=directory_fd)
            except OSError as exc:
                raise LockError(f"cannot open resource lock {resource.lock_path}: {exc}") from exc

        if created:
            if os.geteuid() == 0 and resource.owner_uid != 0:
                os.fchown(descriptor, resource.owner_uid, -1)
            os.fchmod(descriptor, LOCK_MODE)
        opened = os.fstat(descriptor)
        current = _entry_stat(directory_fd, name)
        if current is None or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ):
            raise LockError(f"resource lock changed while opening: {resource.lock_path}")
        if before is not None and (before.st_dev, before.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise LockError(f"resource lock was replaced while opening: {resource.lock_path}")
        _validate_regular_metadata(
            opened,
            owner_uid=resource.owner_uid,
            expected_mode=LOCK_MODE,
            path=resource.lock_path,
        )
        os.set_inheritable(descriptor, False)
        return descriptor
    except Exception:
        _close_quietly(descriptor)
        raise
    finally:
        os.close(directory_fd)


def _state_path(resources: list[ResourceLock]) -> Path:
    return Path(f"{resources[0].lock_path}.state")


def _validate_state_path(path: Path, resource: ResourceLock) -> None:
    if path != Path(f"{resource.lock_path}.state"):
        raise LockError("exclusive lease path must belong to the first sorted resource lock")


def _atomic_write_lease(
    path: Path, payload: dict[str, object], resource: ResourceLock
) -> None:
    _validate_state_path(path, resource)
    directory_fd, directory = _open_owner_directory(resource.owner_uid, create=False)
    name = path.name
    temporary_name = f".{name}.{secrets.token_hex(16)}.tmp"
    temporary_fd: int | None = None
    try:
        existing = _entry_stat(directory_fd, name)
        if existing is not None:
            _validate_regular_metadata(
                existing,
                owner_uid=resource.owner_uid,
                expected_mode=LEASE_MODE,
                path=path,
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            temporary_fd = os.open(
                temporary_name, flags, LEASE_MODE, dir_fd=directory_fd
            )
        except OSError as exc:
            raise LockError(f"cannot create temporary setup lease in {directory}: {exc}") from exc
        if os.geteuid() == 0 and resource.owner_uid != 0:
            os.fchown(temporary_fd, resource.owner_uid, -1)
        os.fchmod(temporary_fd, LEASE_MODE)
        encoded = (
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        if len(encoded) > MAX_LEASE_BYTES:
            raise LockError("exclusive resource lease is unexpectedly large")
        offset = 0
        while offset < len(encoded):
            offset += os.write(temporary_fd, encoded[offset:])
        os.fsync(temporary_fd)
        written = os.fstat(temporary_fd)
        _validate_regular_metadata(
            written,
            owner_uid=resource.owner_uid,
            expected_mode=LEASE_MODE,
            path=path,
        )
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        current = _entry_stat(directory_fd, name)
        if current is None or (current.st_dev, current.st_ino) != (
            written.st_dev,
            written.st_ino,
        ):
            raise LockError(f"setup lease changed while publishing: {path}")
        os.fsync(directory_fd)
    finally:
        _close_quietly(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        os.close(directory_fd)


def _read_lease(
    path: Path, resource: ResourceLock
) -> tuple[dict[str, object], FileIdentity]:
    _validate_state_path(path, resource)
    directory_fd, _directory = _open_owner_directory(resource.owner_uid, create=False)
    descriptor: int | None = None
    try:
        before = _entry_stat(directory_fd, path.name)
        if before is None:
            raise LockError(f"exclusive resource lease does not exist: {path}")
        _validate_regular_metadata(
            before,
            owner_uid=resource.owner_uid,
            expected_mode=LEASE_MODE,
            path=path,
        )
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = os.open(path.name, flags, dir_fd=directory_fd)
        except OSError as exc:
            raise LockError(f"cannot open exclusive resource lease {path}: {exc}") from exc
        opened = os.fstat(descriptor)
        current = _entry_stat(directory_fd, path.name)
        if current is None or (opened.st_dev, opened.st_ino) != (
            current.st_dev,
            current.st_ino,
        ) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise LockError(f"exclusive resource lease changed while opening: {path}")
        _validate_regular_metadata(
            opened,
            owner_uid=resource.owner_uid,
            expected_mode=LEASE_MODE,
            path=path,
        )
        if opened.st_size > MAX_LEASE_BYTES:
            raise LockError(f"exclusive resource lease is too large: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as stream:
            try:
                payload = json.load(stream)
            except (UnicodeError, ValueError, TypeError) as exc:
                raise LockError(f"cannot parse exclusive resource lease {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise LockError("exclusive resource lease must contain a JSON object")
        return payload, FileIdentity(opened.st_dev, opened.st_ino)
    finally:
        _close_quietly(descriptor)
        os.close(directory_fd)


def _remove_matching_lease(path: Path, token: str, resource: ResourceLock) -> None:
    try:
        payload, identity = _read_lease(path, resource)
        if payload.get("token") != token:
            return
        directory_fd, _directory = _open_owner_directory(resource.owner_uid, create=False)
        try:
            current = _entry_stat(directory_fd, path.name)
            if current is None or (current.st_dev, current.st_ino) != (
                identity.device,
                identity.inode,
            ):
                return
            os.unlink(path.name, dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except LockError:
        return


def _verified_active_exclusive_lease(
    state_path: Path,
    state_resource: ResourceLock,
    requested_resource: ResourceLock,
) -> dict[str, object] | None:
    try:
        payload, _identity = _read_lease(state_path, state_resource)
        if payload.get("version") != LEASE_VERSION or payload.get("mode") != "exclusive":
            raise LockError("exclusive resource lease has an unsupported contract")
        resource_set = payload.get("resource_set")
        resources = _parse_context_resource_set(
            json.dumps(resource_set, sort_keys=True, separators=(",", ":"))
        )
        expected_paths = [str(item.lock_path) for item in resources]
        if payload.get("lock_paths") != expected_paths:
            raise LockError("exclusive resource lease lock set is inconsistent")
        if payload.get("state_path") != str(_state_path(resources)):
            raise LockError("exclusive resource lease state path is inconsistent")
        if str(requested_resource.lock_path) not in expected_paths:
            raise LockError("exclusive resource lease does not cover the blocked resource")

        supervisor_pid = payload.get("supervisor_pid")
        start_token = payload.get("supervisor_start_token")
        if not isinstance(supervisor_pid, int) or not isinstance(start_token, str):
            raise LockError("exclusive resource lease has no process identity")
        if _process_start_token(supervisor_pid) != start_token:
            raise LockError("exclusive resource lease supervisor identity changed")
        _verify_supervisor_flocks(resources, supervisor_pid, "exclusive")
        return payload
    except LockError:
        return None


def _active_exclusive_lease(resource: ResourceLock) -> dict[str, object] | None:
    """Return a verified active lease that covers the requested resource."""
    direct_state = Path(f"{resource.lock_path}.state")
    direct = _verified_active_exclusive_lease(direct_state, resource, resource)
    if direct is not None:
        return direct

    directory_fd, directory = _open_owner_directory(resource.owner_uid, create=False)
    try:
        names = sorted(
            name
            for name in os.listdir(directory_fd)
            if name.startswith(LOCK_FILE_PREFIX) and name.endswith(".lock.state")
        )
    except OSError as exc:
        raise LockError(f"cannot inspect active setup leases in {directory}: {exc}") from exc
    finally:
        os.close(directory_fd)

    if len(names) > MAX_LEASE_FILES:
        raise LockError(
            f"too many setup lease files in owner-controlled directory {directory}"
        )
    for name in names:
        state_path = directory / name
        if state_path == direct_state:
            continue
        try:
            state_resource = _parse_lock_path(directory / name.removesuffix(".state"))
        except LockError:
            continue
        lease = _verified_active_exclusive_lease(
            state_path,
            state_resource,
            resource,
        )
        if lease is not None:
            return lease
    return None


def _lease_timeout_detail(resource: ResourceLock) -> str:
    payload = _active_exclusive_lease(resource)
    if payload is None:
        return ""
    operation = payload.get("operation")
    if not isinstance(operation, str) or not operation.strip():
        operation = "exclusive setup operation"
    operation = " ".join(operation.split())[:160]
    supervisor_pid = payload["supervisor_pid"]
    started_at = payload.get("started_at_utc")
    started_detail = (
        f", started {started_at}"
        if isinstance(started_at, str) and started_at
        else ""
    )
    return (
        f"; active operation {operation!r} is owned by supervisor PID "
        f"{supervisor_pid}{started_detail}. It may still be running after an SSH "
        "disconnect; do not delete lock files or start another setup"
    )


def _resolve_specs(
    resource_paths: list[str], lock_paths: list[str]
) -> list[ResourceLock]:
    if bool(resource_paths) == bool(lock_paths):
        raise LockError("provide resource paths or compatibility lock paths, but not both")
    candidates = (
        [_resolve_resource(path) for path in resource_paths]
        if resource_paths
        else [_parse_lock_path(path) for path in lock_paths]
    )
    by_lock_path: dict[str, ResourceLock] = {}
    for candidate in candidates:
        key = str(candidate.lock_path)
        previous = by_lock_path.get(key)
        if previous is not None and previous != candidate:
            raise LockError(f"conflicting resources map to one lock path: {key}")
        by_lock_path[key] = candidate
    if not by_lock_path:
        raise LockError("at least one resource lock is required")
    return sorted(by_lock_path.values(), key=_acquisition_key)


def _acquire_all(
    descriptors: list[tuple[ResourceLock, int]], mode: str, timeout: int
) -> list[int]:
    operation = fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH
    deadline = time.monotonic() + timeout
    held: list[int] = []
    for resource, descriptor in descriptors:
        while True:
            try:
                fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
                metadata = os.fstat(descriptor)
                _validate_regular_metadata(
                    metadata,
                    owner_uid=resource.owner_uid,
                    expected_mode=LOCK_MODE,
                    path=resource.lock_path,
                )
                held.append(descriptor)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockError(
                        f"timed out waiting for resource lock {resource.lock_path}"
                        f"{_lease_timeout_detail(resource)}"
                    )
                time.sleep(0.05)
    return held


def _set_subreaper() -> None:
    if not sys.platform.startswith("linux"):
        raise LockError("resource lock supervision requires Linux process semantics")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise LockError(
            f"prctl(PR_SET_CHILD_SUBREAPER) failed: {os.strerror(ctypes.get_errno())}"
        )


def _set_parent_death_signal(parent_pid: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG) failed")
    if os.getppid() != parent_pid:
        raise OSError("resource lock supervisor exited before child startup")


def _children_of(pid: int) -> list[int]:
    try:
        content = Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError):
        return []
    except OSError as exc:
        raise LockError(f"cannot inspect descendants of PID {pid}") from exc
    children: list[int] = []
    for value in content.split():
        if value.isdecimal():
            children.append(int(value))
    return children


def _descendants() -> set[int]:
    found: set[int] = set()
    pending = _children_of(os.getpid())
    while pending:
        pid = pending.pop()
        if pid in found:
            continue
        found.add(pid)
        pending.extend(_children_of(pid))
    return found


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise LockError(f"cannot inspect supervised process group {process_group}") from exc


def _signal_process(pid: int, signum: int) -> None:
    try:
        os.kill(pid, signum)
    except ProcessLookupError:
        pass


def _signal_tree(process_group: int, signum: int) -> None:
    try:
        os.killpg(process_group, signum)
    except ProcessLookupError:
        pass
    for pid in _descendants():
        try:
            if os.getpgid(pid) == process_group:
                continue
        except ProcessLookupError:
            continue
        _signal_process(pid, signum)


def _reap_available() -> None:
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _wait_for_descendants(process_group: int, timeout: float, signum: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _reap_available()
        descendants = _descendants()
        group_exists = _group_exists(process_group)
        if not descendants and not group_exists:
            return True
        if group_exists or descendants:
            _signal_tree(process_group, signum)
        time.sleep(0.05)
    _reap_available()
    return not _descendants() and not _group_exists(process_group)


def _cleanup_descendants(process_group: int) -> None:
    _reap_available()
    if not _descendants() and not _group_exists(process_group):
        return
    _signal_tree(process_group, signal.SIGTERM)
    if _wait_for_descendants(process_group, TERM_GRACE_SECONDS, signal.SIGTERM):
        return
    _signal_tree(process_group, signal.SIGKILL)
    if not _wait_for_descendants(process_group, KILL_GRACE_SECONDS, signal.SIGKILL):
        raise LockError("could not terminate and reap all supervised descendants")


def _exit_code(wait_status: int) -> int:
    if os.WIFEXITED(wait_status):
        return os.WEXITSTATUS(wait_status)
    if os.WIFSIGNALED(wait_status):
        return 128 + os.WTERMSIG(wait_status)
    return 125


def _child_exec(
    command: list[str],
    parent_pid: int,
    ready_write: int,
    release_read: int,
    context: dict[str, str],
) -> NoReturn:
    try:
        _set_parent_death_signal(parent_pid)
        os.setsid()
        session_id = str(os.getpid())
        os.write(ready_write, session_id.encode("ascii") + b"\n")
        os.close(ready_write)
        if os.read(release_read, 1) != b"1":
            raise OSError("resource lock supervisor did not release child startup")
        os.close(release_read)
        environment = os.environ.copy()
        for name in RESOURCE_CONTEXT_NAMES:
            environment.pop(name, None)
        environment.update(context)
        environment["PIXEAGLE_RESOURCE_LOCK_SESSION_ID"] = session_id
        environment["PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID"] = session_id
        if context["PIXEAGLE_RESOURCE_LOCK_MODE"] == "exclusive":
            environment["PIXEAGLE_SETUP_LOCK_SESSION_ID"] = session_id
        os.execvpe(command[0], command, environment)
    except BaseException as exc:
        print(f"PixEagle resource lock supervisor could not start command: {exc}", file=sys.stderr)
        os._exit(127)


def _resource_set_payload(resources: list[ResourceLock]) -> list[dict[str, object]]:
    return [resource.payload() for resource in resources]


def _build_context(
    resources: list[ResourceLock],
    mode: str,
    parent_pid: int,
    parent_start: str,
    state_path: Path | None,
    token: str,
) -> dict[str, str]:
    lock_paths = [str(resource.lock_path) for resource in resources]
    context = {
        "PIXEAGLE_RESOURCE_LOCK_MODE": mode,
        "PIXEAGLE_RESOURCE_LOCK_SET": json.dumps(
            _resource_set_payload(resources), sort_keys=True, separators=(",", ":")
        ),
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID": str(parent_pid),
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN": parent_start,
        "PIXEAGLE_ENVIRONMENT_LOCK_MODE": mode,
        "PIXEAGLE_ENVIRONMENT_LOCK_PATH": lock_paths[0],
        "PIXEAGLE_ENVIRONMENT_LOCK_PATHS": json.dumps(lock_paths, separators=(",", ":")),
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID": str(parent_pid),
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN": parent_start,
    }
    if mode == "exclusive":
        assert state_path is not None
        context.update(
            {
                "PIXEAGLE_RESOURCE_LOCK_STATE_PATH": str(state_path),
                "PIXEAGLE_RESOURCE_LOCK_TOKEN": token,
                "PIXEAGLE_SETUP_LOCK_PATH": lock_paths[0],
                "PIXEAGLE_SETUP_LOCK_STATE_PATH": str(state_path),
                "PIXEAGLE_SETUP_LOCK_TOKEN": token,
                "PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID": str(parent_pid),
                "PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN": parent_start,
            }
        )
    return context


def run_supervised(args: argparse.Namespace) -> int:
    resources = _resolve_specs(args.resource_path, args.lock_path)
    expected_state = _state_path(resources) if args.mode == "exclusive" else None
    if args.state_path:
        supplied_state = Path(os.path.normpath(args.state_path))
        if expected_state is None:
            raise LockError("shared supervision must not publish an exclusive lease")
        if supplied_state != expected_state:
            raise LockError("supplied exclusive lease path does not match sorted resources")
    descriptors: list[tuple[ResourceLock, int]] = []
    held: list[int] = []
    token = secrets.token_hex(TOKEN_BYTES)
    process_group: int | None = None
    lease_written = False
    ready_read: int | None = None
    ready_write: int | None = None
    release_read: int | None = None
    release_write: int | None = None
    cleanup_error: LockError | None = None
    try:
        for resource in resources:
            descriptors.append((resource, _open_lock(resource, create=True)))
        held = _acquire_all(descriptors, args.mode, args.timeout)
        _set_subreaper()
        parent_pid = os.getpid()
        parent_start = _process_start_token(parent_pid)
        ready_read, ready_write = os.pipe2(os.O_CLOEXEC)
        release_read, release_write = os.pipe2(os.O_CLOEXEC)
        context = _build_context(
            resources,
            args.mode,
            parent_pid,
            parent_start,
            expected_state,
            token,
        )

        child_pid = os.fork()
        if child_pid == 0:
            _close_quietly(ready_read)
            _close_quietly(release_write)
            for _resource, descriptor in descriptors:
                _close_quietly(descriptor)
            assert ready_write is not None and release_read is not None
            _child_exec(args.command, parent_pid, ready_write, release_read, context)

        process_group = child_pid
        _close_quietly(ready_write)
        ready_write = None
        _close_quietly(release_read)
        release_read = None
        assert ready_read is not None
        with os.fdopen(ready_read, "rb", closefd=True) as stream:
            ready = stream.readline(64).strip().decode("ascii")
        ready_read = None
        if ready != str(child_pid):
            raise LockError("supervised child did not establish the expected session")

        if args.mode == "exclusive":
            assert expected_state is not None
            lease = {
                "version": LEASE_VERSION,
                "mode": "exclusive",
                "resource_set": _resource_set_payload(resources),
                "lock_paths": [str(resource.lock_path) for resource in resources],
                "state_path": str(expected_state),
                "token": token,
                "supervisor_pid": parent_pid,
                "supervisor_start_token": parent_start,
                "session_id": process_group,
                "operation": args.operation,
                "started_at_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
            }
            _atomic_write_lease(expected_state, lease, resources[0])
            lease_written = True
        assert release_write is not None
        os.write(release_write, b"1")
        os.close(release_write)
        release_write = None

        def forward(signum: int, _frame: object) -> None:
            if process_group is not None:
                _signal_tree(process_group, signum)

        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT):
            signal.signal(signum, forward)

        while True:
            try:
                waited_pid, wait_status = os.waitpid(child_pid, 0)
                if waited_pid == child_pid:
                    break
            except InterruptedError:
                continue
        exit_code = _exit_code(wait_status)
        if args.descendant_policy == "terminate" or exit_code != 0:
            _cleanup_descendants(process_group)
        process_group = None
        return exit_code
    finally:
        _close_quietly(ready_read)
        _close_quietly(ready_write)
        _close_quietly(release_read)
        _close_quietly(release_write)
        if process_group is not None:
            try:
                _cleanup_descendants(process_group)
            except LockError as exc:
                cleanup_error = exc
                print(f"PixEagle resource lock cleanup failed: {exc}", file=sys.stderr)
        if lease_written and expected_state is not None:
            _remove_matching_lease(expected_state, token, resources[0])
        for descriptor in reversed(held):
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
        for _resource, descriptor in descriptors:
            _close_quietly(descriptor)
        if cleanup_error is not None and sys.exc_info()[0] is None:
            raise cleanup_error


def _parse_context_resource_set(raw_value: str) -> list[ResourceLock]:
    try:
        payload = json.loads(raw_value)
    except (ValueError, TypeError) as exc:
        raise LockError("invalid supervised resource lock set") from exc
    if not isinstance(payload, list) or not payload:
        raise LockError("supervised resource lock set must be a non-empty list")
    resources: list[ResourceLock] = []
    for item in payload:
        if not isinstance(item, dict) or set(item) != {
            "resource_path",
            "lock_path",
            "owner_uid",
        }:
            raise LockError("invalid entry in supervised resource lock set")
        lock_path = item["lock_path"]
        resource_path = item["resource_path"]
        owner_uid = item["owner_uid"]
        if not isinstance(lock_path, str) or not isinstance(owner_uid, int):
            raise LockError("invalid lock path or owner in supervised resource lock set")
        parsed = _parse_lock_path(lock_path)
        if parsed.owner_uid != owner_uid:
            raise LockError("supervised resource owner does not match its lock path")
        if resource_path is None:
            resources.append(parsed)
            continue
        if not isinstance(resource_path, str):
            raise LockError("invalid canonical path in supervised resource lock set")
        resolved = _resolve_resource(resource_path)
        if resolved.resource_path != resource_path or resolved.lock_path != parsed.lock_path:
            raise LockError("supervised canonical resource identity changed")
        resources.append(resolved)
    if resources != sorted(resources, key=_acquisition_key):
        raise LockError("supervised resource lock set is not in acquisition order")
    if len({str(resource.lock_path) for resource in resources}) != len(resources):
        raise LockError("supervised resource lock set contains duplicates")
    return resources


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise LockError(f"incomplete supervised resource context: missing {name}")
    return value


def _validate_compatibility_context(
    resources: list[ResourceLock], mode: str, supervisor_pid: int, start_token: str
) -> None:
    expected_paths = [str(resource.lock_path) for resource in resources]
    expected = {
        "PIXEAGLE_ENVIRONMENT_LOCK_MODE": mode,
        "PIXEAGLE_ENVIRONMENT_LOCK_PATH": expected_paths[0],
        "PIXEAGLE_ENVIRONMENT_LOCK_PATHS": json.dumps(expected_paths, separators=(",", ":")),
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID": str(supervisor_pid),
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN": start_token,
    }
    for name, value in expected.items():
        if os.environ.get(name) != value:
            raise LockError(f"compatibility resource lock context mismatch for {name}")


def _parse_fdinfo_lock(
    line: str,
    *,
    supervisor_pid: int,
    expected_mode: str,
    metadata: os.stat_result,
) -> bool:
    parts = line.split()
    if len(parts) < 9 or parts[0] != "lock:" or parts[2] != "FLOCK":
        return False
    if parts[4] != expected_mode or parts[5] != str(supervisor_pid):
        return False
    try:
        device_text, inode_text = parts[6].rsplit(":", 1)
        major_text, minor_text = device_text.split(":", 1)
        device = os.makedev(int(major_text, 16), int(minor_text, 16))
        inode = int(inode_text)
    except (ValueError, IndexError):
        return False
    return device == metadata.st_dev and inode == metadata.st_ino


def _verify_supervisor_flocks(
    resources: list[ResourceLock], supervisor_pid: int, mode: str
) -> None:
    opened: list[tuple[ResourceLock, int, os.stat_result]] = []
    try:
        for resource in resources:
            descriptor = _open_lock(resource, create=False)
            opened.append((resource, descriptor, os.fstat(descriptor)))
        expected_mode = "WRITE" if mode == "exclusive" else "READ"
        expected_by_identity = {
            (metadata.st_dev, metadata.st_ino): resource
            for resource, _descriptor, metadata in opened
        }
        descriptors_by_identity: set[tuple[int, int]] = set()
        flocks_by_identity: dict[tuple[int, int], set[str]] = {}
        try:
            descriptor_paths = list(Path(f"/proc/{supervisor_pid}/fd").iterdir())
        except OSError as exc:
            raise LockError("cannot inspect resource lock supervisor descriptors") from exc
        for descriptor_path in descriptor_paths:
            if not descriptor_path.name.isdecimal():
                continue
            try:
                current = descriptor_path.stat()
            except OSError:
                continue
            identity = (current.st_dev, current.st_ino)
            if identity in expected_by_identity:
                descriptors_by_identity.add(identity)
            try:
                lines = Path(
                    f"/proc/{supervisor_pid}/fdinfo/{descriptor_path.name}"
                ).read_text(encoding="ascii").splitlines()
            except OSError as exc:
                raise LockError("cannot inspect resource lock supervisor flock state") from exc
            for lock_mode in ("READ", "WRITE"):
                if any(
                    _parse_fdinfo_lock(
                        line,
                        supervisor_pid=supervisor_pid,
                        expected_mode=lock_mode,
                        metadata=current,
                    )
                    for line in lines
                ):
                    flocks_by_identity.setdefault(identity, set()).add(lock_mode)

        for identity, resource in expected_by_identity.items():
            if identity not in descriptors_by_identity:
                raise LockError(
                    f"resource lock supervisor has no descriptor for {resource.lock_path}"
                )
            if flocks_by_identity.get(identity) != {expected_mode}:
                raise LockError(
                    f"resource lock supervisor does not hold the expected {mode} flock "
                    f"for {resource.lock_path}"
                )
        if set(flocks_by_identity) != set(expected_by_identity):
            raise LockError("actual supervisor flock set does not match the held resource set")
    finally:
        for _resource, descriptor, _metadata in opened:
            os.close(descriptor)


def _requested_is_subset(
    requested: list[ResourceLock], held: list[ResourceLock]
) -> bool:
    held_by_path = {str(resource.lock_path): resource for resource in held}
    for resource in requested:
        candidate = held_by_path.get(str(resource.lock_path))
        if candidate is None:
            return False
        if (
            resource.resource_path is not None
            and candidate.resource_path not in (None, resource.resource_path)
        ):
            return False
    return True


def validate_context(args: argparse.Namespace) -> int:
    requested = _resolve_specs(args.resource_path, args.lock_path)
    held_mode = _required_environment("PIXEAGLE_RESOURCE_LOCK_MODE")
    if held_mode not in ("exclusive", "shared"):
        raise LockError("invalid supervised resource lock mode")
    if args.mode == "exclusive" and held_mode == "shared":
        raise LockError("cannot escalate a shared resource lock to exclusive")
    held = _parse_context_resource_set(
        _required_environment("PIXEAGLE_RESOURCE_LOCK_SET")
    )
    if not _requested_is_subset(requested, held):
        raise LockError("expected resources are not an exact subset of the held resource set")

    supervisor_text = _required_environment(
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID"
    )
    session_text = _required_environment("PIXEAGLE_RESOURCE_LOCK_SESSION_ID")
    start_token = _required_environment(
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN"
    )
    if not supervisor_text.isdecimal() or not session_text.isdecimal():
        raise LockError("invalid supervised resource process identity")
    supervisor_pid = int(supervisor_text)
    session_id = int(session_text)
    if _process_start_token(supervisor_pid) != start_token:
        raise LockError("resource lock supervisor identity changed")
    if os.getsid(0) != session_id:
        raise LockError("process is outside the supervised resource session")
    _validate_compatibility_context(held, held_mode, supervisor_pid, start_token)
    _verify_supervisor_flocks(held, supervisor_pid, held_mode)

    if held_mode == "shared":
        return 0

    state_path = Path(
        _required_environment("PIXEAGLE_RESOURCE_LOCK_STATE_PATH")
    )
    expected_state = _state_path(held)
    if state_path != expected_state:
        raise LockError("exclusive resource lease context has the wrong state path")
    token = _required_environment("PIXEAGLE_RESOURCE_LOCK_TOKEN")
    if len(token) != TOKEN_BYTES * 2 or any(
        character not in "0123456789abcdef" for character in token
    ):
        raise LockError("invalid exclusive resource lease token")
    compatibility = {
        "PIXEAGLE_SETUP_LOCK_PATH": str(held[0].lock_path),
        "PIXEAGLE_SETUP_LOCK_STATE_PATH": str(expected_state),
        "PIXEAGLE_SETUP_LOCK_TOKEN": token,
        "PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID": str(supervisor_pid),
        "PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN": start_token,
        "PIXEAGLE_SETUP_LOCK_SESSION_ID": str(session_id),
    }
    for name, value in compatibility.items():
        if os.environ.get(name) != value:
            raise LockError(f"exclusive compatibility context mismatch for {name}")

    payload, _identity = _read_lease(expected_state, held[0])
    expected = {
        "version": LEASE_VERSION,
        "mode": "exclusive",
        "resource_set": _resource_set_payload(held),
        "lock_paths": [str(resource.lock_path) for resource in held],
        "state_path": str(expected_state),
        "token": token,
        "supervisor_pid": supervisor_pid,
        "supervisor_start_token": start_token,
        "session_id": session_id,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise LockError(f"exclusive resource lease mismatch for {key}")
    return 0


def resource_status(args: argparse.Namespace) -> int:
    resource = _resolve_resource(args.resource_path)
    descriptor = _open_lock(resource, create=True)
    active = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            active = True
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)

    lease = _active_exclusive_lease(resource) if active else None
    payload: dict[str, object] = {
        "active": active,
        "lease_verified": lease is not None,
        "resource_path": resource.resource_path,
        "lock_path": str(resource.lock_path),
        "operation": lease.get("operation") if lease else None,
        "started_at_utc": lease.get("started_at_utc") if lease else None,
        "supervisor_pid": lease.get("supervisor_pid") if lease else None,
        "session_id": lease.get("session_id") if lease else None,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0

    print("PixEagle Setup Status")
    print("======================")
    print(f"Resource: {payload['resource_path']}")
    if not active:
        print("Active: no")
        print("A new setup/update transaction may acquire this resource.")
        return 0

    print("Active: yes")
    if lease is None:
        print("Owner: active resource holder (details unavailable for this lock)")
    else:
        print(f"Operation: {payload['operation']}")
        if payload["started_at_utc"]:
            print(f"Started: {payload['started_at_utc']}")
        print(f"Supervisor PID: {payload['supervisor_pid']}")
        print(f"Session ID: {payload['session_id']}")
    print("Action: wait for the active operation or inspect its terminal/process output.")
    print("Do not delete lock files or launch another installer concurrently.")
    return 0


def _prepare_directory_from_argument(raw_directory: str) -> Path:
    path = Path(os.path.normpath(raw_directory))
    if path.parent != LOCK_ROOT or not path.name.startswith(LOCK_DIRECTORY_PREFIX):
        raise LockError(f"invalid owner-controlled lock directory: {path}")
    owner_text = path.name.removeprefix(LOCK_DIRECTORY_PREFIX)
    if not owner_text.isdecimal():
        raise LockError(f"invalid deployment owner lock directory: {path}")
    descriptor, directory = _open_owner_directory(int(owner_text), create=True)
    os.close(descriptor)
    return directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    identity = subparsers.add_parser("identity")
    identity.add_argument("--resource-path", required=True)

    path = subparsers.add_parser("path")
    path.add_argument("--resource-path", required=True)

    directory = subparsers.add_parser("directory")
    directory_group = directory.add_mutually_exclusive_group(required=True)
    directory_group.add_argument("--resource-path")
    directory_group.add_argument("--owner-uid", type=int)
    directory_group.add_argument("--caller", action="store_true")

    prepare_directory = subparsers.add_parser("prepare-directory")
    prepare_directory.add_argument("--directory", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare_group = prepare.add_mutually_exclusive_group(required=True)
    prepare_group.add_argument("--resource-path")
    prepare_group.add_argument("--lock-path")

    run = subparsers.add_parser("run")
    run.add_argument("--mode", choices=("exclusive", "shared"), required=True)
    run.add_argument("--resource-path", action="append", default=[])
    run.add_argument("--lock-path", action="append", default=[])
    run.add_argument("--state-path")
    run.add_argument("--operation", default="resource operation")
    run.add_argument("--timeout", type=int, default=30)
    run.add_argument(
        "--descendant-policy",
        choices=("terminate", "preserve-on-success"),
        default="terminate",
        help=(
            "terminate all descendants before unlocking, or preserve intentional "
            "detached descendants only after a successful command"
        ),
    )
    run.add_argument("command", nargs=argparse.REMAINDER)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--mode", choices=("exclusive", "shared"), required=True)
    validate.add_argument("--resource-path", action="append", default=[])
    validate.add_argument("--lock-path", action="append", default=[])

    status = subparsers.add_parser("status")
    status.add_argument("--resource-path", required=True)
    status.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.subcommand == "identity":
        print(_resolve_resource(args.resource_path).resource_path)
        return 0
    if args.subcommand == "path":
        print(_resolve_resource(args.resource_path).lock_path)
        return 0
    if args.subcommand == "directory":
        if args.resource_path is not None:
            print(_resolve_resource(args.resource_path).lock_path.parent)
        else:
            owner_uid = os.geteuid() if args.caller else args.owner_uid
            if owner_uid < 0:
                parser.error("--owner-uid must be non-negative")
            _authorize(owner_uid)
            print(_lock_directory(owner_uid))
        return 0
    if args.subcommand == "prepare-directory":
        print(_prepare_directory_from_argument(args.directory))
        return 0
    if args.subcommand == "prepare":
        resource = (
            _resolve_resource(args.resource_path)
            if args.resource_path is not None
            else _parse_lock_path(args.lock_path)
        )
        descriptor = _open_lock(resource, create=True)
        os.close(descriptor)
        print(resource.lock_path)
        return 0
    if args.subcommand == "run":
        if args.timeout < 0:
            parser.error("--timeout must be non-negative")
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if not args.command:
            parser.error("a command is required after --")
        return run_supervised(args)
    if args.subcommand == "status":
        return resource_status(args)
    return validate_context(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LockError as exc:
        print(f"PixEagle resource lock error: {exc}", file=sys.stderr)
        raise SystemExit(73) from exc
