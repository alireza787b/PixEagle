#!/usr/bin/env python3
"""Apply PixEagle's one documented exception to ``pip check``."""

from __future__ import annotations

import importlib.metadata as metadata
import re
import subprocess
import sys


ALLOWED_OPENCV_MISMATCH = re.compile(
    r"^ultralytics\s+\S+\s+(?:has requirement|requires)\s+opencv-python\b",
    flags=re.IGNORECASE,
)


def ultralytics_opencv_contract() -> tuple[bool, str]:
    try:
        requirements = metadata.requires("ultralytics") or []
    except metadata.PackageNotFoundError:
        return True, "Ultralytics is not installed"
    try:
        import cv2
        try:
            from packaging.requirements import Requirement
        except ImportError:
            from pip._vendor.packaging.requirements import Requirement
    except Exception as exc:
        return False, f"cannot validate the Ultralytics/OpenCV contract: {exc}"

    matched = False
    for raw in requirements:
        requirement = Requirement(raw)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        normalized = requirement.name.lower().replace("_", "-")
        if normalized != "opencv-python":
            continue
        matched = True
        if requirement.specifier and cv2.__version__ not in requirement.specifier:
            return (
                False,
                f"OpenCV {cv2.__version__} does not satisfy Ultralytics {requirement.specifier}",
            )
    if not matched:
        return False, "Ultralytics metadata did not declare its expected opencv-python contract"
    return True, f"verified cv2 {cv2.__version__} against Ultralytics metadata"


def evaluate_pip_check(returncode: int, output: str) -> tuple[bool, str]:
    contract_valid, contract_detail = ultralytics_opencv_contract()
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
