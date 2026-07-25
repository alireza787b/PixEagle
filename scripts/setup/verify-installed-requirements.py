#!/usr/bin/env python3
"""Verify direct requirement contracts against an installed environment.

This helper is intentionally offline. It checks the active environment's
installed distribution metadata against the canonical requirement files, while
``pip_check_policy.py`` remains responsible for transitive dependency health
and PixEagle's reviewed OpenCV provider substitution.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import re
import sys
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name


HASH_OPTION = re.compile(r"\s+--hash=[^\s]+")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify installed packages against requirement files offline.",
    )
    parser.add_argument(
        "--requirements",
        action="append",
        required=True,
        type=Path,
        help="Requirement file to validate; may be supplied more than once.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Canonical distribution name intentionally owned by another "
            "validated provider; may be supplied more than once."
        ),
    )
    return parser.parse_args()


def _logical_lines(path: Path) -> list[tuple[int, str]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Requirement path must be a regular file: {path}")

    logical: list[tuple[int, str]] = []
    pending = ""
    pending_line = 0
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            pending_line = line_number
        if stripped.endswith("\\"):
            pending += stripped[:-1].rstrip() + " "
            continue
        candidate = (pending + stripped).strip()
        pending = ""
        if candidate and not candidate.startswith("#"):
            logical.append((pending_line, candidate))
    if pending:
        raise ValueError(f"{path}:{pending_line}: unterminated line continuation")
    return logical


def _requirement_from_line(path: Path, line_number: int, line: str) -> Requirement:
    content = line.split(" #", 1)[0].rstrip()
    content = HASH_OPTION.sub("", content).strip()
    if not content:
        raise ValueError(f"{path}:{line_number}: requirement is empty")
    if content.startswith("-"):
        raise ValueError(
            f"{path}:{line_number}: requirement directives are not supported "
            "by the offline verifier"
        )
    try:
        requirement = Requirement(content)
    except InvalidRequirement as exc:
        raise ValueError(f"{path}:{line_number}: invalid requirement: {exc}") from exc
    if requirement.url:
        raise ValueError(
            f"{path}:{line_number}: direct URL requirements require installer "
            "artifact verification"
        )
    return requirement


def verify(
    requirement_paths: list[Path],
    *,
    excluded_names: set[str],
) -> list[str]:
    errors: list[str] = []
    for path in requirement_paths:
        for line_number, line in _logical_lines(path):
            requirement = _requirement_from_line(path, line_number, line)
            canonical_name = canonicalize_name(requirement.name)
            if canonical_name in excluded_names:
                continue
            if requirement.marker and not requirement.marker.evaluate():
                continue
            try:
                installed_version = metadata.version(requirement.name)
            except metadata.PackageNotFoundError:
                errors.append(
                    f"{path}:{line_number}: {requirement.name} is not installed"
                )
                continue
            if (
                requirement.specifier
                and installed_version not in requirement.specifier
            ):
                errors.append(
                    f"{path}:{line_number}: {requirement.name} "
                    f"{installed_version} does not satisfy "
                    f"{requirement.specifier}"
                )
    return errors


def main() -> int:
    args = _parse_args()
    excluded = {canonicalize_name(value) for value in args.exclude}
    try:
        errors = verify(args.requirements, excluded_names=excluded)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Installed-requirements verification failed: {exc}", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Installed direct requirements satisfy the current contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
