"""Tests for legacy recording route helper extraction."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import cv2
import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from classes import api_legacy_recording_routes as routes


pytestmark = [pytest.mark.unit]


class FakeCap:
    def __init__(self, width=1280, height=720) -> None:
        self.values = {
            cv2.CAP_PROP_FRAME_WIDTH: width,
            cv2.CAP_PROP_FRAME_HEIGHT: height,
        }

    def get(self, prop):
        return self.values.get(prop)


class FakeRecordingManager:
    def __init__(self, output_dir) -> None:
        self._output_dir = str(output_dir)
        self.is_active = False
        self.status = {"state": "idle", "is_recording": False}
        self.start_calls = []
        self.pause_calls = 0
        self.resume_calls = 0
        self.stop_calls = 0
        self.delete_calls = []
        self.delete_result = {"status": "success", "message": "deleted"}
        self.include_osd_calls = []

    def start(self, source_fps, source_w, source_h):
        self.start_calls.append((source_fps, source_w, source_h))
        self.is_active = True
        return {"status": "success", "filename": "clip.mp4"}

    def pause(self):
        self.pause_calls += 1
        return {"status": "success", "state": "paused"}

    def resume(self):
        self.resume_calls += 1
        return {"status": "success", "state": "recording"}

    def stop(self):
        self.stop_calls += 1
        self.is_active = False
        return {"status": "success", "filename": "clip.mp4"}

    def list_recordings(self):
        return [{"filename": "clip.mp4", "size": 10}]

    def delete_recording(self, filename):
        self.delete_calls.append(filename)
        return self.delete_result

    def set_include_osd(self, value):
        self.include_osd_calls.append(value)


class FakeRequest:
    def __init__(self, headers=None) -> None:
        self.headers = headers or {}


def make_handler(tmp_path, *, manager=True, storage=True, video=True):
    recording_manager = FakeRecordingManager(tmp_path) if manager else None
    storage_manager = (
        SimpleNamespace(status={"free_bytes": 1024, "state": "ok"})
        if storage
        else None
    )
    video_handler = (
        SimpleNamespace(fps=24.5, cap=FakeCap(width=1280, height=720))
        if video
        else None
    )
    app_controller = SimpleNamespace(
        recording_manager=recording_manager,
        storage_manager=storage_manager,
        video_handler=video_handler,
    )
    return SimpleNamespace(
        app_controller=app_controller,
        logger=logging.getLogger("test.api_legacy_recording_routes"),
    )


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_start_and_toggle_preserve_video_dimension_probe(tmp_path):
    handler = make_handler(tmp_path)
    manager = handler.app_controller.recording_manager

    started = response_body(await routes.start_recording(handler))
    toggled_stop = response_body(await routes.toggle_recording(handler))
    toggled_start = response_body(await routes.toggle_recording(handler))

    assert started["status"] == "success"
    assert started["filename"] == "clip.mp4"
    assert toggled_stop["status"] == "success"
    assert toggled_start["status"] == "success"
    assert manager.start_calls == [(24.5, 1280, 720), (24.5, 1280, 720)]
    assert manager.stop_calls == 1


@pytest.mark.asyncio
async def test_recording_mutations_return_503_when_manager_unavailable(tmp_path):
    handler = make_handler(tmp_path, manager=False)

    with pytest.raises(HTTPException) as start_exc:
        await routes.start_recording(handler)
    with pytest.raises(HTTPException) as pause_exc:
        await routes.pause_recording(handler)
    with pytest.raises(HTTPException) as delete_exc:
        await routes.delete_recording_file(handler, "clip.mp4")

    assert start_exc.value.status_code == 503
    assert start_exc.value.detail == "Recording not available (ENABLE_RECORDING is false)"
    assert pause_exc.value.status_code == 503
    assert pause_exc.value.detail == "Recording not available"
    assert delete_exc.value.status_code == 503
    assert delete_exc.value.detail == "Recording not available"


@pytest.mark.asyncio
async def test_status_storage_pause_resume_stop_and_list_shapes(tmp_path):
    handler = make_handler(tmp_path)
    manager = handler.app_controller.recording_manager

    status = response_body(await routes.get_recording_status(handler))
    storage = response_body(await routes.get_storage_status(handler))
    paused = response_body(await routes.pause_recording(handler))
    resumed = response_body(await routes.resume_recording(handler))
    stopped = response_body(await routes.stop_recording(handler))
    recordings = response_body(await routes.list_recordings(handler))

    assert status["recording"] == manager.status
    assert status["storage"] == {"free_bytes": 1024, "state": "ok"}
    assert status["available"] is True
    assert storage["storage"] == {"free_bytes": 1024, "state": "ok"}
    assert storage["available"] is True
    assert paused["state"] == "paused"
    assert resumed["state"] == "recording"
    assert stopped["filename"] == "clip.mp4"
    assert recordings["recordings"] == [{"filename": "clip.mp4", "size": 10}]
    assert recordings["count"] == 1
    assert manager.pause_calls == 1
    assert manager.resume_calls == 1
    assert manager.stop_calls == 1

    unavailable = response_body(
        await routes.get_recording_status(make_handler(tmp_path, manager=False, storage=False))
    )
    unavailable_storage = response_body(
        await routes.get_storage_status(make_handler(tmp_path, storage=False))
    )
    assert unavailable["recording"] == {"state": "unavailable"}
    assert unavailable["storage"] == {}
    assert unavailable["available"] is False
    assert unavailable_storage["storage"] == {}
    assert unavailable_storage["available"] is False


@pytest.mark.asyncio
async def test_download_recording_full_file_and_range_headers(tmp_path):
    handler = make_handler(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0123456789")

    full_response = await routes.download_recording(handler, "../clip.mp4")
    range_response = await routes.download_recording(
        handler,
        "clip.mp4",
        FakeRequest(headers={"range": "bytes=2-5"}),
    )

    assert isinstance(full_response, FileResponse)
    assert full_response.path == str(clip)
    assert full_response.media_type == "video/mp4"
    assert full_response.headers["accept-ranges"] == "bytes"
    assert isinstance(range_response, StreamingResponse)
    assert range_response.status_code == 206
    assert range_response.media_type == "video/mp4"
    assert range_response.headers["content-range"] == "bytes 2-5/10"
    assert range_response.headers["content-length"] == "4"
    assert range_response.headers["accept-ranges"] == "bytes"


@pytest.mark.asyncio
async def test_download_recording_errors_preserve_legacy_mapping(tmp_path):
    handler = make_handler(tmp_path)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0123456789")

    with pytest.raises(HTTPException) as missing_exc:
        await routes.download_recording(handler, "../../missing.mp4")
    with pytest.raises(HTTPException) as bad_range_exc:
        await routes.download_recording(
            handler,
            "clip.mp4",
            FakeRequest(headers={"range": "bytes=bad-5"}),
        )

    assert missing_exc.value.status_code == 404
    assert missing_exc.value.detail == "Recording not found: missing.mp4"
    assert bad_range_exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_recording_and_include_osd_preserve_legacy_semantics(tmp_path):
    handler = make_handler(tmp_path)
    manager = handler.app_controller.recording_manager

    deleted = response_body(await routes.delete_recording_file(handler, "clip.mp4"))
    include_true = response_body(await routes.set_recording_include_osd(handler, "YES"))
    include_false = response_body(await routes.set_recording_include_osd(handler, "disabled"))

    assert deleted["status"] == "success"
    assert manager.delete_calls == ["clip.mp4"]
    assert include_true["status"] == "success"
    assert include_true["include_osd"] is True
    assert include_true["message"] == "OSD recording enabled"
    assert include_false["include_osd"] is False
    assert include_false["message"] == "OSD recording disabled"
    assert manager.include_osd_calls == [True, False]

    manager.delete_result = {"status": "error", "message": "Recording not found"}
    with pytest.raises(HTTPException) as not_found_exc:
        await routes.delete_recording_file(handler, "missing.mp4")
    assert not_found_exc.value.status_code == 404
    assert not_found_exc.value.detail == "Recording not found"

    manager.delete_result = {"status": "error", "message": "Active recording"}
    with pytest.raises(HTTPException) as active_exc:
        await routes.delete_recording_file(handler, "active.mp4")
    assert active_exc.value.status_code == 400
    assert active_exc.value.detail == "Active recording"
