#!/usr/bin/env python3
"""Cross-process lifecycle lock shared by native Windows setup and runtime."""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Iterator


class LifecycleLockError(RuntimeError):
    """Raised when another lifecycle transaction owns the checkout."""


def lifecycle_lock_path(project_root: Path) -> Path:
    normalized = os.path.abspath(str(project_root)).lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / f"pixeagle-windows-{digest}.lock"


@contextlib.contextmanager
def lifecycle_lock(
    project_root: Path,
    *,
    timeout_seconds: float = 15.0,
) -> Iterator[None]:
    """Own one source/setup/runtime transaction for the checkout."""
    path = lifecycle_lock_path(project_root)
    deadline = time.monotonic() + timeout_seconds
    stream = None

    while stream is None:
        try:
            stream = path.open("a+b")
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise LifecycleLockError(
                    "another PixEagle Windows lifecycle operation is active"
                ) from exc
            time.sleep(0.1)

    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()

        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError) as exc:
                if time.monotonic() >= deadline:
                    raise LifecycleLockError(
                        "another PixEagle Windows lifecycle operation is active"
                    ) from exc
                time.sleep(0.1)

        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()
