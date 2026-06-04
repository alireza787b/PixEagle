"""FlowController frame-freshness routing tests."""

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.flow_controller import FlowController


def test_main_loop_routes_hard_video_stall_to_app_controller():
    """No-frame iterations must still trigger fail-closed follow handling."""
    frame_status = {
        "source": "none",
        "status": "unavailable",
        "usable_for_following": False,
        "reason": "frame_read_failed_no_cache",
    }

    flow = object.__new__(FlowController)
    video_handler = SimpleNamespace(
        delay_frame=1,
        get_frame=MagicMock(return_value=None),
        get_frame_status=MagicMock(return_value=frame_status),
    )
    controller = SimpleNamespace(
        shutdown_flag=False,
        following_active=True,
        video_handler=video_handler,
        handle_video_frame_unavailable=AsyncMock(),
    )

    async def _handle_video_frame_unavailable(status):
        controller.shutdown_flag = True
        return None

    controller.handle_video_frame_unavailable.side_effect = _handle_video_frame_unavailable
    flow.controller = controller

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        with patch('classes.flow_controller.Parameters.SHOW_VIDEO_WINDOW', False), \
                patch('classes.flow_controller.time.sleep'), \
                patch.object(FlowController, '_shutdown', return_value=None):
            FlowController.main_loop(flow)
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    video_handler.get_frame.assert_called_once()
    video_handler.get_frame_status.assert_called_once()
    controller.handle_video_frame_unavailable.assert_awaited_once_with(frame_status)
