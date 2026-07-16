"""Tests for machine-readable AI and model readiness diagnostics."""

from __future__ import annotations

import json
import importlib.util
import shutil
import subprocess
from pathlib import Path

from classes.model_artifact_policy import ModelProvenanceStore, sha256_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "check-ai-runtime.sh"
PROBE_MODULE_PATH = PROJECT_ROOT / "scripts" / "setup" / "ai_runtime_probe.py"


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("ai_runtime_probe_test", PROBE_MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_backend_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    package = root / "src" / "classes" / "backends"
    package.mkdir(parents=True)
    (root / "src" / "classes" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(
        PROJECT_ROOT / "src" / "classes" / "model_artifact_policy.py",
        root / "src" / "classes" / "model_artifact_policy.py",
    )
    (package / "__init__.py").write_text(
        """
from enum import Enum
from pathlib import Path
import numpy as np

from classes.model_artifact_policy import ModelProvenanceStore

class DevicePreference(Enum):
    CPU = "cpu"
    CUDA = "cuda"

class FakeBackend:
    is_available = True
    def __init__(self, config):
        self.config = config
    def load_model(self, model_path, device, fallback_enabled, context):
        if self.config.get("TEST_NOISY_STDOUT"):
            print("upstream-loader-noise: not probe JSON")
        artifact = Path(model_path)
        if not artifact.is_absolute():
            artifact = Path.cwd() / artifact
        record = ModelProvenanceStore(artifact.parent).verify_pt(artifact)
        effective = self.config.get("TEST_EFFECTIVE_DEVICE")
        if effective is None:
            effective = "cuda" if device is DevicePreference.CUDA else "cpu"
        runtime = {
            "model_path": model_path,
            "effective_device": effective,
            "context": context,
            "fallback_enabled": fallback_enabled,
            "model_provenance": {
                "verified": True,
                "artifact_type": "pt",
                "sha256": record["sha256"],
                "models_root": str(artifact.parent.resolve()),
                "registry_path": str(
                    ModelProvenanceStore(artifact.parent).registry_path
                ),
                "source": record["source"],
                "trust_method": record["trust_method"],
                "observed_sha256": record["observed_sha256"],
                "publisher_sha256": record["publisher_sha256"],
                "registration_receipt": record["registration_receipt"],
            },
        }
        if self.config.get("TEST_OMIT_PROVENANCE"):
            runtime.pop("model_provenance")
        return runtime
    def get_model_task(self):
        return self.config.get("TEST_TASK", "detect")
    def detect(self, frame, conf, iou, max_det):
        if self.config.get("TEST_INFERENCE_FAILURE"):
            raise RuntimeError("forced first inference failure")
        assert isinstance(frame, np.ndarray)
        assert frame.shape == (64, 64, 3)
        assert frame.dtype == np.uint8
        assert not frame.any()
        assert conf == 0.99
        assert iou == 0.3
        assert max_det == 1
        return self.config.get("TEST_RESULT_MODE", "detect"), []
    def detect_and_track(self, *args, **kwargs):
        raise AssertionError("tracking must not run in the bounded inference probe")
    def unload_model(self):
        pass

def create_backend(backend_name, config):
    if backend_name != "fake":
        raise ValueError(backend_name)
    return FakeBackend(config)
""",
        encoding="utf-8",
    )
    models = root / "models"
    models.mkdir(mode=0o700)
    models.chmod(0o700)
    model_path = models / "model.pt"
    model_path.write_bytes(b"fake-model")
    model_path.chmod(0o600)
    digest = sha256_file(model_path)
    ModelProvenanceStore(models).trust_pt(
        model_path,
        sha256=digest,
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=digest,
    )
    return root


def test_ai_runtime_check_emits_machine_readable_readiness(tmp_path):
    report_path = tmp_path / "ai-readiness.json"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--json", "--report-json", str(report_path)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == json.loads(report_path.read_text(encoding="utf-8"))
    assert report_path.stat().st_mode & 0o777 == 0o600
    assert set(payload["readiness"]) == {
        "required_modules_ready",
        "model_candidate_ready",
        "model_load_ready",
        "model_provenance_ready",
        "first_inference_ready",
        "configured_inference_ready",
        "tracking_ready",
        "claim",
        "reason",
    }
    assert set(payload["model_probe"]) >= {
        "attempted",
        "candidate_available",
        "load_ready",
        "provenance_ready",
        "model_provenance",
        "inference_attempted",
        "first_inference_ready",
        "inference",
        "tracking_probe",
        "task",
        "runtime",
        "reason",
        "timed_out",
    }


def test_required_mode_exit_matches_reported_configured_inference_readiness():
    probe = subprocess.run(
        ["bash", str(SCRIPT), "--json", "--require-smart-tracker"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = json.loads(probe.stdout)

    assert (probe.returncode == 0) is payload["readiness"][
        "configured_inference_ready"
    ]


def test_model_probe_loads_backend_and_runs_deterministic_first_inference(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": True,
        "SMART_TRACKER_FALLBACK_TO_CPU": False,
        "SMART_TRACKER_GPU_MODEL_PATH": "models/model.pt",
        "TEST_TASK": "detect",
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["attempted"] is True
    assert result["candidate_available"] is True
    assert result["load_ready"] is True
    assert result["provenance_ready"] is True
    assert result["inference_attempted"] is True
    assert result["first_inference_ready"] is True
    assert result["task"] == "detect"
    assert result["runtime"]["effective_device"] == "cuda"
    assert result["model_provenance"]["verified"] is True
    assert result["model_provenance"]["artifact_type"] == "pt"
    assert result["model_provenance"]["trust_method"] == "expected_sha256"
    assert result["inference"] == {
        "method": "detect",
        "input_shape": [64, 64, 3],
        "input_fill": 0,
        "confidence": 0.99,
        "iou": 0.3,
        "max_detections": 1,
        "result_mode": "detect",
        "detection_count": 0,
    }
    assert result["tracking_probe"] == {
        "attempted": False,
        "ready": None,
        "reason": "not_probed_no_offline_side_effect_contract",
    }


def test_model_probe_uses_private_result_channel_when_loader_writes_stdout(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/model.pt",
        "TEST_NOISY_STDOUT": True,
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["first_inference_ready"] is True
    assert result["reason"] == "first_inference_succeeded"
    assert "upstream-loader-noise: not probe JSON" in result["child_stdout"]


def test_model_probe_rejects_unsupported_task_and_gpu_policy_violation(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    base = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": True,
        "SMART_TRACKER_FALLBACK_TO_CPU": False,
        "SMART_TRACKER_GPU_MODEL_PATH": "models/model.pt",
    }

    unsupported = module.probe_smart_tracker_model(
        root, {**base, "TEST_TASK": "segment"}, timeout_seconds=5
    )
    wrong_device = module.probe_smart_tracker_model(
        root,
        {**base, "TEST_TASK": "detect", "TEST_EFFECTIVE_DEVICE": "cpu"},
        timeout_seconds=5,
    )

    assert unsupported["first_inference_ready"] is False
    assert unsupported["inference_attempted"] is False
    assert unsupported["reason"] == "unsupported_model_task"
    assert wrong_device["first_inference_ready"] is False
    assert wrong_device["inference_attempted"] is False
    assert wrong_device["reason"] == "gpu_required_unavailable"


def test_model_probe_rejects_first_inference_failure(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/model.pt",
        "TEST_INFERENCE_FAILURE": True,
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["load_ready"] is True
    assert result["inference_attempted"] is True
    assert result["first_inference_ready"] is False
    assert result["reason"] == "first_inference_failed"
    assert "forced first inference failure" in result["error"]


def test_model_probe_rejects_unverified_runtime_artifact(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    (root / "models" / ".model-provenance.json").unlink()
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/model.pt",
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["candidate_available"] is True
    assert result["attempted"] is True
    assert result["load_ready"] is False
    assert result["provenance_ready"] is False
    assert result["first_inference_ready"] is False
    assert result["reason"] == "model_load_failed"
    assert "not trusted" in result["error"]


def test_model_probe_requires_backend_provenance_metadata(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/model.pt",
        "TEST_OMIT_PROVENANCE": True,
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["load_ready"] is True
    assert result["provenance_ready"] is False
    assert result["inference_attempted"] is False
    assert result["first_inference_ready"] is False
    assert result["reason"] == "model_provenance_unverified"


def test_model_probe_rejects_invalid_detection_result_mode(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    config = {
        "DETECTION_BACKEND": "fake",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/model.pt",
        "TEST_RESULT_MODE": "tracking",
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["load_ready"] is True
    assert result["provenance_ready"] is True
    assert result["inference_attempted"] is True
    assert result["first_inference_ready"] is False
    assert result["reason"] == "first_inference_failed"
    assert "unsupported result mode 'tracking'" in result["error"]


def test_model_probe_does_not_spawn_loader_without_local_artifact(tmp_path):
    module = _load_probe_module()
    root = tmp_path / "project"
    root.mkdir()
    config = {
        "SMART_TRACKER_USE_GPU": True,
        "SMART_TRACKER_FALLBACK_TO_CPU": False,
        "SMART_TRACKER_GPU_MODEL_PATH": "models/missing.pt",
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["attempted"] is False
    assert result["candidate_available"] is False
    assert result["reason"] == "model_required"


def test_model_probe_does_not_spawn_loader_for_symlink_alias(tmp_path):
    module = _load_probe_module()
    root = _fake_backend_root(tmp_path)
    alias = root / "models" / "alias.pt"
    alias.symlink_to(root / "models" / "model.pt")
    config = {
        "SMART_TRACKER_USE_GPU": True,
        "SMART_TRACKER_FALLBACK_TO_CPU": False,
        "SMART_TRACKER_GPU_MODEL_PATH": "models/alias.pt",
    }

    result = module.probe_smart_tracker_model(root, config, timeout_seconds=5)

    assert result["attempted"] is False
    assert result["candidate_available"] is False
    assert result["reason"] == "model_required"


def test_digest_required_probe_rejects_runtime_without_publisher_evidence():
    module = _load_probe_module()
    digest = "a" * 64
    ready, provenance = module._runtime_model_provenance(
        {
            "model_provenance": {
                "verified": True,
                "artifact_type": "pt",
                "sha256": digest,
                "observed_sha256": digest,
                "publisher_sha256": digest,
                "trust_method": "expected_sha256",
                "registration_receipt": {
                    "schema_version": 1,
                    "observed_sha256": digest,
                    "publisher_sha256": digest,
                },
            }
        },
        trust_policy="digest_required",
    )

    assert ready is False
    assert provenance["sha256"] == digest
