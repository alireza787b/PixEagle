"""TargetLossHandler runtime-status regressions."""

import os
import sys
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.target_loss_handler import TargetLossHandler
from classes.tracker_output import TrackerDataType, TrackerOutput


def _active_usable_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='vision_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.8,
        raw_data={'usable_for_following': True, 'data_is_stale': False},
        metadata={'usable_for_following': True},
    )


def _active_stale_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='vision_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.8,
        raw_data={
            'usable_for_following': False,
            'data_is_stale': True,
            'freshness_reason': 'prediction_only',
        },
        metadata={'usable_for_following': False, 'data_is_stale': True},
    )


def _active_not_usable_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        tracker_id='vision_tracker',
        position_2d=(0.2, -0.1),
        confidence=0.8,
        raw_data={'usable_for_following': False, 'data_is_stale': False},
        metadata={'usable_for_following': False},
    )


def test_target_loss_handler_treats_active_stale_output_as_lost():
    handler = TargetLossHandler(
        {'MIN_LOSS_DURATION': 0.0},
        follower_name='unit_test',
    )
    valid_output = _active_usable_output()

    active_response = handler.update_tracker_status(valid_output)
    stale_response = handler.update_tracker_status(_active_stale_output())

    assert active_response['tracking_active'] is True
    assert stale_response['tracking_active'] is False
    assert stale_response['target_state'] == 'LOST'
    assert stale_response['input_tracking_active'] is True
    assert stale_response['has_output'] is True
    assert stale_response['usable_for_following'] is False
    assert stale_response['data_is_stale'] is True
    assert stale_response['runtime_status'] == 'stale_output'
    assert stale_response['runtime_consumer_guidance'] == 'stale'
    assert stale_response['runtime_reason'] == 'prediction_only'
    assert handler.last_valid_tracker_output is valid_output


def test_target_loss_handler_treats_active_not_usable_output_as_lost():
    handler = TargetLossHandler(
        {'MIN_LOSS_DURATION': 0.0},
        follower_name='unit_test',
    )

    response = handler.update_tracker_status(_active_not_usable_output())

    assert response['tracking_active'] is False
    assert response['target_state'] == 'LOST'
    assert response['input_tracking_active'] is True
    assert response['has_output'] is True
    assert response['usable_for_following'] is False
    assert response['data_is_stale'] is False
    assert response['runtime_status'] == 'not_usable'
    assert response['runtime_consumer_guidance'] == 'not_usable'
    assert handler.last_valid_tracker_output is None
