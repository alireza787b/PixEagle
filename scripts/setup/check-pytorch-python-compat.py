#!/usr/bin/env python3
"""Validate an interpreter against the checked-in PyTorch matrix policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _version(value: str, *, field: str) -> tuple[int, int]:
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"{field} must use major.minor syntax")
    return int(match.group(1)), int(match.group(2))


def _matrix_label(data: dict) -> str:
    versions = {
        str(profile.get("packages", {}).get("torch", ""))
        for profile in data.get("profiles", {}).values()
        if profile.get("packages", {}).get("torch")
    }
    if len(versions) == 1:
        return f"PyTorch {versions.pop()} matrix"
    return "PyTorch matrix"


def check_compatibility(matrix_path: Path, python_version: str) -> str:
    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    policy = data.get("python_compatibility")
    if not isinstance(policy, dict):
        raise ValueError("matrix is missing python_compatibility")

    minimum_raw = str(policy.get("minimum", ""))
    maximum_raw = str(policy.get("maximum", ""))
    minimum = _version(minimum_raw, field="python_compatibility.minimum")
    maximum = _version(maximum_raw, field="python_compatibility.maximum")
    selected = _version(python_version, field="selected Python version")
    if minimum > maximum:
        raise ValueError("matrix Python compatibility range is inverted")

    label = _matrix_label(data)
    if selected < minimum or selected > maximum:
        raise RuntimeError(
            f"Python {python_version} is outside the reviewed {label} "
            f"range ({minimum_raw}-{maximum_raw})."
        )
    return (
        f"Python {python_version} is compatible with the reviewed {label} "
        f"range ({minimum_raw}-{maximum_raw})."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument(
        "--python-version",
        default=f"{sys.version_info.major}.{sys.version_info.minor}",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        message = check_compatibility(args.matrix, args.python_version)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Invalid PyTorch compatibility policy: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
