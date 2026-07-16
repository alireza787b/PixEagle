"""Policy tests for the reviewed Ultralytics/OpenCV pip-check exception."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "scripts" / "setup" / "pip_check_policy.py"

spec = importlib.util.spec_from_file_location("pixeagle_pip_check_policy", POLICY_PATH)
assert spec and spec.loader
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

pytestmark = [pytest.mark.unit]


def test_clean_pip_check_still_validates_ultralytics_opencv_contract(monkeypatch):
    monkeypatch.setattr(
        policy,
        "ultralytics_opencv_contract",
        lambda: (True, "verified cv2 contract"),
    )
    valid, detail = policy.evaluate_pip_check(0, "No broken requirements found.\n")
    assert valid
    assert "No broken requirements found." in detail
    assert "verified cv2 contract" in detail


def test_clean_pip_check_rejects_failed_ultralytics_opencv_contract(monkeypatch):
    monkeypatch.setattr(
        policy,
        "ultralytics_opencv_contract",
        lambda: (False, "OpenCV metadata contract failed"),
    )
    valid, detail = policy.evaluate_pip_check(0, "No broken requirements found.\n")
    assert not valid
    assert detail == "OpenCV metadata contract failed"


def test_only_exact_ultralytics_opencv_name_mismatch_can_be_accepted(monkeypatch):
    monkeypatch.setattr(
        policy,
        "ultralytics_opencv_contract",
        lambda: (True, "verified cv2 contract"),
    )
    valid, detail = policy.evaluate_pip_check(
        1,
        "ultralytics 8.4.95 requires opencv-python>=4.6.0, which is not installed.\n",
    )
    assert valid
    assert "verified cv2 contract" in detail


@pytest.mark.parametrize(
    "output",
    [
        "another-package 1.0 requires opencv-python, which is not installed.",
        "ultralytics 8.4.95 requires numpy>=99, but you have numpy 2.0.",
        "",
    ],
)
def test_unrelated_or_undiagnosed_pip_check_failure_is_rejected(monkeypatch, output):
    monkeypatch.setattr(policy, "ultralytics_opencv_contract", lambda: (True, "ok"))
    valid, _detail = policy.evaluate_pip_check(1, output)
    assert not valid


def test_opencv_name_mismatch_is_rejected_when_runtime_contract_fails(monkeypatch):
    monkeypatch.setattr(
        policy,
        "ultralytics_opencv_contract",
        lambda: (False, "OpenCV version mismatch"),
    )
    valid, detail = policy.evaluate_pip_check(
        1,
        "ultralytics 8.4.95 has requirement opencv-python>=4.6.0, but it is missing.\n",
    )
    assert not valid
    assert detail == "OpenCV version mismatch"


def test_init_and_ai_installer_use_the_same_policy_helper():
    init = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    ai = (PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh").read_text(
        encoding="utf-8"
    )
    assert "setup/pip_check_policy.py" in init
    assert "pip_check_policy.py" in ai
    assert '"$VENV_PIP" check' not in init
    assert '"$VENV_PIP" check' not in ai
