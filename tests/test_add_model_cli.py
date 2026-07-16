"""Policy tests for the local SmartTracker model CLI."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import add_model
from classes.model_manager import ModelManager as RealModelManager


class FakeModelManager:
    validation = {
        "valid": True,
        "model_type": "custom",
        "task": "detect",
        "smarttracker_supported": True,
        "compatibility_notes": [],
        "num_classes": 1,
        "class_names": ["target"],
        "is_custom": True,
    }
    export_calls = 0
    models_root: Path
    last_init_kwargs = {}

    def __init__(self, **kwargs):
        type(self).last_init_kwargs = dict(kwargs)
        self.models_folder = self.models_root
        self.max_model_bytes = 1024 * 1024
        self.trust_policy = kwargs.get("trust_policy", "operator_ack_or_digest")

    @contextmanager
    def observe_local_model(self, model_name):
        path = self.models_folder / model_name
        yield SimpleNamespace(
            path=path,
            observed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def trust_observed_local_model(self, observation, **kwargs):
        if not self.validation.get("smarttracker_supported", False):
            return {
                "success": False,
                "error": (
                    "SmartTracker supports only detect/obb models; "
                    f"received task={self.validation.get('task')}"
                ),
            }
        return {
            "success": True,
            "path": str(observation.path),
            "artifact_sha256": observation.observed_sha256,
            "observed_sha256": observation.observed_sha256,
            "publisher_sha256": kwargs.get("expected_sha256"),
            "trust_method": (
                "expected_sha256"
                if kwargs.get("expected_sha256")
                else "operator_assertion"
            ),
            "registration_action_id": "model-registration-v1:" + "a" * 64,
            "validation": dict(self.validation),
        }

    def export_to_ncnn(self, path):
        type(self).export_calls += 1
        output = self.models_folder / f"{path.stem}_ncnn_model"
        output.mkdir(exist_ok=True)
        return {
            "success": True,
            "ncnn_path": str(output),
            "artifact_sha256": "b" * 64,
            "export_time": 0.1,
        }

    def _get_ncnn_path(self, path):
        return self.models_folder / f"{path.stem}_ncnn_model"


@pytest.fixture
def fake_manager(tmp_path, monkeypatch):
    FakeModelManager.models_root = tmp_path
    FakeModelManager.export_calls = 0
    FakeModelManager.last_init_kwargs = {}
    FakeModelManager.validation = {
        "valid": True,
        "model_type": "custom",
        "task": "detect",
        "smarttracker_supported": True,
        "compatibility_notes": [],
        "num_classes": 1,
        "class_names": ["target"],
        "is_custom": True,
    }
    (tmp_path / "demo.pt").write_bytes(b"model")
    monkeypatch.setattr(add_model, "ModelManager", FakeModelManager)
    return FakeModelManager


def test_download_and_validation_do_not_export_ncnn_by_default(fake_manager, capsys):
    result = add_model.main(["--model-name", "demo.pt", "--trust-model"])

    assert result == 0
    assert fake_manager.export_calls == 0
    assert "NCNN export was not requested" in capsys.readouterr().out


def test_ncnn_export_requires_explicit_flag(fake_manager):
    result = add_model.main(
        ["--model-name", "demo.pt", "--trust-model", "--export-ncnn"]
    )

    assert result == 0
    assert fake_manager.export_calls == 1


def test_cli_rejects_loadable_but_unsupported_model_task(fake_manager, capsys):
    fake_manager.validation = {
        **fake_manager.validation,
        "task": "segment",
        "smarttracker_supported": False,
        "compatibility_notes": ["SmartTracker supports detect/obb only."],
    }

    result = add_model.main(["--model-name", "demo.pt", "--trust-model"])

    assert result == 1
    assert "SmartTracker supports only detect/obb" in capsys.readouterr().out


def test_remote_download_option_is_not_exposed():
    help_text = add_model._build_parser().format_help()

    assert "--download-url" not in help_text


def test_cli_uses_grouped_smarttracker_model_policy(fake_manager, monkeypatch):
    monkeypatch.setattr(
        add_model.Parameters,
        "SmartTracker",
        {
            "SMART_TRACKER_MODEL_MAX_BYTES": 1234567,
            "SMART_TRACKER_MODEL_TRUST_POLICY": "digest_required",
            "SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS": 321,
        },
    )

    assert add_model.main(["--model-name", "demo.pt", "--trust-model"]) == 2
    digest = hashlib.sha256((fake_manager.models_root / "demo.pt").read_bytes()).hexdigest()
    assert add_model.main(
        ["--model-name", "demo.pt", "--trust-model", "--sha256", digest]
    ) == 0
    assert fake_manager.last_init_kwargs == {
        "max_model_bytes": 1234567,
        "trust_policy": "digest_required",
        "ncnn_export_timeout_seconds": 321,
    }


def test_cli_keeps_descriptor_binding_across_interactive_approval(
    tmp_path,
    monkeypatch,
    capsys,
):
    manager = RealModelManager(models_folder=str(tmp_path))
    model = tmp_path / "demo.pt"
    model.write_bytes(b"operator-observed")
    model.chmod(0o600)
    replacement = tmp_path / "replacement.pt"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or FakeModelManager.validation,
    )
    monkeypatch.setattr(add_model, "ModelManager", lambda **_kwargs: manager)
    monkeypatch.setattr(
        add_model.sys,
        "stdin",
        SimpleNamespace(isatty=lambda: True),
    )

    def approve_after_swap(_prompt):
        os.replace(replacement, model)
        return "y"

    monkeypatch.setattr("builtins.input", approve_after_swap)

    result = add_model.main(["--model-name", "demo.pt"])

    assert result == 1
    assert "canonical store binding" in capsys.readouterr().out
    assert inspection_calls == []


def test_cli_help_imports_from_repo_root_without_pythonpath():
    result = subprocess.run(
        [sys.executable, str(Path(add_model.__file__).resolve()), "--help"],
        cwd=Path(add_model.__file__).resolve().parent,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--trust-model" in result.stdout
