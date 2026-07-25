#!/usr/bin/env python3
"""Reset operator runtime settings to the current checked-in defaults.

This command is intentionally narrower than a reinstall. It replaces only
``configs/config.yaml`` and ``dashboard/.env``, refreshes config-sync metadata,
and records owner-only backups. Models, credentials, recordings, logs, and
other operator data are not touched.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.config_service import ConfigService


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    mode: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reset PixEagle runtime config and dashboard environment to the "
            "current checked-in defaults."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--source",
        default="setup_local_settings_reset",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def _regular_file(path: Path, *, required: bool) -> bool:
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link settings path: {path}")
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required settings source is missing: {path}")
        return False
    if not path.is_file():
        raise ValueError(f"Settings path must be a regular file: {path}")
    return True


def _snapshot(path: Path, *, mode: int = 0o600) -> FileSnapshot:
    existed = _regular_file(path, required=False)
    return FileSnapshot(
        path=path,
        existed=existed,
        content=path.read_bytes() if existed else None,
        mode=(path.stat().st_mode & 0o777) if existed else mode,
    )


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError(f"Settings parent must be a regular directory: {path.parent}")
    if path.is_symlink():
        raise ValueError(f"Refusing symbolic-link settings path: {path}")

    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        os.chmod(path, mode)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _restore(snapshot: FileSnapshot) -> None:
    if snapshot.existed:
        _atomic_write(
            snapshot.path,
            snapshot.content or b"",
            mode=snapshot.mode,
        )
        return
    if snapshot.path.exists() or snapshot.path.is_symlink():
        if snapshot.path.is_symlink() or not snapshot.path.is_file():
            raise ValueError(
                f"Cannot remove changed non-regular rollback path: {snapshot.path}"
            )
        snapshot.path.unlink()
        _fsync_directory(snapshot.path.parent)


def _create_backup(
    path: Path,
    backup_dir: Path,
    *,
    prefix: str,
    suffix: str,
) -> Path | None:
    if not _regular_file(path, required=False):
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    if backup_dir.is_symlink() or not backup_dir.is_dir():
        raise ValueError(f"Backup path must be a regular directory: {backup_dir}")
    os.chmod(backup_dir, 0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / (
        f"{prefix}_{timestamp}_{uuid.uuid4().hex[:10]}{suffix}"
    )
    descriptor = os.open(
        backup_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(path.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        os.chmod(backup_path, 0o600)
        _fsync_directory(backup_dir)
    except Exception:
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


def _serialize_dashboard_env(path: Path) -> bytes:
    _regular_file(path, required=True)
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not loaded:
        raise ValueError("dashboard/env_default.yaml must contain a non-empty mapping")
    invalid_keys = [
        key
        for key in loaded
        if not isinstance(key, str)
        or not key
        or any(character in key for character in "=\r\n\0")
    ]
    if invalid_keys:
        raise ValueError("dashboard/env_default.yaml contains an invalid key")
    lines = []
    for key, value in loaded.items():
        rendered = str(value)
        if any(character in rendered for character in "\r\n\0"):
            raise ValueError(
                f"dashboard/env_default.yaml value for {key} is not single-line"
            )
        lines.append(f"{key}={rendered}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_checked_in_config(project_root: Path, staging_root: Path) -> bytes:
    source_dir = project_root / "configs"
    validation_dir = staging_root / "validation" / "configs"
    validation_dir.mkdir(parents=True)
    for filename in (
        "config_default.yaml",
        "config_schema.yaml",
        "config_retirements.yaml",
    ):
        source = source_dir / filename
        _regular_file(source, required=True)
        shutil.copyfile(source, validation_dir / filename)
    shutil.copyfile(
        validation_dir / "config_default.yaml",
        validation_dir / "config.yaml",
    )
    ConfigService(project_root=validation_dir.parent)
    return (source_dir / "config_default.yaml").read_bytes()


def reset_local_settings(project_root: Path, *, source: str) -> dict[str, str | None]:
    project_root = project_root.expanduser().resolve()
    config_path = project_root / "configs" / "config.yaml"
    env_path = project_root / "dashboard" / ".env"
    sync_meta_path = project_root / "configs" / "config_sync_meta.json"
    audit_path = project_root / "configs" / "audit_log.json"
    env_default_path = project_root / "dashboard" / "env_default.yaml"
    staged_defaults_path = project_root / "configs" / ".config_default_preupdate.yaml"

    snapshots = [
        _snapshot(config_path),
        _snapshot(env_path),
        _snapshot(sync_meta_path),
        _snapshot(audit_path),
        _snapshot(staged_defaults_path),
    ]
    created_backups: list[Path] = []
    config_backup: Path | None = None
    env_backup: Path | None = None
    with tempfile.TemporaryDirectory(
        prefix=".pixeagle-settings-reset.",
        dir=project_root,
    ) as temp_name:
        staging_root = Path(temp_name)
        os.chmod(staging_root, 0o700)
        config_content = _validate_checked_in_config(project_root, staging_root)
        env_content = _serialize_dashboard_env(env_default_path)

        try:
            config_backup = _create_backup(
                config_path,
                project_root / "configs" / "backups",
                prefix="config",
                suffix=".yaml",
            )
            if config_backup is not None:
                created_backups.append(config_backup)
            env_backup = _create_backup(
                env_path,
                project_root / "dashboard" / "backups",
                prefix="env",
                suffix=".env",
            )
            if env_backup is not None:
                created_backups.append(env_backup)

            _atomic_write(config_path, config_content)
            _atomic_write(env_path, env_content)

            service = ConfigService(project_root=project_root)
            source_digests = service.get_source_state_digests()
            if not service.refresh_defaults_snapshot(provenance=source):
                raise RuntimeError("Could not refresh the config defaults baseline")
            service.log_audit_entry(
                action="reset_defaults",
                section="*",
                old_value=None,
                new_value=None,
                source=source,
                expected_digest=source_digests["audit_log"],
            )
            if staged_defaults_path.exists() or staged_defaults_path.is_symlink():
                if staged_defaults_path.is_symlink() or not staged_defaults_path.is_file():
                    raise ValueError(
                        "Pending pre-update defaults are not a regular file"
                    )
                staged_defaults_path.unlink()
                _fsync_directory(staged_defaults_path.parent)
        except Exception:
            rollback_errors = []
            for snapshot in reversed(snapshots):
                try:
                    _restore(snapshot)
                except Exception as rollback_error:
                    rollback_errors.append(f"{snapshot.path}: {rollback_error}")
            for backup in created_backups:
                backup.unlink(missing_ok=True)
            if rollback_errors:
                raise RuntimeError(
                    "Settings reset failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                )
            raise

    return {
        "config_backup": str(config_backup) if config_backup else None,
        "env_backup": str(env_backup) if env_backup else None,
    }


def main() -> int:
    args = _parse_args()
    try:
        result = reset_local_settings(args.project_root, source=args.source)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Settings reset failed: {exc}", file=sys.stderr)
        return 1

    print("Runtime config and dashboard environment reset to current defaults.")
    if result["config_backup"]:
        print(f"Config backup: {result['config_backup']}")
    if result["env_backup"]:
        print(f"Dashboard env backup: {result['env_backup']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
