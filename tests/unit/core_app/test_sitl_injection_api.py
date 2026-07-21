"""Tests for validation-only SITL injection API contracts."""

import json
import logging

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi import Response

from classes.fastapi_handler import FastAPIHandler, SITLTrackerOutputInjection
from classes.fastapi_handler import SITLVideoStallInjection
from classes.fastapi_handler import SITLCommanderPublishFailureInjection
from classes.fastapi_handler import SITLMavsdkDisconnectInjection
from classes.fastapi_handler import SITLMavlink2RestTimeoutInjection


class _ControllerProbe:
    def __init__(self):
        self.following_active = True
        self.calls = []

    async def inject_tracker_output_for_validation(self, tracker_output, *, source):
        self.calls.append((tracker_output, source))
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": True,
            "injection": {
                "source": source,
                "tracker_id": tracker_output.tracker_id,
                "data_type": tracker_output.data_type.value,
                "input_tracking_active": tracker_output.tracking_active,
                "processed_tracking_active": tracker_output.tracking_active,
                "processed_usable_for_following": tracker_output.raw_data.get(
                    "usable_for_following"
                ),
            },
            "command_intent": None,
            "offboard_commander": {
                "exists": True,
                "running": True,
                "command_publication_source": "offboard_commander",
            },
            "timestamp": 1.0,
        }

    async def inject_video_stall_for_validation(self, frame_status, *, source):
        self.calls.append((frame_status, source))
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": True,
            "injection": {
                "source": source,
                "tracker_requires_video": True,
                "frame_status": frame_status,
            },
            "command_intent": {
                "profile_name": "mc_velocity_position",
                "control_type": "velocity_body_offboard",
                "fields": {
                    "vel_body_down": 0.0,
                    "yawspeed_deg_s": 0.0,
                },
                "source": "mc_velocity_position",
                "reason": "mc_velocity_position_inactive_hold",
                "created_at_monotonic_s": 1.0,
                "created_at_utc": "2026-06-02T00:00:00",
            },
            "offboard_commander": {
                "exists": True,
                "running": True,
                "command_publication_source": "offboard_commander",
            },
            "timestamp": 1.0,
        }

    async def inject_commander_publish_failure_for_validation(
        self,
        *,
        failure_count,
        reason,
        source,
        failure_mode="recorded_failure",
        metadata,
    ):
        self.calls.append((failure_count, reason, source, failure_mode, metadata))
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": False,
            "injection": {
                "source": source,
                "failure_mode": failure_mode,
                "requested_failure_count": failure_count,
                "applied_failure_count": failure_count,
                "failure_reason": reason,
                "metadata": metadata,
            },
            "offboard_commander": {
                "exists": True,
                "running": False,
                "health_state": "failed",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "consecutive_failures": 3,
                "failure_policy_triggered": True,
                "failure_policy_trigger_count": 1,
            },
            "offboard_commander_before": {
                "exists": True,
                "running": True,
                "health_state": "running",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "failure_policy_triggered": False,
            },
            "offboard_commander_after": {
                "exists": True,
                "running": False,
                "health_state": "failed",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "consecutive_failures": 3,
                "failure_policy_triggered": True,
                "failure_policy_trigger_count": 1,
            },
            "offboard_commander_failure": {
                "failure_policy_triggered": True,
                "consecutive_failures": 3,
                "disconnect_result": {"errors": []},
            },
            "disconnect_result": {"errors": []},
            "timestamp": 1.0,
        }

    async def inject_mavsdk_disconnect_for_validation(
        self,
        *,
        failure_count,
        reason,
        source,
        failure_mode,
        metadata,
    ):
        self.calls.append((failure_count, reason, source, failure_mode, metadata))
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": False,
            "injection": {
                "source": source,
                "failure_mode": failure_mode,
                "requested_failure_count": failure_count,
                "applied_failure_count": failure_count,
                "failure_reason": reason,
                "metadata": metadata,
            },
            "px4_connection_before": {
                "status": "connected",
                "connected": True,
                "active_mode": True,
                "validation_disconnect_active": False,
                "disconnect_count": 0,
                "system_address": "udpin://127.0.0.1:14540",
                "uses_mavlink2rest": True,
            },
            "px4_connection_after": {
                "status": "validation_disconnected",
                "connected": False,
                "active_mode": False,
                "validation_disconnect_active": True,
                "disconnect_reason": reason,
                "disconnect_source": source,
                "disconnect_count": 1,
                "last_error": f"MAVSDK disconnected - {reason}",
                "system_address": "udpin://127.0.0.1:14540",
                "uses_mavlink2rest": True,
            },
            "offboard_commander": {
                "exists": True,
                "running": False,
                "health_state": "failed",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "consecutive_failures": 3,
                "last_publish_success": False,
                "last_publish_reason": reason,
                "failure_policy_triggered": True,
                "failure_policy_trigger_count": 1,
            },
            "offboard_commander_before": {
                "exists": True,
                "running": True,
                "health_state": "running",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "failure_policy_triggered": False,
            },
            "offboard_commander_after": {
                "exists": True,
                "running": False,
                "health_state": "failed",
                "command_publication_source": "offboard_commander",
                "command_failure_threshold": 3,
                "consecutive_failures": 3,
                "last_publish_success": False,
                "last_publish_reason": reason,
                "failure_policy_triggered": True,
                "failure_policy_trigger_count": 1,
            },
            "offboard_commander_failure": {
                "failure_policy_triggered": True,
                "consecutive_failures": 3,
                "last_publish_reason": reason,
                "disconnect_result": {
                    "errors": [f"Failed to stop offboard mode: MAVSDK disconnected - {reason}"],
                },
            },
            "disconnect_result": {
                "steps": ["Offboard commander stopped"],
                "errors": [f"Failed to stop offboard mode: MAVSDK disconnected - {reason}"],
            },
            "timestamp": 1.0,
        }

    async def inject_mavlink2rest_timeout_for_validation(
        self,
        *,
        failure_count,
        reason,
        force_stale,
        timeout_window_s,
        source,
        metadata,
    ):
        self.calls.append(
            (failure_count, reason, force_stale, timeout_window_s, source, metadata)
        )
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "injection": {
                "source": source,
                "requested_failure_count": failure_count,
                "applied_failure_count": failure_count,
                "failure_reason": reason,
                "force_stale": force_stale,
                "timeout_window_s": timeout_window_s,
                "metadata": metadata,
            },
            "mavlink_telemetry": {
                "enabled": True,
                "status": "stale",
                "connection_state": "error",
                "fresh": False,
                "last_success_age_s": 2.1,
                "stale_timeout_s": 2.0,
                "request_timeout_s": 5.0,
                "request_retries": 0,
                "connection_error_count": failure_count,
                "last_error": f"Connection timeout - {reason}",
                "endpoint": "http://127.0.0.1:8088",
                "validation_timeout_active": True,
            },
            "timestamp": 1.0,
        }


def _handler(controller=None):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.app_controller = controller or _ControllerProbe()
    handler.logger = logging.getLogger(__name__)
    return handler


def _request(path="/api/v1/sitl/injections/tracker-output"):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


@pytest.mark.asyncio
async def test_sitl_tracker_output_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)
    handler = _handler()
    request = SITLTrackerOutputInjection(position_2d=(0.0, 0.0))

    response = await handler.inject_sitl_tracker_output(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 403
    assert payload["code"] == "SITL_INJECTIONS_DISABLED"
    assert payload["error"] == "SITL_INJECTIONS_DISABLED"
    assert payload["path"] == "/api/v1/sitl/injections/tracker-output"
    assert payload["request_id"].startswith("pixeagle-sitl-")
    assert isinstance(payload["timestamp"], int)
    assert "message" in payload["detail"]


@pytest.mark.asyncio
async def test_sitl_tracker_output_injection_builds_tracker_output(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLTrackerOutputInjection(
        injection_id="target-loss",
        source="unit.api",
        data_type="position_2d",
        tracker_id="api_probe",
        position_2d=(0.1, -0.2),
        bbox=(10, 20, 30, 40),
        confidence=0.5,
        usable_for_following=False,
        data_is_stale=True,
        freshness_reason="unit_loss",
        has_output=True,
    )

    result = await handler.inject_sitl_tracker_output(request, response)

    assert response.status_code == 202
    assert result["status"] == "accepted"
    assert result["injection"]["source"] == "unit.api"
    tracker_output, source = controller.calls[0]
    assert source == "unit.api"
    assert tracker_output.tracker_id == "api_probe"
    assert tracker_output.position_2d == pytest.approx((0.1, -0.2))
    assert tracker_output.raw_data["usable_for_following"] is False
    assert tracker_output.raw_data["data_is_stale"] is True
    assert tracker_output.raw_data["freshness_reason"] == "unit_loss"
    assert tracker_output.raw_data["sitl_injection_id"] == "target-loss"


@pytest.mark.asyncio
async def test_sitl_tracker_output_injection_dry_run_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLTrackerOutputInjection(
        dry_run=True,
        position_2d=(0.0, 0.0),
    )

    result = await handler.inject_sitl_tracker_output(request, response)

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["reason"] == "dry_run"
    assert controller.calls == []


@pytest.mark.asyncio
async def test_sitl_tracker_output_injection_invalid_type_uses_error_envelope(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    handler = _handler()
    response = Response()
    request = SITLTrackerOutputInjection(
        data_type="not_a_tracker_type",
        position_2d=(0.0, 0.0),
    )

    result = await handler.inject_sitl_tracker_output(request, response)
    payload = json.loads(result.body)

    assert result.status_code == 422
    assert payload["code"] == "INVALID_TRACKER_OUTPUT"
    assert payload["path"] == "/api/v1/sitl/injections/tracker-output"
    assert "Unsupported tracker data_type" in payload["detail"]["message"]


@pytest.mark.asyncio
async def test_sitl_request_validation_errors_use_api_v1_envelope():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "unexpected"),
                "msg": "Extra inputs are not permitted",
                "type": "extra_forbidden",
            }
        ]
    )

    response = await handler._handle_request_validation_error(_request(), exc)
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["path"] == "/api/v1/sitl/injections/tracker-output"
    assert payload["detail"]["validation_errors"][0]["type"] == "extra_forbidden"


@pytest.mark.asyncio
async def test_sitl_video_stall_request_validation_errors_use_api_v1_envelope():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "unexpected"),
                "msg": "Extra inputs are not permitted",
                "type": "extra_forbidden",
            }
        ]
    )

    response = await handler._handle_request_validation_error(
        _request("/api/v1/sitl/injections/video-stall"),
        exc,
    )
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["path"] == "/api/v1/sitl/injections/video-stall"
    assert payload["detail"]["validation_errors"][0]["type"] == "extra_forbidden"


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_request_validation_errors_use_api_v1_envelope():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "failure_mode"),
                "msg": "Input should be 'recorded_failure'",
                "type": "literal_error",
            }
        ]
    )

    response = await handler._handle_request_validation_error(
        _request("/api/v1/sitl/injections/commander-publish-failure"),
        exc,
    )
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["path"] == "/api/v1/sitl/injections/commander-publish-failure"
    assert payload["detail"]["validation_errors"][0]["type"] == "literal_error"


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_request_validation_errors_use_api_v1_envelope():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "failure_mode"),
                "msg": "Input should be 'local_mavsdk_command_disconnect'",
                "type": "literal_error",
            }
        ]
    )

    response = await handler._handle_request_validation_error(
        _request("/api/v1/sitl/injections/mavsdk-disconnect"),
        exc,
    )
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["path"] == "/api/v1/sitl/injections/mavsdk-disconnect"
    assert payload["detail"]["validation_errors"][0]["type"] == "literal_error"


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_request_validation_errors_use_api_v1_envelope():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "failure_count"),
                "msg": "Input should be greater than or equal to 1",
                "type": "greater_than_equal",
            }
        ]
    )

    response = await handler._handle_request_validation_error(
        _request("/api/v1/sitl/injections/mavlink2rest-timeout"),
        exc,
    )
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert payload["code"] == "REQUEST_VALIDATION_ERROR"
    assert payload["path"] == "/api/v1/sitl/injections/mavlink2rest-timeout"
    assert payload["detail"]["validation_errors"][0]["type"] == "greater_than_equal"


@pytest.mark.asyncio
async def test_legacy_request_validation_errors_keep_default_detail_shape():
    handler = _handler()
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "x"),
                "msg": "Field required",
                "type": "missing",
            }
        ]
    )

    response = await handler._handle_request_validation_error(_request("/commands/quit"), exc)
    payload = json.loads(response.body)

    assert response.status_code == 422
    assert "detail" in payload
    assert "code" not in payload


@pytest.mark.asyncio
async def test_sitl_video_stall_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)
    handler = _handler()
    request = SITLVideoStallInjection()

    response = await handler.inject_sitl_video_stall(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 403
    assert payload["code"] == "SITL_INJECTIONS_DISABLED"
    assert payload["path"] == "/api/v1/sitl/injections/video-stall"


@pytest.mark.asyncio
async def test_sitl_video_stall_injection_dispatches_frame_status(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLVideoStallInjection(
        injection_id="stall",
        source="unit.video_stall",
        frame_source="unit_test_video",
        reason="unit_frame_stall",
        consecutive_failures=3,
        metadata={"scenario": "video_stall"},
    )

    result = await handler.inject_sitl_video_stall(request, response)

    assert response.status_code == 202
    assert result["status"] == "accepted"
    assert result["injection"]["source"] == "unit.video_stall"
    assert result["injection"]["frame_status"]["source"] == "unit_test_video"
    assert result["injection"]["frame_status"]["usable_for_following"] is False
    assert result["injection"]["frame_status"]["reason"] == "unit_frame_stall"
    assert result["injection"]["frame_status"]["sitl_injection_id"] == "stall"
    frame_status, source = controller.calls[0]
    assert source == "unit.video_stall"
    assert frame_status["consecutive_failures"] == 3
    assert frame_status["metadata"]["scenario"] == "video_stall"


@pytest.mark.asyncio
async def test_sitl_video_stall_injection_dry_run_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLVideoStallInjection(dry_run=True)

    result = await handler.inject_sitl_video_stall(request, response)

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["reason"] == "dry_run"
    assert controller.calls == []


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)
    handler = _handler()
    request = SITLCommanderPublishFailureInjection()

    response = await handler.inject_sitl_commander_publish_failure(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 403
    assert payload["code"] == "SITL_INJECTIONS_DISABLED"
    assert payload["path"] == "/api/v1/sitl/injections/commander-publish-failure"


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_dispatches(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLCommanderPublishFailureInjection(
        injection_id="commander-failure",
        source="unit.commander",
        failure_count=3,
        reason="unit_publish_failure",
        metadata={"scenario": "commander_publish_failure"},
    )

    result = await handler.inject_sitl_commander_publish_failure(request, response)

    assert response.status_code == 202
    assert result["status"] == "accepted"
    assert result["following_active"] is False
    assert result["injection"]["source"] == "unit.commander"
    assert result["injection"]["failure_mode"] == "recorded_failure"
    assert result["injection"]["applied_failure_count"] == 3
    assert result["offboard_commander_before"]["running"] is True
    assert result["offboard_commander_after"]["health_state"] == "failed"
    failure_count, reason, source, failure_mode, metadata = controller.calls[0]
    assert failure_count == 3
    assert reason == "unit_publish_failure"
    assert source == "unit.commander"
    assert failure_mode == "recorded_failure"
    assert metadata["sitl_injection_id"] == "commander-failure"
    assert metadata["scenario"] == "commander_publish_failure"


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_dry_run_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLCommanderPublishFailureInjection(dry_run=True)

    result = await handler.inject_sitl_commander_publish_failure(request, response)

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["reason"] == "dry_run"
    assert result["injection"]["applied_failure_count"] == 0
    assert controller.calls == []


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_unavailable(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    handler = _handler(controller=object())
    request = SITLCommanderPublishFailureInjection()

    response = await handler.inject_sitl_commander_publish_failure(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 501
    assert payload["code"] == "SITL_INJECTION_UNAVAILABLE"
    assert payload["path"] == "/api/v1/sitl/injections/commander-publish-failure"


@pytest.mark.asyncio
async def test_sitl_commander_publish_failure_injection_rejected(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")

    class RejectingController(_ControllerProbe):
        async def inject_commander_publish_failure_for_validation(self, **_kwargs):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "following_not_active",
                "following_active": False,
                "injection": {
                    "source": "unit.commander",
                    "failure_mode": "recorded_failure",
                    "requested_failure_count": None,
                    "applied_failure_count": 0,
                    "failure_reason": "sitl_commander_publish_failure",
                    "metadata": {},
                },
                "offboard_commander": None,
                "offboard_commander_before": None,
                "offboard_commander_after": None,
                "offboard_commander_failure": None,
                "disconnect_result": None,
                "timestamp": 1.0,
            }

    handler = _handler(controller=RejectingController())
    request = SITLCommanderPublishFailureInjection()

    response = await handler.inject_sitl_commander_publish_failure(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["code"] == "SITL_INJECTION_REJECTED"
    assert payload["detail"]["reason"] == "following_not_active"


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)
    handler = _handler()
    request = SITLMavsdkDisconnectInjection()

    response = await handler.inject_sitl_mavsdk_disconnect(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 403
    assert payload["code"] == "SITL_INJECTIONS_DISABLED"
    assert payload["path"] == "/api/v1/sitl/injections/mavsdk-disconnect"


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_dispatches(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLMavsdkDisconnectInjection(
        injection_id="mavsdk-disconnect",
        source="unit.mavsdk",
        failure_count=3,
        reason="unit_mavsdk_disconnect",
        metadata={"scenario": "mavsdk_disconnect"},
    )

    result = await handler.inject_sitl_mavsdk_disconnect(request, response)

    assert response.status_code == 202
    assert result["status"] == "accepted"
    assert result["following_active"] is False
    assert result["injection"]["source"] == "unit.mavsdk"
    assert result["injection"]["failure_mode"] == "local_mavsdk_command_disconnect"
    assert result["injection"]["applied_failure_count"] == 3
    assert result["px4_connection_before"]["connected"] is True
    assert result["px4_connection_after"]["status"] == "validation_disconnected"
    assert result["px4_connection_after"]["validation_disconnect_active"] is True
    assert result["offboard_commander_before"]["running"] is True
    assert result["offboard_commander_after"]["health_state"] == "failed"
    assert result["disconnect_result"]["errors"] == [
        "Failed to stop offboard mode: MAVSDK disconnected - unit_mavsdk_disconnect"
    ]
    failure_count, reason, source, failure_mode, metadata = controller.calls[0]
    assert failure_count == 3
    assert reason == "unit_mavsdk_disconnect"
    assert source == "unit.mavsdk"
    assert failure_mode == "local_mavsdk_command_disconnect"
    assert metadata["sitl_injection_id"] == "mavsdk-disconnect"
    assert metadata["scenario"] == "mavsdk_disconnect"
    assert metadata["transport_scope"] == "pixeagle_local_only"


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_dry_run_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLMavsdkDisconnectInjection(
        dry_run=True,
        failure_count=3,
    )

    result = await handler.inject_sitl_mavsdk_disconnect(request, response)

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["reason"] == "dry_run"
    assert result["injection"]["applied_failure_count"] == 0
    assert result["injection"]["requested_failure_count"] == 3
    assert result["px4_connection_before"] is None
    assert result["px4_connection_after"] is None
    assert controller.calls == []


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_unavailable(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    handler = _handler(controller=object())
    request = SITLMavsdkDisconnectInjection()

    response = await handler.inject_sitl_mavsdk_disconnect(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 501
    assert payload["code"] == "SITL_INJECTION_UNAVAILABLE"
    assert payload["path"] == "/api/v1/sitl/injections/mavsdk-disconnect"


@pytest.mark.asyncio
async def test_sitl_mavsdk_disconnect_injection_rejected(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")

    class RejectingController(_ControllerProbe):
        async def inject_mavsdk_disconnect_for_validation(self, **_kwargs):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "offboard_commander_not_running",
                "following_active": True,
                "injection": {
                    "source": "unit.mavsdk",
                    "failure_mode": "local_mavsdk_command_disconnect",
                    "requested_failure_count": None,
                    "applied_failure_count": 0,
                    "failure_reason": "sitl_mavsdk_disconnect",
                    "metadata": {},
                },
                "px4_connection_before": None,
                "px4_connection_after": None,
                "offboard_commander": None,
                "offboard_commander_before": None,
                "offboard_commander_after": None,
                "offboard_commander_failure": None,
                "disconnect_result": None,
                "timestamp": 1.0,
            }

    handler = _handler(controller=RejectingController())
    request = SITLMavsdkDisconnectInjection()

    response = await handler.inject_sitl_mavsdk_disconnect(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["code"] == "SITL_INJECTION_REJECTED"
    assert payload["detail"]["reason"] == "offboard_commander_not_running"


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_injection_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)
    handler = _handler()
    request = SITLMavlink2RestTimeoutInjection()

    response = await handler.inject_sitl_mavlink2rest_timeout(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 403
    assert payload["code"] == "SITL_INJECTIONS_DISABLED"
    assert payload["path"] == "/api/v1/sitl/injections/mavlink2rest-timeout"


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_injection_dispatches(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLMavlink2RestTimeoutInjection(
        injection_id="mavlink2rest-timeout",
        source="unit.mavlink2rest",
        failure_count=2,
        reason="unit_timeout",
        force_stale=True,
        timeout_window_s=1.5,
        metadata={"scenario": "mavlink2rest_timeout"},
    )

    result = await handler.inject_sitl_mavlink2rest_timeout(request, response)

    assert response.status_code == 202
    assert result["status"] == "accepted"
    assert result["injection"]["source"] == "unit.mavlink2rest"
    assert result["injection"]["applied_failure_count"] == 2
    assert result["injection"]["force_stale"] is True
    assert result["injection"]["timeout_window_s"] == 1.5
    assert result["mavlink_telemetry"]["status"] == "stale"
    assert result["mavlink_telemetry"]["connection_state"] == "error"
    assert result["mavlink_telemetry"]["validation_timeout_active"] is True

    (
        failure_count,
        reason,
        force_stale,
        timeout_window_s,
        source,
        metadata,
    ) = controller.calls[0]
    assert failure_count == 2
    assert reason == "unit_timeout"
    assert force_stale is True
    assert timeout_window_s == 1.5
    assert source == "unit.mavlink2rest"
    assert metadata["sitl_injection_id"] == "mavlink2rest-timeout"
    assert metadata["scenario"] == "mavlink2rest_timeout"


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_injection_dry_run_does_not_dispatch(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    controller = _ControllerProbe()
    handler = _handler(controller)
    response = Response()
    request = SITLMavlink2RestTimeoutInjection(
        dry_run=True,
        failure_count=3,
        force_stale=False,
        timeout_window_s=0.5,
    )

    result = await handler.inject_sitl_mavlink2rest_timeout(request, response)

    assert response.status_code == 200
    assert result["status"] == "validated"
    assert result["reason"] == "dry_run"
    assert result["injection"]["applied_failure_count"] == 0
    assert result["injection"]["requested_failure_count"] == 3
    assert result["injection"]["force_stale"] is False
    assert result["injection"]["timeout_window_s"] == 0.5
    assert controller.calls == []


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_injection_unavailable(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")
    handler = _handler(controller=object())
    request = SITLMavlink2RestTimeoutInjection()

    response = await handler.inject_sitl_mavlink2rest_timeout(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 501
    assert payload["code"] == "SITL_INJECTION_UNAVAILABLE"
    assert payload["path"] == "/api/v1/sitl/injections/mavlink2rest-timeout"


@pytest.mark.asyncio
async def test_sitl_mavlink2rest_timeout_injection_rejected(monkeypatch):
    monkeypatch.setenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "1")

    class RejectingController(_ControllerProbe):
        async def inject_mavlink2rest_timeout_for_validation(self, **_kwargs):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "mavlink_data_manager_unavailable",
                "injection": {
                    "source": "unit.mavlink2rest",
                    "requested_failure_count": 1,
                    "applied_failure_count": 0,
                    "failure_reason": "sitl_mavlink2rest_timeout",
                    "force_stale": True,
                    "timeout_window_s": 2.0,
                    "metadata": {},
                },
                "mavlink_telemetry": None,
                "timestamp": 1.0,
            }

    handler = _handler(controller=RejectingController())
    request = SITLMavlink2RestTimeoutInjection()

    response = await handler.inject_sitl_mavlink2rest_timeout(request, Response())
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["code"] == "SITL_INJECTION_REJECTED"
    assert payload["detail"]["reason"] == "mavlink_data_manager_unavailable"
