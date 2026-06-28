"""Tests for legacy follower route helper extraction."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_follower_routes as routes
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class FakeRequest:
    def __init__(self, payload) -> None:
        self.payload = payload

    async def json(self):
        return self.payload


class FakeFollower:
    mode = "mc_velocity_chase"

    def __init__(self, *, switch_success=True) -> None:
        self.switch_success = switch_success
        self.switch_calls = []

    def get_display_name(self):
        return "MC Velocity Chase"

    def get_description(self):
        return "Pursuit follower"

    def get_control_type(self):
        return "velocity_body_offboard"

    def get_available_fields(self):
        return ["vel_body_fwd", "vel_body_right"]

    def get_follower_telemetry(self):
        return {"fields": {"vel_body_fwd": 1.0}}

    def validate_current_mode(self):
        return True

    def switch_mode(self, profile_name):
        self.switch_calls.append(profile_name)
        return self.switch_success


def make_handler(*, follower=None, following_active=False, offboard_commander=None):
    app_controller = SimpleNamespace(
        follower=follower,
        following_active=following_active,
        offboard_commander=offboard_commander,
    )
    return SimpleNamespace(
        app_controller=app_controller,
        logger=logging.getLogger("test.api_legacy_follower_routes"),
    )


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.fixture(autouse=True)
def restore_follower_mode(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_velocity_chase", raising=False)


@pytest.mark.asyncio
async def test_schema_and_profiles_return_legacy_payloads(monkeypatch, tmp_path):
    schema_path = tmp_path / "follower_commands.yaml"
    schema_path.write_text("profiles:\n  mc_velocity_chase:\n    fields: []\n")
    monkeypatch.setattr(routes, "_follower_schema_path", lambda: schema_path)
    monkeypatch.setattr(
        routes.FollowerFactory,
        "get_available_modes",
        lambda: ["mc_velocity_chase", "gm_velocity_vector"],
    )
    monkeypatch.setattr(
        routes.FollowerFactory,
        "get_follower_info",
        lambda mode: {"mode": mode, "implemented": True},
    )

    handler = make_handler()

    schema = response_body(await routes.get_follower_schema(handler))
    profiles = response_body(await routes.get_follower_profiles(handler))

    assert schema == {"profiles": {"mc_velocity_chase": {"fields": []}}}
    assert profiles == {
        "mc_velocity_chase": {"mode": "mc_velocity_chase", "implemented": True},
        "gm_velocity_vector": {"mode": "gm_velocity_vector", "implemented": True},
    }


@pytest.mark.asyncio
async def test_current_profile_reports_active_follower_and_configured_fallback(
    monkeypatch,
):
    active_handler = make_handler(follower=FakeFollower(), following_active=True)
    configured_handler = make_handler()
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_profile_info",
        lambda mode: {
            "display_name": "Configured Chase",
            "description": "Configured profile",
            "control_type": "velocity_body_offboard",
            "required_fields": ["vel_body_fwd"],
            "optional_fields": ["yaw_rate"],
        },
    )

    active = response_body(await routes.get_current_follower_profile(active_handler))
    configured = response_body(
        await routes.get_current_follower_profile(configured_handler)
    )

    assert active["status"] == "engaged"
    assert active["active"] is True
    assert active["mode"] == "mc_velocity_chase"
    assert active["current_field_values"] == {"vel_body_fwd": 1.0}
    assert configured["status"] == "configured"
    assert configured["active"] is False
    assert configured["available_fields"] == ["vel_body_fwd", "yaw_rate"]
    assert "Start offboard mode" in configured["message"]


@pytest.mark.asyncio
async def test_current_profile_unknown_config_preserves_error_shape(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_profile_info",
        lambda mode: (_ for _ in ()).throw(KeyError(mode)),
    )

    current = response_body(await routes.get_current_follower_profile(make_handler()))

    assert current["status"] == "unknown"
    assert current["active"] is False
    assert current["validation_status"] is False
    assert current["error"] == "Profile not found in schema: mc_velocity_chase"


@pytest.mark.asyncio
async def test_switch_profile_updates_configured_and_active_modes(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_available_profiles",
        lambda: ["mc_velocity_chase", "gm_velocity_vector"],
    )
    inactive_handler = make_handler()
    active_follower = FakeFollower()
    active_handler = make_handler(follower=active_follower, following_active=True)

    configured = response_body(
        await routes.switch_follower_profile(
            inactive_handler,
            FakeRequest({"profile_name": "gm_velocity_vector"}),
        )
    )
    active = response_body(
        await routes.switch_follower_profile(
            active_handler,
            FakeRequest({"profile_name": "mc_velocity_chase"}),
        )
    )

    assert configured["status"] == "success"
    assert configured["action"] == "config_update"
    assert configured["old_profile"] == "mc_velocity_chase"
    assert configured["new_profile"] == "gm_velocity_vector"
    assert active["status"] == "success"
    assert active["action"] == "active_switch"
    assert active_follower.switch_calls == ["mc_velocity_chase"]
    assert Parameters.FOLLOWER_MODE == "mc_velocity_chase"


@pytest.mark.asyncio
async def test_switch_profile_validation_and_active_failure(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_available_profiles",
        lambda: ["mc_velocity_chase"],
    )
    active_handler = make_handler(
        follower=FakeFollower(switch_success=False),
        following_active=True,
    )

    with pytest.raises(HTTPException) as missing_exc:
        await routes.switch_follower_profile(active_handler, FakeRequest({}))
    with pytest.raises(HTTPException) as invalid_exc:
        await routes.switch_follower_profile(
            active_handler,
            FakeRequest({"profile_name": "bad_mode"}),
        )
    failed = await routes.switch_follower_profile(
        active_handler,
        FakeRequest({"profile_name": "mc_velocity_chase"}),
    )

    assert missing_exc.value.status_code == 400
    assert missing_exc.value.detail == "profile_name is required"
    assert invalid_exc.value.status_code == 400
    assert "Schema validation failed" in invalid_exc.value.detail
    assert failed.status_code == 500
    assert response_body(failed)["action"] == "active_switch_failed"


@pytest.mark.asyncio
async def test_configured_and_current_mode_payloads(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_profile_info",
        lambda mode: {"display_name": "MC Velocity Chase"},
    )
    monkeypatch.setattr(
        "classes.safety_manager.get_safety_manager",
        lambda: SimpleNamespace(
            get_effective_limits_summary=lambda follower: {
                "MAX_VELOCITY_FORWARD": {"value": 5.0, "source": "GlobalLimits"}
            }
        ),
    )
    handler = make_handler(following_active=True)

    configured = response_body(await routes.get_configured_follower_mode(handler))
    current = response_body(await routes.get_current_follower_mode(handler))

    assert configured == {
        "configured_mode": "mc_velocity_chase",
        "profile_info": {"display_name": "MC Velocity Chase"},
        "status": "valid",
    }
    assert current["success"] is True
    assert current["mode"] == "mc_velocity_chase"
    assert current["mode_upper"] == "MC_VELOCITY_CHASE"
    assert current["is_active"] is True
    assert current["profile_valid"] is True
    assert current["limits_available"] is True
    assert current["effective_limits"] == {
        "MAX_VELOCITY_FORWARD": {"value": 5.0, "source": "GlobalLimits"}
    }


@pytest.mark.asyncio
async def test_setpoints_status_inactive_and_active_publication(monkeypatch):
    monkeypatch.setattr(
        "classes.circuit_breaker.FollowerCircuitBreaker",
        SimpleNamespace(is_active=lambda: bool(0)),
    )
    setpoint_handler = SimpleNamespace(
        get_fields_with_status=lambda: {
            "setpoints": {"vel_body_fwd": 1.0},
            "circuit_breaker": {"active": False, "status": "LIVE_MODE"},
        }
    )
    commander = SimpleNamespace(
        get_status=lambda: {
            "exists": True,
            "running": True,
            "successful_publishes": 2,
            "last_intent_fresh": True,
            "failsafe_defaults_active": False,
        }
    )
    active_handler = make_handler(
        follower=SimpleNamespace(
            follower=SimpleNamespace(setpoint_handler=setpoint_handler)
        ),
        following_active=True,
        offboard_commander=commander,
    )

    inactive = response_body(
        await routes.get_follower_setpoints_with_status(make_handler())
    )
    active = response_body(await routes.get_follower_setpoints_with_status(active_handler))

    assert inactive["follower_active"] is False
    assert inactive["circuit_breaker"]["status"] == "LIVE_MODE"
    assert active["follower_active"] is True
    assert active["command_publication"]["source"] == "offboard_commander"
    assert active["command_publication"]["commands_sent_to_px4"] is True
    assert active["circuit_breaker"]["commands_allowed_by_circuit_breaker"] is True
    assert active["following_engaged"] is True


@pytest.mark.asyncio
async def test_setpoints_status_reports_missing_handler_error():
    handler = make_handler(follower=SimpleNamespace(), following_active=True)

    response = response_body(await routes.get_follower_setpoints_with_status(handler))

    assert response["follower_active"] is True
    assert response["error"] == "Follower has no setpoint handler"
