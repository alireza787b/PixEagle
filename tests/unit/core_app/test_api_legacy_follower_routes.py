"""Tests for legacy follower route helper extraction."""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

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

def make_handler(
    *,
    follower=None,
    following_active=False,
    offboard_commander=None,
    config_rate_limiter=None,
    config_service=None,
    **app_attrs,
):
    app_controller = SimpleNamespace(
        follower=follower,
        following_active=following_active,
        offboard_commander=offboard_commander,
        **app_attrs,
    )
    if not hasattr(app_controller, "_follower_state_lock"):
        app_controller._follower_state_lock = asyncio.Lock()
    handler = SimpleNamespace(
        app_controller=app_controller,
        config_rate_limiter=(
            config_rate_limiter
            or SimpleNamespace(is_allowed=lambda bucket: (bool(1), None))
        ),
        logger=logging.getLogger("test.api_legacy_follower_routes"),
    )
    if config_service is not None:
        handler._get_config_service = lambda: config_service
    return handler


class FakeRuntimeConfigService:
    def __init__(self) -> None:
        self.apply_calls = []

    def apply_runtime_config_tiers(self, tiers, *, source):
        self.apply_calls.append((set(tiers), source))
        return {
            "requested_tiers": sorted(tiers),
            "applied": True,
            "applied_paths": ["Follower.FOLLOWER_MODE"],
            "applied_count": 1,
            "pending_paths": [],
            "pending_count": 0,
            "generation_before": 1,
            "generation_after": 2,
        }


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
            "required_fields": ["vel_body_fwd", "yawspeed_deg_s"],
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
    assert configured["available_fields"] == ["vel_body_fwd", "yawspeed_deg_s"]
    assert "next guarded follow session" in configured["message"]


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
    async def persist_profile(_handler, section, parameter, body):
        assert (section, parameter, body.value) == (
            "Follower",
            "FOLLOWER_MODE",
            "gm_velocity_vector",
        )
        return JSONResponse(content={"success": True, "saved": True})

    monkeypatch.setattr(
        "classes.api_legacy_config_routes.update_config_parameter",
        persist_profile,
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
    active_response = await routes.switch_follower_profile(
        active_handler,
        FakeRequest({"profile_name": "mc_velocity_chase"}),
    )
    active = response_body(active_response)

    assert configured["status"] == "success"
    assert configured["action"] == "profile_saved"
    assert configured["old_profile"] == "mc_velocity_chase"
    assert configured["new_profile"] == "gm_velocity_vector"
    assert active_response.status_code == 409
    assert active["action"] == "profile_change_blocked"
    assert Parameters.FOLLOWER_MODE == "mc_velocity_chase"


@pytest.mark.asyncio
async def test_switch_profile_validation_and_active_block(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_available_profiles",
        lambda: ["mc_velocity_chase"],
    )
    active_handler = make_handler(
        follower=FakeFollower(),
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
    assert failed.status_code == 409
    assert response_body(failed)["action"] == "profile_change_blocked"


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
async def test_follower_health_reports_degraded_commander(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_available_profiles",
        lambda: ["mc_velocity_chase"],
    )
    follower = SimpleNamespace(
        get_display_name=lambda: "MC Velocity Chase",
        get_control_type=lambda: "velocity_body_offboard",
        validate_current_mode=lambda: bool(1),
    )
    commander = SimpleNamespace(
        get_status=lambda: {
            "exists": True,
            "running": True,
            "health_state": "degraded",
            "consecutive_failures": 1,
        }
    )
    handler = make_handler(
        follower=follower,
        following_active=True,
        offboard_commander=commander,
        setpoint_sender=None,
        px4_interface=SimpleNamespace(is_connected=lambda: bool(1)),
        tracker=SimpleNamespace(),
        tracking_started=True,
        _follower_state_lock=object(),
    )

    health = response_body(await routes.get_follower_health(handler))

    assert health["overall_status"] == "degraded"
    assert health["components"]["follower"]["type"] == "MC Velocity Chase"
    assert health["components"]["px4_interface"]["status"] == "connected"
    assert "OffboardCommander has transient publish failures" in health["issues"]


@pytest.mark.asyncio
async def test_follower_health_reports_inactive_cleanup_and_errors(monkeypatch):
    monkeypatch.setattr(
        routes.SetpointHandler,
        "get_available_profiles",
        lambda: (_ for _ in ()).throw(RuntimeError("schema down")),
    )
    handler = make_handler(
        follower=SimpleNamespace(),
        following_active=False,
        offboard_commander=SimpleNamespace(),
        setpoint_sender=object(),
        _follower_state_lock=None,
    )

    health = response_body(await routes.get_follower_health(handler))

    assert health["overall_status"] == "unhealthy"
    assert "Follower inactive but resources not cleaned up" in health["issues"]
    assert "State lock not initialized - thread safety compromised" in health["issues"]
    assert "Configuration validation error: schema down" in health["issues"]
    assert health["components"]["configuration"]["error"] == "schema down"


@pytest.mark.asyncio
async def test_restart_follower_rate_limited_and_inactive_config_reload(monkeypatch):
    service = FakeRuntimeConfigService()
    limited_handler = make_handler(
        config_rate_limiter=SimpleNamespace(
            is_allowed=lambda bucket: (bool(0), 17)
        )
    )
    allowed_handler = make_handler(config_service=service)

    limited = await routes.restart_follower(limited_handler)
    inactive = response_body(await routes.restart_follower(allowed_handler))

    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "17"
    assert response_body(limited)["error"] == "Too many restart requests"
    assert service.apply_calls == [
        ({"immediate", "follower_restart"}, "follower_restart_action")
    ]
    assert inactive["success"] is True
    assert inactive["action"] == "follower_config_applied"
    assert "next follow session" in inactive["message"]


@pytest.mark.asyncio
async def test_restart_follower_refuses_active_follow_session(monkeypatch):
    service = FakeRuntimeConfigService()
    stop_following = AsyncMock()
    start_following = AsyncMock()
    handler = make_handler(
        follower=SimpleNamespace(profile_name="mc_velocity_chase"),
        following_active=True,
        config_service=service,
        stop_following=stop_following,
        start_following=start_following,
    )

    response = await routes.restart_follower(handler)
    restarted = response_body(response)

    assert response.status_code == 409
    stop_following.assert_not_awaited()
    start_following.assert_not_awaited()
    assert service.apply_calls == []
    assert restarted["success"] is False
    assert restarted["error_code"] == "FOLLOWER_RESTART_WHILE_ACTIVE"


@pytest.mark.asyncio
async def test_follower_config_routes_return_general_and_effective(monkeypatch):
    fake_manager = SimpleNamespace(
        get_all_config_summary=lambda: {
            "general": {"CONTROL_UPDATE_RATE": 30},
            "follower_overrides": {
                "MC_VELOCITY_CHASE": {"MAX_SPEED": 5}
            },
            "cache_size": 0,
            "initialized": True,
        },
        get_effective_config_summary=lambda follower_name: {
            "MAX_SPEED": {"value": 5, "source": follower_name}
        },
    )
    monkeypatch.setattr(
        "classes.follower_config_manager.get_follower_config_manager",
        lambda: fake_manager,
    )
    handler = make_handler()

    general = response_body(await routes.get_follower_config_general(handler))
    effective = response_body(
        await routes.get_follower_config_effective(handler, "MC_VELOCITY_CHASE")
    )

    assert general["available"] is True
    assert general["general"] == {"CONTROL_UPDATE_RATE": 30}
    assert general["follower_overrides"] == {"MC_VELOCITY_CHASE": {"MAX_SPEED": 5}}
    assert general["available_followers"] == ["MC_VELOCITY_CHASE"]
    assert effective["follower_name"] == "MC_VELOCITY_CHASE"
    assert effective["params"] == {
        "MAX_SPEED": {"value": 5, "source": "MC_VELOCITY_CHASE"}
    }


@pytest.mark.asyncio
async def test_follower_config_routes_map_errors_to_http_500(monkeypatch):
    monkeypatch.setattr(
        "classes.follower_config_manager.get_follower_config_manager",
        lambda: (_ for _ in ()).throw(RuntimeError("config unavailable")),
    )

    with pytest.raises(HTTPException) as general_exc:
        await routes.get_follower_config_general(make_handler())
    with pytest.raises(HTTPException) as effective_exc:
        await routes.get_follower_config_effective(make_handler(), "bad")

    assert general_exc.value.status_code == 500
    assert general_exc.value.detail == "config unavailable"
    assert effective_exc.value.status_code == 500
    assert effective_exc.value.detail == "config unavailable"


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
