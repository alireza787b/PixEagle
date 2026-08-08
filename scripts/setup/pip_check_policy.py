#!/usr/bin/env python3
"""Validate reviewed OpenCV distribution-name substitutions around ``pip check``."""

from __future__ import annotations

import importlib.metadata as metadata
import re
import subprocess
import sys


OPENCV_SUBSTITUTION_CONSUMERS = ("ultralytics", "ncnn")
ALLOWED_OPENCV_MISMATCH = re.compile(
    r"^(?:ultralytics|ncnn)\s+\S+\s+"
    r"(?:has requirement|requires)\s+opencv-python\b",
    flags=re.IGNORECASE,
)
OPENCV_DISTRIBUTIONS = (
    "opencv-python",
    "opencv-contrib-python",
    "opencv-python-headless",
    "opencv-contrib-python-headless",
)


def installed_opencv_contract_version() -> tuple[str, str]:
    """Return the version namespace that owns the active OpenCV provider."""
    owners: list[tuple[str, str]] = []
    for name in OPENCV_DISTRIBUTIONS:
        try:
            owners.append((name, metadata.version(name)))
        except metadata.PackageNotFoundError:
            continue
    if len(owners) > 1:
        names = ", ".join(name for name, _version in owners)
        raise RuntimeError(f"multiple OpenCV distributions are installed: {names}")
    if owners:
        name, version = owners[0]
        return version, f"{name} distribution"

    import cv2

    return cv2.__version__, "source-built cv2 module"


def opencv_substitution_contracts() -> tuple[bool, str]:
    try:
        try:
            from packaging.requirements import Requirement
        except ImportError:
            from pip._vendor.packaging.requirements import Requirement
        opencv_version, opencv_provider = installed_opencv_contract_version()
    except Exception as exc:
        return False, f"cannot validate the OpenCV substitution contract: {exc}"

    verified: list[str] = []
    installed_consumers = 0
    for consumer in OPENCV_SUBSTITUTION_CONSUMERS:
        try:
            requirements = metadata.requires(consumer) or []
        except metadata.PackageNotFoundError:
            continue
        installed_consumers += 1
        matched = False
        for raw in requirements:
            requirement = Requirement(raw)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            normalized = requirement.name.lower().replace("_", "-")
            if normalized != "opencv-python":
                continue
            matched = True
            if requirement.specifier and opencv_version not in requirement.specifier:
                return (
                    False,
                    f"OpenCV {opencv_version} from {opencv_provider} does not satisfy "
                    f"{consumer} {requirement.specifier}",
                )
        if not matched:
            return (
                False,
                f"{consumer} metadata did not declare its expected opencv-python contract",
            )
        verified.append(consumer)

    if installed_consumers == 0:
        return True, "No OpenCV substitution consumers are installed"
    return True, (
        f"verified OpenCV {opencv_version} from {opencv_provider} "
        f"against {', '.join(verified)} metadata"
    )


def evaluate_pip_check(returncode: int, output: str) -> tuple[bool, str]:
    contract_valid, contract_detail = opencv_substitution_contracts()
    if not contract_valid:
        return False, contract_detail
    if returncode == 0:
        pip_detail = output.strip() or "No broken requirements found."
        return True, f"{pip_detail} {contract_detail}"
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    allowed = [line for line in lines if ALLOWED_OPENCV_MISMATCH.match(line)]
    unexpected = [line for line in lines if line not in allowed]
    if unexpected or not allowed:
        return False, "\n".join(unexpected or lines or ["pip check failed without diagnostics"])
    return True, (
        f"{contract_detail}; accepted only the package-name mismatch reported by pip"
    )


def main() -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        text=True,
        capture_output=True,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    valid, detail = evaluate_pip_check(completed.returncode, output)
    stream = sys.stdout if valid else sys.stderr
    print(detail, file=stream)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
