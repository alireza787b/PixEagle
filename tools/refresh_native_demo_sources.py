#!/usr/bin/env python3
"""Refresh a stopped private development demo without replacing operator data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import uuid

REPOSITORY = Path(__file__).resolve().parents[1]
DEFINITIONS = (
    "config_default.yaml", "config_schema.yaml", "config_retirements.yaml",
    "tracker_schemas.yaml", "follower_commands.yaml",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths(repository):
    entries = subprocess.check_output(
        ["git", "ls-files", "-cmo", "--exclude-standard", "-z", "--", "src"], cwd=repository,
    ).decode().split("\0")
    return sorted(set(entries) - {""})


def refresh(runtime, *, repository=REPOSITORY):
    runtime = Path(runtime).absolute()
    repository = Path(repository).resolve()
    if runtime.is_symlink() or not runtime.is_dir() or runtime.stat().st_mode & 0o077:
        raise ValueError("Use an existing private, non-symlink demo directory")
    manifest_path = runtime / "demo-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("version") != 1 or manifest.get("kind") != "real-core-recorded-video":
        raise ValueError("Unsupported demo manifest")
    target = runtime / "src"
    if target.is_symlink():
        raise ValueError("Refresh the prepared source demo directly, not a derived symlink fixture")
    if not target.is_dir():
        raise ValueError("Demo source tree is missing")
    definitions = runtime / "configs"
    if definitions.is_symlink() or not definitions.is_dir():
        raise ValueError("Demo config definitions must be a local directory")
    for name in DEFINITIONS:
        if (definitions / name).is_symlink():
            raise ValueError("Refusing a symlinked config definition")
    backup = runtime / ("source-refresh-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    backup.mkdir(mode=0o700)
    staged = Path(tempfile.mkdtemp(prefix=".src-refresh-", dir=target.parent))
    copied = {}
    try:
        for name in source_paths(repository):
            source = repository / name
            relative = Path(name)
            if relative.parts[0] != "src" or ".." in relative.parts or source.is_symlink() or not source.is_file():
                raise ValueError("Unexpected source snapshot path")
            destination = staged / relative.relative_to("src")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied[name] = digest(destination)
        if "src/classes/api_security_policy.py" not in copied:
            raise ValueError("Source snapshot is missing the API security policy")
        shutil.copyfile(manifest_path, backup / "demo-manifest.json")
        for name in DEFINITIONS:
            source = repository / "configs" / name
            if source.is_symlink() or not source.is_file():
                raise ValueError("Source definition is not a regular file")
            if (definitions / name).exists():
                shutil.copyfile(definitions / name, backup / name)
        target.rename(backup / "src")
        try:
            staged.rename(target)
            for name in DEFINITIONS:
                shutil.copyfile(repository / "configs" / name, definitions / name)
                copied["configs/" + name] = digest(definitions / name)
            old = manifest.get("source_files", {})
            manifest["source_files"] = {key: value for key, value in old.items() if not key.startswith("src/")}
            manifest["source_files"].update(copied)
            manifest["source_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository).decode().strip()
            manifest["source_repository"] = str(repository)
            manifest["source_refresh"] = {"backup": str(backup), "files": copied,
                                          "operator_config_preserved": True, "models_media_secrets_preserved": True}
            temp_manifest = runtime / ".demo-manifest.refresh.json"
            temp_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
            os.chmod(temp_manifest, 0o600)
            temp_manifest.replace(manifest_path)
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            (backup / "src").rename(target)
            for name in DEFINITIONS:
                if (backup / name).exists():
                    shutil.copyfile(backup / name, definitions / name)
            shutil.copyfile(backup / "demo-manifest.json", manifest_path)
            raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path, help="Prepared private demo; stop its backend before refreshing")
    args = parser.parse_args()
    backup = refresh(args.runtime)
    print(f"Demo source and definitions refreshed; prior snapshot: {backup}")


if __name__ == "__main__":
    main()
