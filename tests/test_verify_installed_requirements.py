"""Tests for offline installed-requirement verification."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "verify-installed-requirements.py"


def _run(requirements: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--requirements",
            str(requirements),
            *extra,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_accepts_installed_marked_and_hash_pinned_requirements(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "\n".join(
            [
                'packaging >= 20; python_version >= "3.8"',
                'missing-only-on-old-python==1; python_version < "2"',
                "packaging >= 20 \\",
                "    --hash=sha256:" + ("0" * 64),
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run(requirements)

    assert result.returncode == 0, result.stderr


def test_reports_missing_or_incompatible_direct_requirement(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "definitely-not-a-pixeagle-package==9999\npackaging<0\n",
        encoding="utf-8",
    )

    result = _run(requirements)

    assert result.returncode == 1
    assert "definitely-not-a-pixeagle-package is not installed" in result.stderr
    assert "does not satisfy <0" in result.stderr


def test_explicit_exclusion_supports_validated_provider_substitution(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "definitely-not-a-pixeagle-package==9999\n",
        encoding="utf-8",
    )

    result = _run(
        requirements,
        "--exclude",
        "definitely_not_a_pixeagle_package",
    )

    assert result.returncode == 0, result.stderr


def test_fails_closed_on_requirement_directives(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-r another-file.txt\n", encoding="utf-8")

    result = _run(requirements)

    assert result.returncode == 2
    assert "directives are not supported" in result.stderr
