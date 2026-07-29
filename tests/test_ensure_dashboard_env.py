"""Structured dashboard environment initialization."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "scripts" / "setup" / "ensure-dashboard-env.py"


def _load_helper():
    spec = importlib.util.spec_from_file_location(
        "ensure_dashboard_env_contract",
        HELPER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creates_scalar_environment_atomically_and_preserves_existing(tmp_path):
    module = _load_helper()
    defaults = tmp_path / "env.yaml"
    output = tmp_path / ".env"
    defaults.write_text(
        "PORT: 3040\nHOST: 127.0.0.1\nFEATURE: true\nEMPTY: ''\n",
        encoding="utf-8",
    )

    assert module.ensure_dashboard_env(defaults, output) is True
    assert output.read_text(encoding="utf-8") == (
        "PORT=3040\nHOST=127.0.0.1\nFEATURE=true\nEMPTY=\n"
    )

    output.write_text("OPERATOR=preserved\n", encoding="utf-8")
    assert module.ensure_dashboard_env(defaults, output) is False
    assert output.read_text(encoding="utf-8") == "OPERATOR=preserved\n"


def test_rejects_nested_or_multiline_values(tmp_path):
    module = _load_helper()
    defaults = tmp_path / "env.yaml"
    output = tmp_path / ".env"
    defaults.write_text("NESTED:\n  value: invalid\n", encoding="utf-8")

    with pytest.raises(ValueError, match="scalar"):
        module.ensure_dashboard_env(defaults, output)
