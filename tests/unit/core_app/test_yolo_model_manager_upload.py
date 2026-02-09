import pytest

from classes.yolo_model_manager import YOLOModelManager
import classes.yolo_model_manager as yolo_model_manager_module


@pytest.mark.asyncio
async def test_upload_model_returns_consistent_response_shape(tmp_path, monkeypatch):
    manager = YOLOModelManager(yolo_folder=str(tmp_path))

    validation = {
        "valid": True,
        "num_classes": 3,
        "class_names": ["a", "b", "c"],
        "is_custom": True,
        "task": "detect",
        "output_geometry": "aabb",
        "smarttracker_supported": True,
        "compatibility_notes": [],
    }

    monkeypatch.setattr(manager, "validate_model", lambda _: validation)

    async def fake_export(_):
        return {
            "success": True,
            "ncnn_path": str((tmp_path / "demo_ncnn_model").as_posix()),
            "export_time": 0.12,
        }

    monkeypatch.setattr(manager, "_export_async", fake_export)

    discovered = {
        "demo": {
            "name": "DEMO",
            "path": str((tmp_path / "demo.pt").as_posix()),
            "has_ncnn": True,
            "ncnn_path": str((tmp_path / "demo_ncnn_model").as_posix()),
            "num_classes": 3,
            "class_names": ["a", "b", "c"],
        }
    }
    monkeypatch.setattr(manager, "discover_models", lambda force_rescan=False: discovered)

    result = await manager.upload_model(
        file_data=b"model-bytes",
        filename="demo.pt",
        auto_export_ncnn=True,
    )

    assert result["success"] is True
    assert result["model_id"] == "demo"
    assert "message" in result and result["message"]
    assert result["model_info"]["path"].endswith("demo.pt")
    assert result["ncnn_exported"] is True
    assert result["ncnn_export"]["success"] is True
    assert result["ncnn_path"].endswith("demo_ncnn_model")


def test_export_to_ncnn_restores_cuda_visible_devices_on_failure(tmp_path, monkeypatch):
    manager = YOLOModelManager(yolo_folder=str(tmp_path))
    pt_file = tmp_path / "demo.pt"
    pt_file.write_bytes(b"pt")

    class FakeYOLO:
        def __init__(self, _):
            pass

        def export(self, format="ncnn"):  # noqa: ARG002
            import os

            # Simulate Ultralytics side effect that can poison later CUDA runtime.
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
            raise RuntimeError("forced export failure")

    monkeypatch.setattr(yolo_model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(yolo_model_manager_module, "YOLO", FakeYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "forced export failure" in result["error"]
    assert yolo_model_manager_module.os.environ.get("CUDA_VISIBLE_DEVICES") == "0"


def test_export_to_ncnn_returns_clear_error_when_pnnx_missing(tmp_path, monkeypatch):
    manager = YOLOModelManager(yolo_folder=str(tmp_path))
    pt_file = tmp_path / "demo.pt"
    pt_file.write_bytes(b"pt")

    monkeypatch.setattr(yolo_model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: False)

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "pnnx" in result["error"].lower()
