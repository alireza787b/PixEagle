"""Truthful source metadata for controller lifecycle fixtures, without real IO."""

from types import SimpleNamespace
import time

from classes.frame_publisher import CaptureStamp
from classes.guidance_observation import ImageFrameContext, ObservationProvenance
from classes.following_observation_source import project_following_observation_source
from classes.tracker_output import TrackerDataType, TrackerOutput


def bind_image_source(app, output=None, *, active=False):
    generation = getattr(app, '_tracking_session_generation', 0)
    context = ImageFrameContext(ObservationProvenance('fixture-image-owner', generation, 'analysis-v1', None,
        CaptureStamp('fixture-capture-epoch', '1', time.monotonic(), 'fresh')), (640, 480))
    app.frame_publisher = SimpleNamespace(stream_id='fixture-image-owner', control_source_epoch='fixture-capture-epoch')
    app.tracking_input_context = context
    if output is None:
        output = TrackerOutput(TrackerDataType.POSITION_2D, time.time(), True,
            position_2d=(.5, .5), raw_data={'usable_for_following': True})
    output.image_measurement = context.at_pixel((319.5, 239.5))
    app.get_tracker_output = lambda: output
    if active:
        app._following_observation_source = project_following_observation_source(context)
        app._following_session_id = 'fixture-follow-session'
    return output


def bind_controller_source(app, output=None, *, active=False):
    """Bind whichever real typed observation kind the fixture already supplies."""
    if output is None:
        output = app.get_tracker_output()
    if output is None or output.data_type is not TrackerDataType.GIMBAL_ANGLES:
        return bind_image_source(app, output, active=active)
    from classes.camera_runtime import CameraRuntime
    from classes.gimbal_provider import SipUdpGimbalProvider
    from classes.gimbal_types import GimbalAngleObservation
    runtime = CameraRuntime(app, {'ENABLED': True})
    runtime.camera_id = 'fixture-gimbal-owner'
    runtime.provider = SipUdpGimbalProvider()
    runtime.get_provider()
    app.camera_runtime = runtime
    source = runtime.angle_source_identity()
    output.gimbal_observation = GimbalAngleObservation(source, getattr(app, '_tracking_session_generation', 0),
        'fixture-provider', 'fixture-mount', tuple(output.angular), 'gimbal_body', 1,
        time.monotonic(), 'TRACKING_ACTIVE', time.monotonic())
    tracker = getattr(app, 'tracker', None)
    if tracker is None:
        tracker = app.tracker = SimpleNamespace()
    tracker.provider_metadata = {'provider': 'fixture-provider'}
    tracker._geometry_revision = 'fixture-mount'
    if active:
        app._following_observation_source = project_following_observation_source(output.gimbal_observation)
        app._following_session_id = 'fixture-follow-session'
    return output


def image_output(output):
    """Give an already-created image sample its original analysis provenance."""
    context = ImageFrameContext(ObservationProvenance('fixture-image-owner', 0, 'analysis-v1', None,
        CaptureStamp('fixture-capture-epoch', '1', time.monotonic(), 'fresh')), (640, 480))
    output.image_measurement = context.at_pixel((319.5, 239.5))
    return output


def gimbal_output(output):
    from classes.gimbal_types import CameraObservationSource, GimbalAngleObservation
    output.gimbal_observation = GimbalAngleObservation(CameraObservationSource('fixture-gimbal-owner', 0),
        0, 'fixture-provider', 'fixture-mount', tuple(output.angular), 'gimbal_body', 1,
        time.monotonic(), 'TRACKING_ACTIVE', time.monotonic())
    return output
