"""Socket-free regressions for restart ownership and external cleanup."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from classes.app_controller import AppController
from classes.fastapi_handler import FastAPIHandler
from classes.gimbal_provider import create_gimbal_provider


@pytest.mark.asyncio
async def test_restart_returns_lifecycle_lock_before_real_shutdown():
    controller = object.__new__(AppController)
    controller._follower_state_lock = asyncio.Lock()
    controller._flight_event_loop = asyncio.get_running_loop()
    controller._disconnect_px4_internal = AsyncMock(return_value={"steps": [], "errors": []})
    handler = object.__new__(FastAPIHandler)
    handler.app_controller = controller
    handler.logger = MagicMock()
    handler.server = SimpleNamespace(should_exit=False)
    await controller._follower_state_lock.acquire()

    with patch("classes.fastapi_handler.asyncio.sleep", new=AsyncMock()), patch(
        "classes.fastapi_handler.os._exit"
    ) as process_exit:
        await asyncio.wait_for(
            handler._schedule_backend_restart(state_lock=controller._follower_state_lock),
            timeout=1.0,
        )

    controller._disconnect_px4_internal.assert_awaited_once()
    assert controller._shutdown_task.done()
    assert not controller._follower_state_lock.locked()
    assert controller.shutdown_flag
    handler.logger.error.assert_not_called()
    process_exit.assert_called_once_with(42)


@pytest.mark.asyncio
@pytest.mark.parametrize("preview", [False, True])
async def test_follow_start_queued_on_restart_barrier_is_rejected(preview):
    controller = object.__new__(AppController)
    controller._follower_state_lock = asyncio.Lock()
    controller._is_command_preview_configured = lambda: preview
    controller._get_command_preview_readiness = MagicMock()
    await controller._follower_state_lock.acquire()
    with patch("classes.app_controller.Follower.get_mode_info", return_value={}), patch(
        "classes.app_controller.FollowerCircuitBreaker.get_activation_state"
    ) as activation:
        start = asyncio.create_task(controller._connect_px4_on_flight_loop())
        await asyncio.sleep(0)
        assert not start.done()
        controller.shutdown_flag = True
        controller._follower_state_lock.release()
        result = await asyncio.wait_for(start, timeout=1)
    assert result["precondition"]["code"] == "application_shutting_down"
    activation.assert_not_called()
    controller._get_command_preview_readiness.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,owned", [(False, False), (True, False), (True, True)])
async def test_shutdown_closes_external_provider_and_only_cancels_owned_target(enabled, owned):
    provider = create_gimbal_provider({"CONTROL_ENABLED": enabled})
    provider.running = True
    provider._send_command = MagicMock(return_value=True)
    if enabled:
        provider.manual_control.owns_tracking = owned
    controller = object.__new__(AppController)
    controller._disconnect_px4_on_flight_loop = AsyncMock(return_value={"steps": [], "errors": []})
    controller.tracker = SimpleNamespace(is_external_tracker=True, stop_tracking=provider.stop_listening)
    result = await controller._shutdown_impl()
    assert not result["errors"]
    assert not provider.running
    frames = [call.args[0] for call in provider._send_command.call_args_list]
    if not enabled:
        assert frames == []
    else:
        assert any(b"PTZ00" in frame for frame in frames)
        assert any(b"ZMC00" in frame for frame in frames)
        assert any(b"TRC00" in frame for frame in frames) is owned
