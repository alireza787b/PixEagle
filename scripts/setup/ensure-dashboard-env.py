#!/usr/bin/env python3
"""Create dashboard/.env from the checked-in YAML defaults when absent."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

import yaml


ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _serialize(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        text = str(value)
        if "\n" in text or "\r" in text:
            raise ValueError("dashboard environment values must be single-line scalars")
        return text
    raise ValueError("dashboard environment defaults must contain scalar values")


def ensure_dashboard_env(default_path: Path, output_path: Path) -> bool:
    """Create the output atomically; return False when it already exists."""
    if output_path.is_symlink():
        raise ValueError(f"dashboard environment must not be a symlink: {output_path}")
    if output_path.exists():
        if not output_path.is_file():
            raise ValueError(
                f"dashboard environment path must be a regular file: {output_path}"
            )
        return False

    if default_path.is_symlink() or not default_path.is_file():
        raise ValueError(f"dashboard defaults must be a regular file: {default_path}")
    payload = yaml.safe_load(default_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("dashboard defaults must contain a non-empty mapping")

    lines: list[str] = []
    for raw_name, value in payload.items():
        name = str(raw_name)
        if not ENVIRONMENT_NAME.fullmatch(name):
            raise ValueError(f"invalid dashboard environment name: {name!r}")
        lines.append(f"{name}={_serialize(value)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--defaults", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        created = ensure_dashboard_env(args.defaults, args.output)
    except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
        print(f"Dashboard environment setup failed: {exc}")
        return 1
    print("created" if created else "preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
