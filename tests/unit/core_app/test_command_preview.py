"""Tests for the explicit video-replay-to-command-intent preview boundary."""

from __future__ import annotations

import asyncio
import json
import math
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import Response
import pytest

from classes.circuit_breaker import FollowerCircuitBreaker
from classes.command_intent import CommandIntent
from classes.command_preview import (
    COMMAND_PREVIEW_EXECUTION_MODE,
    CommandPreviewCommander,
    CommandPreviewController,
)
from classes.api_legacy_control_routes import get_offboard_start_preflight
from classes.api_v1_contracts import APIActionRequest
from classes.api_v1_snapshots import (
    classify_following_commander_degradation,
    get_following_command_publication_status,
)
from classes.app_controller import AppController
from classes.fastapi_handler import FastAPIHandler
from classes.following_readiness import (
    evaluate_command_preview_start_readiness,
    evaluate_following_start_readiness,
)
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerDataType, TrackerOutput


def _active_tracker_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.1, -0.1),
        raw_data={
            "has_output": True,
            "usable_for_following": True,
            "data_is_stale": False,
        },
        metadata={
            "usable_for_following": True,
            "data_is_stale": False,
        },
    )


class _PreviewVideo:
    def __init__(self, frame_status: dict):
        self._frame_status = frame_status

    def get_frame_status(self):
        return dict(self._frame_status)


class _PreviewApp:
    current_tracker_type = "CSRT"
    tracker = SimpleNamespace()
    smart_mode_active = False
    following_active = False
    video_handler = _PreviewVideo(
        {
            "source": "fresh",
            "status": "fresh",
            "replay_source": True,
            "connection_open": True,
            "usable_for_following": False,
        }
    )

    def get_tracker_output(self):
        return _active_tracker_output()

    def _tracker_requires_video_for_following(self):
        return True


@pytest.mark.asyncio
async def test_command_preview_records_schema_valid_intents_without_px4():
    handler = SetpointHandler("mc_velocity_chase")
    commander = CommandPreviewCommander(handler, max_history=2)

    assert await commander.start() is True
    fields = handler.get_fields()
    fields["vel_body_fwd"] = 0.25
    intent = CommandIntent(
        profile_name=handler.profile_name,
        control_type=handler.get_control_type(),
        fields=fields,
        source="unit_test",
        reason="preview_step",
    )

    assert commander.submit_intent(intent) is True
    status = commander.get_status()
    assert status["accepted_intents"] == 1
    assert status["commands_sent_to_px4"] is False
    assert status["sends_mavsdk_commands"] is False
    assert status["command_publication_source"] == "command_preview"
    assert status["execution_mode"] == COMMAND_PREVIEW_EXECUTION_MODE
    assert status["last_preview_intent"]["fields"]["vel_body_fwd"] == 0.25

    assert await commander.stop() is True
    stopped = commander.get_status()
    assert stopped["running"] is False
    assert stopped["failsafe_defaults_active"] is True
    assert stopped["commands_sent_to_px4"] is False


def test_command_preview_preserves_raw_follower_math_but_rejects_nonfinite_values():
    handler = SetpointHandler(
        "mc_velocity_chase",
        enforce_operational_limits=False,
    )
    fields = handler.get_fields()
    fields["vel_body_fwd"] = 999.0

    intent = handler.set_fields(fields, source="unit_test", reason="raw_preview")

    assert intent.fields["vel_body_fwd"] == 999.0
    fields["vel_body_fwd"] = math.nan
    with pytest.raises(ValueError, match="finite"):
        handler.set_fields(fields, source="unit_test")


@pytest.mark.asyncio
async def test_command_preview_rejects_incomplete_intents_and_has_no_network_tripwire():
    handler = SetpointHandler("mc_velocity_chase")
    commander = CommandPreviewCommander(handler)
    assert await commander.start() is True

    fields = handler.get_fields()
    fields.pop("yawspeed_deg_s")
    incomplete = CommandIntent(
        profile_name=handler.profile_name,
        control_type=handler.get_control_type(),
        fields=fields,
        source="unit_test",
    )
    assert commander.submit_intent(incomplete) is False
    assert commander.get_status()["rejected_intents"] == 1

    wrong_profile = CommandIntent(
        profile_name="gm_velocity_vector",
        control_type=handler.get_control_type(),
        fields=handler.get_fields(),
        source="unit_test",
    )
    assert commander.submit_intent(wrong_profile) is False
    assert commander.get_status()["rejected_intents"] == 2

    controller = CommandPreviewController()
    assert controller.get_connection_status()["connected"] is False
    with pytest.raises(RuntimeError, match="no PX4/MAVSDK command path"):
        await controller.send_commands_unified()


def test_command_preview_readiness_is_explicit_and_live_readiness_still_rejects_replay(
    monkeypatch,
):
    app = _PreviewApp()
    monkeypatch.setattr(
        Parameters,
        "FOLLOWER_EXECUTION_MODE",
        COMMAND_PREVIEW_EXECUTION_MODE,
        raising=False,
    )
    monkeypatch.setattr(
        FollowerCircuitBreaker,
        "get_activation_state",
        classmethod(
            lambda cls: {"available": True, "active": True, "reason": None}
        ),
    )

    preview = evaluate_command_preview_start_readiness(app)
    assert preview["ready"] is True
    assert preview["usable_for_command_preview"] is True
    assert preview["autonomous_following_authorized"] is False
    assert preview["commands_sent_to_px4"] is False
    assert preview["operational_limits_enforced"] is False
    assert preview["target_freshness_required"] is True
    assert preview["finite_validation_required"] is True
    assert preview["warnings"] == []

    live = evaluate_following_start_readiness(app)
    assert live["usable_for_following"] is False
    assert "not authorized" in live["reason"]

    app.video_handler = _PreviewVideo(
        {
            "source": "cached",
            "status": "cached",
            "replay_source": True,
            "connection_open": True,
            "usable_for_following": False,
        }
    )
    not_ready = evaluate_command_preview_start_readiness(app)
    assert not_ready["ready"] is False
    assert "fresh frame" in not_ready["reason"]


@pytest.mark.asyncio
async def test_typed_preview_start_has_no_px4_command_path(monkeypatch):
    monkeypatch.setattr(
        Parameters,
        "FOLLOWER_EXECUTION_MODE",
        "PX4",
        raising=False,
    )
    circuit_state = {"active": False}
    monkeypatch.setattr(
        FollowerCircuitBreaker,
        "get_activation_state",
        classmethod(
            lambda cls: {
                "available": True,
                "active": circuit_state["active"],
                "reason": None,
            }
        ),
    )

    replay_app = _PreviewApp()
    live_readiness = evaluate_following_start_readiness(replay_app)
    assert live_readiness["usable_for_following"] is False
    assert "not authorized" in live_readiness["reason"]

    px4_connect = AsyncMock(
        side_effect=AssertionError("COMMAND_PREVIEW attempted a PX4 connection")
    )
    px4_start = AsyncMock(
        side_effect=AssertionError("COMMAND_PREVIEW attempted PX4 Offboard start")
    )
    px4_dispatch = AsyncMock(
        side_effect=AssertionError("COMMAND_PREVIEW attempted PX4 command dispatch")
    )
    mavsdk_setter = AsyncMock(
        side_effect=AssertionError("COMMAND_PREVIEW called a MAVSDK setter")
    )
    app = AppController.__new__(AppController)
    app._follower_state_lock = asyncio.Lock()
    app.following_active = False
    app.following_execution_mode = "PX4"
    app.follower = None
    app.offboard_commander = None
    app.setpoint_sender = None
    app.current_tracker_type = "CSRT"
    app.smart_mode_active = False
    app.tracker = SimpleNamespace(normalized_center=(0.0, 0.0))
    app.video_handler = _PreviewVideo(
        {
            "source": "fresh",
            "status": "fresh",
            "replay_source": True,
            "connection_open": True,
            "usable_for_following": False,
        }
    )
    app.get_tracker_output = _active_tracker_output
    app._tracker_requires_video_for_following = lambda: True
    app.telemetry_handler = SimpleNamespace(follower=None)
    app.px4_interface = SimpleNamespace(
        setpoint_handler=None,
        connect=px4_connect,
        start_offboard_mode=px4_start,
        send_commands_unified=px4_dispatch,
        drone=SimpleNamespace(
            offboard=SimpleNamespace(
                set_velocity_body=mavsdk_setter,
                set_velocity_ned=mavsdk_setter,
                set_position_ned=mavsdk_setter,
                set_attitude=mavsdk_setter,
                set_attitude_rate=mavsdk_setter,
            )
        ),
    )
    app._active_following_controller = app.px4_interface
    app.last_offboard_commander_failure = None
    app.tracker_trace_recorder = None
    app._apply_pending_follower_config = AsyncMock(
        return_value={"applied_count": 0, "applied_paths": []}
    )

    handler = object.__new__(FastAPIHandler)
    handler.logger = MagicMock()
    handler.app_controller = app

    px4_response = Response()
    px4_result = await handler.start_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="typed-px4-replay",
            source="unit_test",
            reason="start_following",
        ),
        px4_response,
    )
    px4_payload = json.loads(px4_result.body)
    assert px4_result.status_code == 409
    assert px4_payload["code"] == "ACTION_OFFBOARD_REPLAY_NOT_AUTHORIZED"
    px4_connect.assert_not_awaited()
    px4_start.assert_not_awaited()
    px4_dispatch.assert_not_awaited()
    mavsdk_setter.assert_not_awaited()

    monkeypatch.setattr(
        Parameters,
        "FOLLOWER_EXECUTION_MODE",
        COMMAND_PREVIEW_EXECUTION_MODE,
        raising=False,
    )
    circuit_state["active"] = True

    response = Response()
    result = await handler.start_offboard_action(
        APIActionRequest(
            confirm=True,
            idempotency_key="typed-preview",
            source="unit_test",
            reason="start_command_preview",
        ),
        response,
    )

    assert response.status_code == 202
    assert result["status"] == "success"
    assert result["following_active_after"] is True
    details = result["result"]["legacy_result"]["details"]
    assert details["execution_mode"] == COMMAND_PREVIEW_EXECUTION_MODE
    assert details["commands_sent_to_px4"] is False
    assert details["px4_connection_attempted"] is False
    px4_connect.assert_not_awaited()
    px4_start.assert_not_awaited()
    px4_dispatch.assert_not_awaited()
    mavsdk_setter.assert_not_awaited()

    accepted = await app._dispatch_tracker_output_on_flight_loop(
        _active_tracker_output()
    )
    assert accepted is True
    preview_status = app.offboard_commander.get_status()
    assert preview_status["accepted_intents"] == 1
    assert preview_status["commands_sent_to_px4"] is False
    px4_connect.assert_not_awaited()
    px4_start.assert_not_awaited()
    px4_dispatch.assert_not_awaited()
    mavsdk_setter.assert_not_awaited()

    stopped = await app._disconnect_px4_internal()
    assert stopped["errors"] == []
    px4_connect.assert_not_awaited()
    px4_start.assert_not_awaited()
    px4_dispatch.assert_not_awaited()
    mavsdk_setter.assert_not_awaited()


def test_command_preview_preflight_never_requires_a_px4_component():
    readiness = {
        "ready": True,
        "usable_for_command_preview": True,
        "commands_sent_to_px4": False,
        "circuit_breaker": {"available": True, "active": True},
    }
    app = SimpleNamespace(
        _is_command_preview_configured=lambda: True,
        _get_command_preview_readiness=lambda: dict(readiness),
    )

    preflight = get_offboard_start_preflight(SimpleNamespace(app_controller=app))

    assert preflight["ready"] is True
    assert preflight["issues"] == []
    assert preflight["execution_mode"] == COMMAND_PREVIEW_EXECUTION_MODE
    assert preflight["command_preview"]["commands_sent_to_px4"] is False


def test_inactive_status_reports_configured_preview_for_the_next_start(monkeypatch):
    monkeypatch.setattr(
        Parameters,
        "FOLLOWER_EXECUTION_MODE",
        COMMAND_PREVIEW_EXECUTION_MODE,
        raising=False,
    )
    owner = SimpleNamespace(
        app_controller=SimpleNamespace(
            following_active=False,
            following_execution_mode="PX4",
            offboard_commander=None,
        )
    )

    publication = get_following_command_publication_status(owner)

    assert publication["execution_mode"] == COMMAND_PREVIEW_EXECUTION_MODE
    assert publication["exists"] is False
    assert publication["commands_sent_to_px4"] is False


def test_preview_waiting_for_first_intent_is_not_misclassified_as_px4_failure():
    waiting = {
        "command_publication_source": "command_preview",
        "health_state": "running",
        "running": True,
        "task_active": True,
        "last_intent_fresh": False,
        "accepted_intents": 0,
        "failsafe_defaults_active": False,
    }
    assert classify_following_commander_degradation(waiting, True) is None

    failed = {**waiting, "accepted_intents": 1, "failsafe_defaults_active": True}
    assert (
        classify_following_commander_degradation(failed, True)
        == "offboard_commander_intent_stale"
    )


@pytest.mark.asyncio
async def test_app_controller_preview_lifecycle_uses_no_px4_start_or_stop_path(
    monkeypatch,
):
    app = AppController.__new__(AppController)
    app._follower_state_lock = asyncio.Lock()
    app.following_active = False
    app.following_execution_mode = "PX4"
    app.follower = None
    app.offboard_commander = None
    app.setpoint_sender = None
    app.tracker = SimpleNamespace(normalized_center=(0.0, 0.0))
    app.telemetry_handler = SimpleNamespace(follower=None)
    app.px4_interface = SimpleNamespace(setpoint_handler=None)
    app._active_following_controller = app.px4_interface
    app.last_offboard_commander_failure = None
    app.tracker_trace_recorder = None
    app._apply_pending_follower_config = AsyncMock(
        return_value={"applied_count": 0, "applied_paths": []}
    )
    app._get_command_preview_readiness = lambda: {
        "ready": True,
        "commands_sent_to_px4": False,
        "reason": "unit_test_ready",
    }

    result = await app._connect_command_preview_on_flight_loop()

    assert result["errors"] == []
    assert result["px4_connection_attempted"] is False
    assert result["commands_sent_to_px4"] is False
    assert app.following_active is True
    assert app.following_execution_mode == COMMAND_PREVIEW_EXECUTION_MODE
    assert isinstance(app._active_following_controller, CommandPreviewController)
    assert isinstance(app.offboard_commander, CommandPreviewCommander)

    accepted = await app._dispatch_tracker_output_on_flight_loop(
        _active_tracker_output()
    )
    assert accepted is True
    preview_status = app.offboard_commander.get_status()
    assert preview_status["accepted_intents"] == 1
    assert preview_status["commands_sent_to_px4"] is False
    assert all(
        math.isfinite(float(value))
        for value in preview_status["last_preview_intent"]["fields"].values()
    )

    stopped = await app._disconnect_px4_internal()
    assert stopped["errors"] == []
    assert any("no PX4 Offboard stop sent" in step for step in stopped["steps"])
    assert app.following_active is False
    assert app.following_execution_mode == "PX4"
