#!/usr/bin/env python3
"""Validate and atomically publish owner-controlled setup evidence."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any


FILE_MODE = 0o600
DIRECTORY_MODE = 0o700


def _absolute_path(raw_path: str) -> Path:
    requested = Path(os.path.abspath(os.path.expanduser(raw_path)))
    if not requested.name or requested.name in {".", ".."}:
        raise RuntimeError("evidence report path must name a file")
    return requested


def _ensure_parent(parent: Path) -> None:
    missing: list[Path] = []
    candidate = parent
    while not os.path.lexists(candidate):
        missing.append(candidate)
        if candidate.parent == candidate:
            raise RuntimeError("evidence report parent has no existing anchor")
        candidate = candidate.parent
    _validate_path_chain(candidate, require_owner=False)
    for directory in reversed(missing):
        try:
            os.mkdir(directory, DIRECTORY_MODE)
        except FileExistsError:
            pass


def _validate_path_chain(parent: Path, *, require_owner: bool = True) -> None:
    effective_uid = os.geteuid()
    current = Path(parent.anchor)
    components = parent.parts[1:] if parent.anchor else parent.parts
    for component in components:
        current /= component
        metadata = current.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"evidence path component is not a real directory: {current}")
        if mode & 0o022 and not mode & stat.S_ISVTX:
            raise RuntimeError(f"evidence path has a group/world-writable ancestor: {current}")
    parent_metadata = parent.lstat()
    if require_owner and (
        parent_metadata.st_uid != effective_uid
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise RuntimeError("evidence report parent must be owner-controlled and non-writable by others")


def _open_parent(parent: Path) -> tuple[int, os.stat_result]:
    before = parent.lstat()
    descriptor = os.open(
        parent,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    opened = os.fstat(descriptor)
    if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
        os.close(descriptor)
        raise RuntimeError("evidence report parent changed while opening")
    return descriptor, opened


def _target_metadata(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _validate_existing_target(metadata: os.stat_result | None) -> None:
    if metadata is None:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != FILE_MODE
    ):
        raise RuntimeError(
            "existing evidence report is not an owner-controlled 0600 regular file"
        )


def preflight(raw_path: str) -> Path:
    requested = _absolute_path(raw_path)
    _ensure_parent(requested.parent)
    _validate_path_chain(requested.parent)
    directory_fd, _metadata = _open_parent(requested.parent)
    temporary_name = f".{requested.name}.{secrets.token_hex(16)}.preflight"
    temporary_fd: int | None = None
    try:
        _validate_existing_target(_target_metadata(directory_fd, requested.name))
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            FILE_MODE,
            dir_fd=directory_fd,
        )
        os.fchmod(temporary_fd, FILE_MODE)
        os.write(temporary_fd, b"pixeagle-evidence-preflight\n")
        os.fsync(temporary_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)
    return requested


def atomic_write_bytes(raw_path: str, payload: bytes) -> Path:
    report = preflight(raw_path)
    directory_fd, _metadata = _open_parent(report.parent)
    temporary_name = f".{report.name}.{secrets.token_hex(16)}.tmp"
    temporary_fd: int | None = None
    published = False
    try:
        _validate_existing_target(_target_metadata(directory_fd, report.name))
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            FILE_MODE,
            dir_fd=directory_fd,
        )
        os.fchmod(temporary_fd, FILE_MODE)
        view = memoryview(payload)
        offset = 0
        while offset < len(view):
            written_bytes = os.write(temporary_fd, view[offset:])
            if written_bytes <= 0:
                raise RuntimeError("evidence report write made no progress")
            offset += written_bytes
        os.fsync(temporary_fd)
        written = os.fstat(temporary_fd)
        _validate_existing_target(written)
        os.replace(
            temporary_name,
            report.name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        published = True
        current = _target_metadata(directory_fd, report.name)
        if current is None or (current.st_dev, current.st_ino) != (
            written.st_dev,
            written.st_ino,
        ):
            raise RuntimeError("evidence report changed while publishing")
        os.fsync(directory_fd)
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if not published:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)
    return report


def atomic_write_json(raw_path: str, payload: Any) -> Path:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return atomic_write_bytes(raw_path, encoded)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    print(preflight(args.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
