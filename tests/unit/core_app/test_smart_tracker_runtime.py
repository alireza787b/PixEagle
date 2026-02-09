from pathlib import Path

from classes.parameters import Parameters
from classes.smart_tracker import SmartTracker
import classes.smart_tracker as smart_tracker_module


class FakeYOLO:
    fail_on_init = set()
    fail_on_to_cuda = set()

    def __init__(self, model_path):
        self.model_path = str(model_path)
        self.ckpt_path = self.model_path if self.model_path.endswith(".pt") else None
        self.names = {0: "person"}
        self.task = "detect"
        self.device = "cpu"
        if self.model_path in self.fail_on_init:
            raise RuntimeError(f"forced init failure for {self.model_path}")

    def to(self, device):
        if device == "cuda" and self.model_path in self.fail_on_to_cuda:
            raise RuntimeError(f"forced cuda transfer failure for {self.model_path}")
        self.device = device
        return self

    def track(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return []

    def predict(self, *args, **kwargs):  # pragma: no cover - not used in these tests
        return []


class DummyAppController:
    def __init__(self):
        self.tracker = None
        self.tracking_started = False


def _make_ncnn_dir(base_dir: Path, name: str) -> Path:
    ncnn_dir = base_dir / name
    ncnn_dir.mkdir(parents=True, exist_ok=True)
    (ncnn_dir / "model.bin").write_bytes(b"bin")
    (ncnn_dir / "model.param").write_text("param", encoding="utf-8")
    return ncnn_dir


def _configure(monkeypatch, gpu_path: Path, cpu_path: Path, use_gpu: bool = True, fallback_to_cpu: bool = True):
    monkeypatch.setattr(smart_tracker_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(smart_tracker_module, "YOLO", FakeYOLO)

    FakeYOLO.fail_on_init = set()
    FakeYOLO.fail_on_to_cuda = set()

    monkeypatch.setattr(
        Parameters,
        "SmartTracker",
        {
            "SMART_TRACKER_USE_GPU": use_gpu,
            "SMART_TRACKER_FALLBACK_TO_CPU": fallback_to_cpu,
            "SMART_TRACKER_GPU_MODEL_PATH": str(gpu_path.as_posix()),
            "SMART_TRACKER_CPU_MODEL_PATH": str(cpu_path.as_posix()),
            "TRACKER_TYPE": "bytetrack",
            "ENABLE_PREDICTION_BUFFER": False,
            "ENABLE_APPEARANCE_MODEL": False,
            "SMART_TRACKER_SHOW_FPS": False,
        },
        raising=False,
    )


def test_init_cpu_mode_prefers_ncnn(monkeypatch, tmp_path):
    pt_model = tmp_path / "demo.pt"
    pt_model.write_bytes(b"pt")
    ncnn_model = _make_ncnn_dir(tmp_path, "demo_ncnn_model")

    _configure(monkeypatch, gpu_path=pt_model, cpu_path=ncnn_model, use_gpu=False, fallback_to_cpu=True)
    monkeypatch.setattr(SmartTracker, "_cuda_available", lambda self: True)

    tracker = SmartTracker(DummyAppController())
    runtime = tracker.get_runtime_info()

    assert runtime["backend"] == "cpu_ncnn"
    assert runtime["effective_device"] == "cpu"
    assert runtime["model_path"] == str(ncnn_model.as_posix())
    assert runtime["fallback_occurred"] is False


def test_gpu_failure_falls_back_to_cpu_ncnn(monkeypatch, tmp_path):
    gpu_pt = tmp_path / "gpu.pt"
    gpu_pt.write_bytes(b"gpu")
    cpu_ncnn = _make_ncnn_dir(tmp_path, "gpu_ncnn_model")

    _configure(monkeypatch, gpu_path=gpu_pt, cpu_path=cpu_ncnn, use_gpu=True, fallback_to_cpu=True)
    monkeypatch.setattr(SmartTracker, "_cuda_available", lambda self: True)
    FakeYOLO.fail_on_to_cuda = {str(gpu_pt.as_posix())}

    tracker = SmartTracker(DummyAppController())
    runtime = tracker.get_runtime_info()

    assert runtime["backend"] == "cpu_ncnn"
    assert runtime["effective_device"] == "cpu"
    assert runtime["fallback_occurred"] is True
    assert runtime["fallback_reason"] is not None


def test_switch_model_cpu_prefers_ncnn_sibling(monkeypatch, tmp_path):
    base_pt = tmp_path / "base.pt"
    base_pt.write_bytes(b"base")
    base_ncnn = _make_ncnn_dir(tmp_path, "base_ncnn_model")

    _configure(monkeypatch, gpu_path=base_pt, cpu_path=base_ncnn, use_gpu=False, fallback_to_cpu=True)
    monkeypatch.setattr(SmartTracker, "_cuda_available", lambda self: True)

    tracker = SmartTracker(DummyAppController())

    next_pt = tmp_path / "next.pt"
    next_pt.write_bytes(b"next")
    next_ncnn = _make_ncnn_dir(tmp_path, "next_ncnn_model")

    result = tracker.switch_model(str(next_pt.as_posix()), device="cpu")

    assert result["success"] is True
    assert result["model_info"]["backend"] == "cpu_ncnn"
    assert tracker.get_runtime_info()["model_path"] == str(next_ncnn.as_posix())


def test_switch_model_cpu_uses_pt_when_ncnn_missing(monkeypatch, tmp_path):
    base_pt = tmp_path / "base.pt"
    base_pt.write_bytes(b"base")
    base_ncnn = _make_ncnn_dir(tmp_path, "base_ncnn_model")

    _configure(monkeypatch, gpu_path=base_pt, cpu_path=base_ncnn, use_gpu=False, fallback_to_cpu=True)
    monkeypatch.setattr(SmartTracker, "_cuda_available", lambda self: False)

    tracker = SmartTracker(DummyAppController())

    next_pt = tmp_path / "next_no_ncnn.pt"
    next_pt.write_bytes(b"next")

    result = tracker.switch_model(str(next_pt.as_posix()), device="cpu")

    assert result["success"] is True
    assert result["model_info"]["backend"] == "cpu_torch"
    assert tracker.get_runtime_info()["model_path"] == str(next_pt.as_posix())
