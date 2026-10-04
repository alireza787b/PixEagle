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
