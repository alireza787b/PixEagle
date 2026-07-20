#!/usr/bin/env python3
"""Validate Python against PixEagle's checked-in dependency policy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?$")


class CompatibilityError(RuntimeError):
    """The policy is valid, but the selected interpreter is not compatible."""


def _version(value: str, *, field: str) -> tuple[int, ...]:
    match = VERSION_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"{field} must use major.minor or major.minor.patch syntax")
    parts = [int(match.group(1)), int(match.group(2))]
    if match.group(3) is not None:
        parts.append(int(match.group(3)))
    return tuple(parts)


def _series(value: tuple[int, ...]) -> tuple[int, int]:
    return value[0], value[1]


def _policy_range(
    policy: dict[str, Any], *, field: str
) -> tuple[tuple[int, int], tuple[int, int] | None]:
    minimum_raw = str(policy.get("minimum", ""))
    minimum = _series(_version(minimum_raw, field=f"{field}.minimum"))
    maximum_value = policy.get("maximum")
    maximum = None
    if maximum_value not in (None, ""):
        maximum = _series(
            _version(str(maximum_value), field=f"{field}.maximum")
        )
        if minimum > maximum:
            raise ValueError(f"{field} range is inverted")
    return minimum, maximum


def _excluded(policy: dict[str, Any], *, field: str) -> list[tuple[int, ...]]:
    raw = policy.get("excluded", [])
    if not isinstance(raw, list):
        raise ValueError(f"{field}.excluded must be a list")
    return [
        _version(str(value), field=f"{field}.excluded")
        for value in raw
    ]


def _matches_exclusion(selected: tuple[int, ...], excluded: tuple[int, ...]) -> bool:
    if len(excluded) == 2:
        return _series(selected) == excluded
    selected_patch = selected if len(selected) == 3 else (*selected, 0)
    return selected_patch == excluded


def _range_text(policy: dict[str, Any]) -> str:
    minimum = str(policy["minimum"])
    maximum = policy.get("maximum")
    text = f">={minimum}" if maximum in (None, "") else f"{minimum}-{maximum}"
    excluded = policy.get("excluded", [])
    if excluded:
        text += "; excluding " + ", ".join(str(value) for value in excluded)
    return text


def _check_policy(
    policy: dict[str, Any],
    python_version: str,
    *,
    field: str,
) -> None:
    selected = _version(python_version, field="selected Python version")
    selected_series = _series(selected)
    minimum, maximum = _policy_range(policy, field=field)
    if selected_series < minimum or (maximum is not None and selected_series > maximum):
        raise CompatibilityError(
            f"Python {python_version} is outside the reviewed range "
            f"({_range_text(policy)})."
        )
    for excluded in _excluded(policy, field=field):
        if _matches_exclusion(selected, excluded):
            raise CompatibilityError(
                f"Python {python_version} is explicitly excluded by the reviewed policy."
            )


def _load_policy(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("policy root must be an object")
    if data.get("schema_version") != 2:
        raise ValueError("unsupported or missing schema_version (expected 2)")
    return data


def _check_language_family(data: dict[str, Any], python_version: str) -> None:
    language = data.get("python_language")
    if not isinstance(language, dict):
        raise ValueError("policy is missing python_language")
    required_major = language.get("required_major")
    if (
        isinstance(required_major, bool)
        or not isinstance(required_major, int)
        or required_major < 1
    ):
        raise ValueError("python_language.required_major must be a positive integer")

    selected = _version(python_version, field="selected Python version")
    if selected[0] != required_major:
        raise CompatibilityError(
            f"Python {python_version} is outside the supported Python "
            f"{required_major} language family."
        )


def _runtime_message(data: dict[str, Any], role: str, python_version: str) -> str:
    runtimes = data.get("python_runtime")
    if not isinstance(runtimes, dict) or not isinstance(runtimes.get(role), dict):
        raise ValueError(f"policy is missing python_runtime.{role}")
    policy = runtimes[role]
    _check_policy(policy, python_version, field=f"python_runtime.{role}")

    selected_series = ".".join(python_version.split(".")[:2])
    evidence_series = policy.get("evidence_series", [])
    if not isinstance(evidence_series, list):
        raise ValueError(f"python_runtime.{role}.evidence_series must be a list")
    evidence = {str(value) for value in evidence_series}
    if selected_series in evidence:
        return f"Python {python_version} is covered by recorded {role} runtime evidence."
    return (
        f"Python {python_version} is accepted by the {role} runtime policy; "
        "the transactional dependency install will validate this exact host."
    )


def _profile_label(profile_key: str, profile: dict[str, Any]) -> str:
    packages = profile.get("packages", {})
    torch_version = packages.get("torch") if isinstance(packages, dict) else None
    if torch_version:
        return f"{profile_key} (PyTorch {torch_version})"
    return profile_key


def _profile_policy(
    data: dict[str, Any], profile_key: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("policy is missing profiles")
    profile = profiles.get(profile_key)
    if not isinstance(profile, dict):
        raise ValueError(f"unknown profile: {profile_key}")
    policy = profile.get("python_compatibility")
    if not isinstance(policy, dict):
        raise ValueError(f"profile {profile_key} is missing python_compatibility")
    return profile, policy


def _profile_message(data: dict[str, Any], profile_key: str, python_version: str) -> str:
    profile, policy = _profile_policy(data, profile_key)
    try:
        _check_policy(
            policy,
            python_version,
            field=f"profiles.{profile_key}.python_compatibility",
        )
    except CompatibilityError as exc:
        raise CompatibilityError(
            f"Python {python_version} is not compatible with "
            f"{_profile_label(profile_key, profile)}: {exc}"
        ) from exc
    return (
        f"Python {python_version} is compatible with the reviewed "
        f"{_profile_label(profile_key, profile)} profile "
        f"({_range_text(policy)})."
    )


def _any_profile_message(data: dict[str, Any], python_version: str) -> str:
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise ValueError("policy is missing profiles")

    compatible: list[str] = []
    reviewed: list[str] = []
    for profile_key, raw_profile in profiles.items():
        if not isinstance(raw_profile, dict) or not raw_profile.get("supported", True):
            continue
        profile, policy = _profile_policy(data, str(profile_key))
        reviewed.append(_profile_label(str(profile_key), profile))
        try:
            _check_policy(
                policy,
                python_version,
                field=f"profiles.{profile_key}.python_compatibility",
            )
        except CompatibilityError:
            continue
        compatible.append(_profile_label(str(profile_key), profile))

    if not reviewed:
        raise ValueError("policy has no supported Full AI profiles")
    if not compatible:
        raise CompatibilityError(
            f"Python {python_version} is not covered by any supported Full AI profile."
        )
    return (
        f"Python {python_version} is covered by {len(compatible)} reviewed Full AI "
        "profile(s); the exact hardware profile is validated before AI packages change."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--runtime-role")
    mode.add_argument("--profile")
    mode.add_argument("--any-supported-profile", action="store_true")
    parser.add_argument(
        "--python-version",
        default=(
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        data = _load_policy(args.policy)
        _check_language_family(data, args.python_version)
        if args.runtime_role:
            message = _runtime_message(data, args.runtime_role, args.python_version)
        elif args.profile:
            message = _profile_message(data, args.profile, args.python_version)
        else:
            message = _any_profile_message(data, args.python_version)
    except CompatibilityError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Invalid Python compatibility policy: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
