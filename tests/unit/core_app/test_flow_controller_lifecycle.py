"""FlowController event-loop ownership and fail-closed lifecycle tests."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from classes.flow_controller import FlowController


def _start_flight_loop(flow):
    flow.flight_loop, flow.flight_thread = flow.start_flight_event_loop()


def test_flight_event_loop_is_stable_and_independently_stoppable():
    flow = object.__new__(FlowController)
    _start_flight_loop(flow)
    try:
        assert flow.flight_loop.is_running()
        assert flow.flight_thread.is_alive()
        assert flow.flight_thread.name == "PixEagleFlightLoop"
    finally:
        flow.stop_flight_event_loop()

    assert not flow.flight_thread.is_alive()
    assert flow.flight_loop.is_closed()


def test_process_exit_code_preserves_supervised_restart_request():
    flow = object.__new__(FlowController)
    flow.controller = SimpleNamespace(requested_process_exit_code=42)

    assert flow.get_process_exit_code(default=1) == 42
    assert flow.get_process_exit_code(default=0) == 42


def test_process_exit_code_rejects_invalid_request():
    flow = object.__new__(FlowController)
    flow.controller = SimpleNamespace(requested_process_exit_code=999)

    assert flow.get_process_exit_code(default=1) == 1


def test_shutdown_watchdog_uses_supervised_restart_exit_code():
    flow = object.__new__(FlowController)
    flow.controller = SimpleNamespace(
        requested_process_exit_code=42,
        shutdown=AsyncMock(),
        api_handler=SimpleNamespace(),
    )
    flow.flight_loop = None
    flow.server_loop = None
    flow.server_thread = MagicMock()
    flow.server_thread.is_alive.return_value = False
    flow.stop_flight_event_loop = MagicMock()
    flow._windows_timer_set = False
    watchdog = SimpleNamespace(start=MagicMock(), cancel=MagicMock())
    watchdog_callback = None

    def capture_timer(_interval, callback):
        nonlocal watchdog_callback
        watchdog_callback = callback
        return watchdog

    with patch("classes.flow_controller.threading.Timer", side_effect=capture_timer), patch(
        "classes.flow_controller.os._exit"
    ) as process_exit, patch("classes.flow_controller.Parameters.SHOW_VIDEO_WINDOW", False):
        flow._shutdown()
        watchdog_callback()

    process_exit.assert_called_once_with(42)
    watchdog.start.assert_called_once_with()
    watchdog.cancel.assert_called_once_with()


def test_main_returns_supervised_restart_exit_code():
    import main as main_module

    flow = SimpleNamespace(
        main_loop=MagicMock(),
        get_process_exit_code=MagicMock(return_value=42),
    )
    with patch.object(main_module, "FlowController", return_value=flow), patch.object(
        main_module,
        "configure_runtime_logging",
        return_value={"run_id": "unit-restart"},
    ):
        result = main_module.main()

    assert result == 42
    flow.main_loop.assert_called_once_with()
    flow.get_process_exit_code.assert_called_once_with(default=0)


def test_api_server_exit_runs_cleanup_on_flight_owner_loop():
    flow = object.__new__(FlowController)
    cleanup_loop = []

    async def shutdown():
        cleanup_loop.append(asyncio.get_running_loop())
        return {"errors": []}

    flow.controller = SimpleNamespace(
        shutdown_flag=False,
        shutdown=AsyncMock(side_effect=shutdown),
    )
    flow._api_server_error = None
    _start_flight_loop(flow)
    try:
        flow._fail_closed_after_api_server_exit("unit API exit")
    finally:
        flow.stop_flight_event_loop()

    assert flow.controller.shutdown_flag is True
    assert flow._api_server_error == "unit API exit"
    flow.controller.shutdown.assert_awaited_once()
    assert cleanup_loop == [flow.flight_loop]


def test_fastapi_return_does_not_own_or_stop_flight_loop():
    flow = object.__new__(FlowController)
    handler = SimpleNamespace(start=AsyncMock(return_value=None))
    flow.controller = SimpleNamespace(
        api_handler=handler,
        shutdown_flag=False,
        shutdown=AsyncMock(return_value={"errors": []}),
    )
    flow._api_server_error = None
    _start_flight_loop(flow)
    try:
        _, server_thread = flow.start_fastapi_server()
        server_thread.join(timeout=5.0)

        assert not server_thread.is_alive()
        assert flow.flight_loop.is_running()
        assert flow.controller.shutdown_flag is True
        flow.controller.shutdown.assert_awaited_once()
        handler.start.assert_awaited_once()
    finally:
        flow.stop_flight_event_loop()


def test_loop_task_drain_is_bounded_and_reports_cancellation_resistance():
    loop = asyncio.new_event_loop()
    release = asyncio.Event()

    async def resist_cancellation():
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    task = loop.create_task(
        resist_cancellation(),
        name="resistant-flight-owner",
    )
    loop.run_until_complete(asyncio.sleep(0))

    started = time.monotonic()
    result = FlowController._cancel_and_drain_loop_tasks(
        loop,
        label="unit loop",
        timeout_s=0.01,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert result == {
        "clean": False,
        "cancelled": 1,
        "unresolved": ["resistant-flight-owner"],
    }

    release.set()
    loop.run_until_complete(task)
    loop.close()


def test_main_loop_reports_frame_stall_even_when_follow_mode_is_inactive():
    """Classic UI tracking recovery must run independently of follow mode."""
    flow = object.__new__(FlowController)
    controller = SimpleNamespace(shutdown_flag=False, following_active=False)

    def get_frame():
        controller.shutdown_flag = True
        return None

    controller.video_handler = SimpleNamespace(
        get_frame=MagicMock(side_effect=get_frame),
        get_frame_status=MagicMock(return_value={"status": "unavailable"}),
        delay_frame=0,
    )
    controller.handle_video_frame_unavailable = AsyncMock(return_value=True)
    flow.controller = controller
    flow._observe_video_playback_epoch = MagicMock()
    flow._shutdown = MagicMock()

    flow.main_loop()

    controller.handle_video_frame_unavailable.assert_awaited_once_with(
        {"status": "unavailable"}
    )
    flow._shutdown.assert_called_once_with()
