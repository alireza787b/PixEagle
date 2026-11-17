from classes.tracker_output import TrackerDataType, TrackerOutput
from classes.tracker_trace import tracker_output_summary


def test_trace_preserves_measurement_and_processing_times_separately():
    output = TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=100.0, tracking_active=True, angular=(0.0, 90.0, 0.0),
        raw_data={
            "angle_sample_timestamp": 100.0, "processing_timestamp": 101.0,
            "angle_sample_sequence": 7, "angle_sample_age_s": 1.0,
            "tracking_sample_timestamp": 100.5, "password": "not-a-trace-field",
        },
    )
    summary = tracker_output_summary(output)
    assert summary["timestamp"] == 100.0
    assert summary["camera_measurement"] == {
        "angle_sample_timestamp": 100.0, "processing_timestamp": 101.0,
        "angle_sample_sequence": 7, "angle_sample_age_s": 1.0,
        "tracking_sample_timestamp": 100.5,
    }


def test_non_camera_trace_does_not_invent_measurement_metadata():
    output = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=100.0, tracking_active=True, position_2d=(0.0, 0.0),
    )
    assert tracker_output_summary(output)["camera_measurement"] is None


def test_typed_gimbal_source_and_independent_receipts_survive_trace_without_python_addresses():
    from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
    observation = GimbalAngleObservation(CameraObservationSource('camera-owner', 4), 9, 'provider',
        'mount-v2', (0., 90., 0.), 'gimbal_body', 7, 100., 'TRACKING_ACTIVE', 99.8)
    output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 101., True, angular=(0., 90., 0.),
        gimbal_observation=observation, raw_data={'password': 'secret', 'camera_provider_instance': 'obsolete-address'})
    summary = tracker_output_summary(output)
    assert summary['gimbal_observation']['source'] == {'camera_id': 'camera-owner', 'source_generation': 4}
    assert summary['gimbal_observation']['angle_received_at_monotonic_s'] == 100.
    assert summary['gimbal_observation']['tracking_received_at_monotonic_s'] == 99.8
    assert summary['gimbal_observation']['physical_target_identity_confirmed'] is False
    assert 'secret' not in str(summary) and 'obsolete-address' not in str(summary)
    assert output.gimbal_observation is observation


def test_image_trace_preserves_original_capture_geometry_and_frozen_dispatch_context():
    from classes.tracker_trace import build_offboard_publish_trace_record
    from classes.following_observation_source import project_following_observation_source
    from classes.frame_publisher import CaptureStamp
    from classes.guidance_observation import ImageFrameContext, ObservationProvenance
    context = ImageFrameContext(ObservationProvenance('source', 3, 'analysis', None,
        CaptureStamp('capture-epoch', '12', 100., 'fresh')), (640, 480))
    measured = context.at_pixel((12., 23.))
    output = TrackerOutput(TrackerDataType.POSITION_2D, 101., True, position_2d=(.1, .2), image_measurement=measured)
    summary = tracker_output_summary(output)
    assert summary['image_measurement']['provenance']['capture']['captured_at'] == 100.
    assert summary['image_measurement']['provenance']['calibration_revision'] is None
    accepted = {'follow_session_id': 'follow', 'target_generation': 3,
        'observation_source': project_following_observation_source(measured),
        'session_control_revisions': (('speed', 7, None),)}
    result = build_offboard_publish_trace_record(sequence=1, command_intent=None,
        publish_status={'last_publish_success': True}, source='test', dispatch_context=accepted,
        publication_attempted=False, target_generation=3)
    assert result['dispatch_context']['observation_source'] == {
        'source_id': 'source', 'source_epoch': 'capture-epoch', 'geometry_revision': 'analysis', 'calibration_revision': None}
    assert result['dispatch_context']['session_control_revisions'] == [['speed', 7, None]]
    assert result['target_generation'] == 3
    assert result['publish_success'] is None and result['publication_attempted'] is False
    assert measured.provenance.capture.captured_at == 100.
