"""Tests for legacy safety and circuit-breaker route helper extraction."""

from __future__ import annotations

import asyncio
import json
import math
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_safety_routes as routes


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def __init__(self) -> None:
        self.errors = []
        self.infos = []
        self.warnings = []

    def error(self, *args):
        self.errors.append(args)

    def info(self, *args):
        self.infos.append(args)

    def warning(self, *args):
        self.warnings.append(args)


class FakeConfigService:
    def __init__(self, schema=None) -> None:
        self.schema = schema or {
            "sections": {
                "Follower": {},
                "Safety": {},
                "PID": {},
                "Tracking": {},
                "OSD": {},
                "PX4": {},
                "Custom": {},
            }
        }
        self.values = {
            "FOLLOWER_CIRCUIT_BREAKER": bool(
                getattr(routes.Parameters, "FOLLOWER_CIRCUIT_BREAKER", True)
            ),
            "CIRCUIT_BREAKER_DISABLE_SAFETY": bool(
                getattr(routes.Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False)
            ),
        }
        self.runtime_updates = []

    def get_schema(self):
        return self.schema

    def get_path_value(self, path, default=None):
        return self.values.get(path[0], default)

    def persist_and_apply_runtime_config_path(
        self,
        path,
        value,
        *,
        source,
        allowed_reload_tiers,
    ):
        parameter = path[0]
        old_value = self.values.get(parameter)
        value = bool(value)
        self.values[parameter] = value
        setattr(routes.Parameters, parameter, value)
        self.runtime_updates.append(
            {
                "path": list(path),
                "value": value,
                "source": source,
                "allowed_reload_tiers": tuple(allowed_reload_tiers),
            }
        )
        return {
            "path": parameter,
            "reload_tier": "immediate",
            "changed": old_value != value,
            "applied": old_value != value,
            "backup_id": "config-test-backup" if old_value != value else None,
        }


class FakeHandler:
    def __init__(self, service=None) -> None:
        self.logger = FakeLogger()
        self.service = service or FakeConfigService()
        self.app_controller = SimpleNamespace(
            _follower_state_lock=asyncio.Lock(),
            following_active=False,
        )

    def _get_config_service(self):
        return self.service


class FakeSafetyManager:
    def __init__(self) -> None:
        self._global_limits = {"MAX_VELOCITY": 10.0}
        self._follower_overrides = {
            "MC_VELOCITY_CHASE": {"MAX_VELOCITY_FORWARD": 4.0}
        }
        self.summary = {
            "MAX_VELOCITY_FORWARD": {
                "is_overridden": True,
                "source": "FollowerOverrides",
            },
            "MAX_VELOCITY_LATERAL": {"is_overridden": False},
            "MAX_VELOCITY_VERTICAL": {"is_overridden": False},
            "MAX_VELOCITY": {"is_overridden": False},
            "MIN_ALTITUDE": {"is_overridden": False},
            "MAX_ALTITUDE": {"is_overridden": False},
            "ALTITUDE_WARNING_BUFFER": {"is_overridden": False},
            "ALTITUDE_SAFETY_ENABLED": {"is_overridden": False},
            "MAX_YAW_RATE": {"is_overridden": False},
            "MAX_PITCH_RATE": {"is_overridden": False},
            "MAX_ROLL_RATE": {"is_overridden": False},
        }

    def get_velocity_limits(self, follower_name):
        return SimpleNamespace(
            forward=4.0,
            lateral=3.0,
            vertical=2.0,
            max_magnitude=6.0,
        )

    def get_altitude_limits(self, follower_name):
        return SimpleNamespace(
            min_altitude=5.0,
            max_altitude=90.0,
            warning_buffer=3.0,
            safety_enabled=False,
        )

    def get_rate_limits(self, follower_name):
        return SimpleNamespace(
            yaw=math.radians(30.0),
            pitch=math.radians(20.0),
            roll=math.radians(10.0),
        )

    def get_effective_limits_summary(self, follower_name):
        return self.summary

    def get_all_limits_summary(self):
        return {
            "global_limits": dict(self._global_limits),
            "follower_overrides": {
                name: dict(values)
                for name, values in self._follower_overrides.items()
            },
            "cache_size": 0,
            "initialized": True,
        }

    def is_altitude_safety_enabled(self, follower_name):
        return False

    def get_available_followers(self):
        return ["mc_velocity_chase"]


class FakeCircuitBreaker:
    active = True
    reset_count = 0
    stats = {
        "circuit_breaker_active": True,
        "total_commands": 12,
        "total_commands_blocked": 10,
        "total_commands_allowed": 2,
        "last_blocked_command": "velocity_body(x=1)",
        "followers_tested": ["mc_velocity_chase", "gm_velocity_vector"],
        "command_types": {"velocity_body": 10, "attitude_rate": 2},
        "elapsed_time_seconds": 8.0,
        "command_rate_hz": 6.5,
        "last_command_time": 123.0,
        "session_start_time": 115.0,
        "system_status": "testing",
    }

    @classmethod
    def is_active(cls):
        return getattr(routes.Parameters, "FOLLOWER_CIRCUIT_BREAKER", cls.active)

    @classmethod
    def get_statistics(cls):
        return cls.stats

    @classmethod
    def reset_statistics(cls):
        cls.reset_count += 1
        cls.stats = {
            **cls.stats,
            "circuit_breaker_active": cls.active,
            "total_commands": 0,
            "total_commands_blocked": 0,
            "total_commands_allowed": 0,
            "followers_tested": [],
            "command_types": {},
            "elapsed_time_seconds": 0.0,
            "command_rate_hz": 0.0,
            "last_command_time": None,
            "last_blocked_command": None,
        }


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.fixture(autouse=True)
def reset_fake_circuit_breaker(monkeypatch):
    FakeCircuitBreaker.active = True
    FakeCircuitBreaker.reset_count = 0
    monkeypatch.setattr(
        routes.Parameters,
        "FOLLOWER_CIRCUIT_BREAKER",
        True,
        raising=False,
    )
    monkeypatch.setattr(
        routes.Parameters,
        "CIRCUIT_BREAKER_DISABLE_SAFETY",
        False,
        raising=False,
    )
    FakeCircuitBreaker.stats = {
        "circuit_breaker_active": True,
        "total_commands": 12,
        "total_commands_blocked": 10,
        "total_commands_allowed": 2,
        "last_blocked_command": "velocity_body(x=1)",
        "followers_tested": ["mc_velocity_chase", "gm_velocity_vector"],
        "command_types": {"velocity_body": 10, "attitude_rate": 2},
        "elapsed_time_seconds": 8.0,
        "command_rate_hz": 6.5,
        "last_command_time": 123.0,
        "session_start_time": 115.0,
        "system_status": "testing",
    }


@pytest.mark.asyncio
async def test_circuit_breaker_status_and_statistics_payloads(monkeypatch):
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)
    monkeypatch.setattr(
        routes.Parameters,
        "CIRCUIT_BREAKER_DISABLE_SAFETY",
        True,
        raising=False,
    )
    handler = FakeHandler()

    status = response_body(await routes.get_circuit_breaker_status(handler))
    statistics = response_body(await routes.get_circuit_breaker_statistics(handler))

    assert status["available"] is True
    assert status["active"] is True
    assert status["status"] == "testing"
    assert status["safety_bypass_effective"] is True
    assert status["configuration"]["parameter_name"] == "FOLLOWER_CIRCUIT_BREAKER"
    assert status["configuration"]["persisted_value"] is True
    assert status["configuration"]["runtime_matches_persisted"] is True
    assert status["safety_bypass_persisted"] is True
    assert status["safety_bypass_runtime_matches_persisted"] is True
    assert statistics["usage_summary"]["total_intercepted_commands"] == 12
    assert statistics["usage_summary"]["unique_followers_tested"] == 2
    assert statistics["performance"]["testing_efficiency"] == "high"


@pytest.mark.asyncio
async def test_circuit_breaker_unavailable_legacy_shapes(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", False)

    status = response_body(await routes.get_circuit_breaker_status(handler))
    assert status == {
        "available": False,
        "error": "Circuit breaker system not available",
        "message": "FollowerCircuitBreaker module could not be imported",
    }

    with pytest.raises(HTTPException) as exc_info:
        await routes.get_circuit_breaker_statistics(handler)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_toggle_circuit_breaker_enables_and_resets_statistics(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)
    monkeypatch.setattr(
        routes.Parameters,
        "FOLLOWER_CIRCUIT_BREAKER",
        False,
        raising=False,
    )

    body = response_body(await routes.toggle_circuit_breaker(handler))

    assert body["status"] == "success"
    assert body["action"] == "enabled"
    assert body["active"] is True
    assert body["old_state"] is False
    assert body["new_state"] is True
    assert body["message"] == "Circuit breaker enabled"
    assert body["statistics_reset"] is True
    assert body["persisted"] is True
    assert body["runtime_applied"] is True
    assert body["deprecated"] is True
    assert routes.Parameters.FOLLOWER_CIRCUIT_BREAKER is True
    assert FakeCircuitBreaker.reset_count == 1
    assert handler.logger.infos


@pytest.mark.asyncio
async def test_toggle_circuit_breaker_disables_without_reset(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)

    body = response_body(await routes.toggle_circuit_breaker(handler))

    assert body["status"] == "success"
    assert body["action"] == "disabled"
    assert body["active"] is False
    assert body["old_state"] is True
    assert body["new_state"] is False
    assert body["message"] == "Circuit breaker disabled"
    assert body["statistics_reset"] is False
    assert routes.Parameters.FOLLOWER_CIRCUIT_BREAKER is False
    assert FakeCircuitBreaker.reset_count == 0
    assert handler.logger.warnings


@pytest.mark.asyncio
async def test_toggle_circuit_breaker_safety_bypass_reports_effective_only_when_active(
    monkeypatch,
):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)

    enabled = response_body(await routes.toggle_circuit_breaker_safety_bypass(handler))

    assert enabled["status"] == "success"
    assert enabled["action"] == "enabled"
    assert enabled["safety_bypass"] is True
    assert enabled["old_state"] is False
    assert enabled["new_state"] is True
    assert enabled["circuit_breaker_active"] is True
    assert enabled["effective"] is True
    assert enabled["message"] == "Safety checks bypassed"
    assert enabled["warning"] == "Safety bypass active - altitude/velocity limits disabled"
    assert routes.Parameters.CIRCUIT_BREAKER_DISABLE_SAFETY is True
    assert handler.logger.warnings

    disabled = response_body(await routes.toggle_circuit_breaker_safety_bypass(handler))

    assert disabled["action"] == "disabled"
    assert disabled["safety_bypass"] is False
    assert disabled["old_state"] is True
    assert disabled["new_state"] is False
    assert disabled["effective"] is False
    assert disabled["message"] == "Safety checks enforced"
    assert disabled["warning"] is None
    assert routes.Parameters.CIRCUIT_BREAKER_DISABLE_SAFETY is False


@pytest.mark.asyncio
async def test_toggle_circuit_breaker_safety_bypass_not_effective_when_cb_inactive(
    monkeypatch,
):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)
    monkeypatch.setattr(
        routes.Parameters,
        "FOLLOWER_CIRCUIT_BREAKER",
        False,
        raising=False,
    )

    body = response_body(await routes.toggle_circuit_breaker_safety_bypass(handler))

    assert body["safety_bypass"] is True
    assert body["circuit_breaker_active"] is False
    assert body["effective"] is False
    assert body["message"] == "Safety checks enforced"
    assert body["warning"] is None


@pytest.mark.asyncio
async def test_circuit_breaker_change_is_refused_while_following(monkeypatch):
    handler = FakeHandler()
    handler.app_controller.following_active = True
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)

    with pytest.raises(HTTPException) as exc_info:
        await routes.toggle_circuit_breaker(handler)

    assert exc_info.value.status_code == 409
    assert "while following is active" in str(exc_info.value.detail)
    assert handler.service.runtime_updates == []
    assert routes.Parameters.FOLLOWER_CIRCUIT_BREAKER is True


@pytest.mark.asyncio
async def test_reset_circuit_breaker_statistics_payload(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", True)
    monkeypatch.setattr(routes, "FollowerCircuitBreaker", FakeCircuitBreaker)

    body = response_body(await routes.reset_circuit_breaker_statistics(handler))

    assert body["status"] == "success"
    assert body["action"] == "statistics_reset"
    assert body["message"] == "Circuit breaker statistics have been reset"
    assert body["old_statistics"] == {
        "total_commands": 12,
        "followers_tested": 2,
        "elapsed_time": 8.0,
    }
    assert body["new_statistics"]["total_commands"] == 0
    assert body["new_statistics"]["followers_tested"] == []
    assert "reset_timestamp" in body
    assert FakeCircuitBreaker.reset_count == 1
    assert handler.logger.infos


@pytest.mark.asyncio
async def test_circuit_breaker_mutations_preserve_legacy_unavailable_error_shape(
    monkeypatch,
):
    handler = FakeHandler()
    monkeypatch.setattr(routes, "CIRCUIT_BREAKER_AVAILABLE", False)

    for route in (
        routes.toggle_circuit_breaker,
        routes.toggle_circuit_breaker_safety_bypass,
        routes.reset_circuit_breaker_statistics,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await route(handler)
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_safety_config_available_and_unavailable(monkeypatch):
    handler = FakeHandler()
    manager = FakeSafetyManager()

    monkeypatch.setattr(
        routes,
        "_safety_manager_or_none",
        lambda: (True, manager),
    )
    available = response_body(await routes.get_safety_config(handler))

    monkeypatch.setattr(
        routes,
        "_safety_manager_or_none",
        lambda: (False, None),
    )
    unavailable = response_body(await routes.get_safety_config(handler))

    assert available["available"] is True
    assert available["global_limits"] == {"MAX_VELOCITY": 10.0}
    assert available["follower_overrides"]["MC_VELOCITY_CHASE"][
        "MAX_VELOCITY_FORWARD"
    ] == 4.0
    assert unavailable["available"] is False
    assert unavailable["message"] == "SafetyManager not available"


@pytest.mark.asyncio
async def test_follower_safety_limits_use_manager_units_and_override_summary(
    monkeypatch,
):
    handler = FakeHandler()
    manager = FakeSafetyManager()
    monkeypatch.setattr(routes, "_safety_manager_or_none", lambda: (True, manager))

    limits = response_body(
        await routes.get_follower_safety_limits(handler, "mc_velocity_chase")
    )

    assert limits["follower_name"] == "mc_velocity_chase"
    assert limits["velocity"]["forward"] == 4.0
    assert limits["velocity"]["source"] == "FollowerOverrides"
    assert limits["velocity"]["is_overridden"] is True
    assert limits["altitude"]["safety_enabled"] is False
    assert limits["rates"] == {
        "yaw_deg": 29.999999999999996,
        "pitch_deg": 20.0,
        "roll_deg": 10.0,
        "source": "GlobalLimits",
        "is_overridden": False,
    }
    assert limits["altitude_safety_enabled"] is False
    assert limits["has_any_overrides"] is True


@pytest.mark.asyncio
async def test_follower_safety_limits_fallback_uses_parameters(monkeypatch):
    handler = FakeHandler()
    values = {
        "MAX_VELOCITY_FORWARD": 7.0,
        "MAX_VELOCITY_LATERAL": 5.0,
        "MAX_VELOCITY_VERTICAL": 2.0,
        "MIN_ALTITUDE": 4.0,
        "MAX_ALTITUDE": 80.0,
        "ALTITUDE_WARNING_BUFFER": 6.0,
        "MAX_YAW_RATE": 35.0,
        "MAX_PITCH_RATE": None,
        "MAX_ROLL_RATE": None,
    }
    monkeypatch.setattr(routes, "_safety_manager_or_none", lambda: (False, None))
    monkeypatch.setattr(
        routes.Parameters,
        "get_effective_limit",
        staticmethod(lambda name, follower: values[name]),
    )

    limits = response_body(
        await routes.get_follower_safety_limits(handler, "gm_velocity_vector")
    )

    assert limits["velocity"] == {
        "forward": 7.0,
        "lateral": 5.0,
        "vertical": 2.0,
    }
    assert limits["altitude"]["warning_buffer"] == 6.0
    assert limits["rates"] == {
        "yaw_deg": 35.0,
        "pitch_deg": 45.0,
        "roll_deg": 45.0,
    }
    assert limits["altitude_safety_enabled"] is True


@pytest.mark.asyncio
async def test_effective_limits_and_relevant_sections_payloads(monkeypatch):
    handler = FakeHandler()
    manager = FakeSafetyManager()
    monkeypatch.setattr(routes, "_safety_manager_or_none", lambda: (True, manager))

    effective = response_body(
        await routes.get_effective_limits(handler, "mc_velocity_chase")
    )
    relevant = response_body(
        await routes.get_relevant_sections(handler, "gm_velocity_vector")
    )

    assert effective["success"] is True
    assert effective["follower_name"] == "mc_velocity_chase"
    assert effective["limits"] == manager.summary
    assert effective["available_followers"] == ["mc_velocity_chase"]
    assert relevant["success"] is True
    assert relevant["current_mode"] == "gm_velocity_vector"
    assert "GimbalTracker" in relevant["mode_specific_sections"]
    assert "PX4" in relevant["active_sections"]
    assert relevant["other_sections"] == ["Custom"]


@pytest.mark.asyncio
async def test_effective_limits_unavailable_and_relevant_sections_defaults(
    monkeypatch,
):
    handler = FakeHandler(service=FakeConfigService({"sections": {}}))
    monkeypatch.setattr(routes, "_safety_manager_or_none", lambda: (False, None))
    monkeypatch.setattr(
        routes.Parameters,
        "FOLLOWER_MODE",
        "MC_VELOCITY_CHASE",
        raising=False,
    )

    effective = response_body(await routes.get_effective_limits(handler))
    relevant = response_body(await routes.get_relevant_sections(handler))

    assert effective["available"] is False
    assert effective["message"] == "SafetyManager not available"
    assert relevant["current_mode"] == "mc_velocity_chase"
    assert relevant["other_sections"] == []


@pytest.mark.asyncio
async def test_safety_route_errors_map_to_http_500(monkeypatch):
    handler = FakeHandler()
    monkeypatch.setattr(
        routes,
        "_safety_manager_or_none",
        lambda: (_ for _ in ()).throw(RuntimeError("manager failed")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.get_safety_config(handler)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "manager failed"
    assert handler.logger.errors
