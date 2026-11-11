"""SIH-only boresight samples; no hardware IO, exposure clock or flight model."""

from copy import deepcopy
from datetime import datetime, timezone
import time

from classes.aircraft_state import Quaternion, finite_number
from classes.camera_runtime import CameraRuntime
from classes.gimbal_geometry import resolve_angle_geometry, resolve_mount_type
from classes.gimbal_types import CoordinateSystem, GimbalAngles, GimbalData, TrackingState, TrackingStatus
from classes.parameters import Parameters
from classes.trackers.gimbal_tracker import GimbalTracker
try:
    from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target
except ModuleNotFoundError:
    from sitl_gimbal_geometry_fixture import camera_angles_for_world_target


class _SihGimbalProvider:
    """In-memory normalized input; CameraRuntime alone owns source incarnation."""

    provider_id = 'sih_gimbal_world_target'
    display_name = 'Simulated world-target boresight'
    protocol_name = 'sih_simulated_boresight'
    manual_control = None

    def __init__(self, settings):
        self.settings = dict(settings)
        self.running = False
        self.angle_sample_sequence = 0
        self._observer = None
        self._data = None

    def set_lifecycle_observer(self, observer):
        self._observer = observer

    def start_listening(self):
        if self.running:
            return True
        token = self._observer('starting', None)
        self._data = None
        self.running = True
        if self._observer('started', token) is False:
            self.running = False
            return False
        return True

    def stop_listening(self):
        if self.running:
            self._observer('stopping', None)
            self.running = False
            self._data = None

    def commit(self, angles, received, epoch, lost):
        if not self.running:
            raise ValueError('sih_gimbal_source_stopped')
        stamp = datetime.fromtimestamp(epoch, timezone.utc)
        self.angle_sample_sequence += 1
        self._data = GimbalData(
            angles=GimbalAngles(*angles, coordinate_system=CoordinateSystem.GIMBAL_BODY, timestamp=stamp),
            tracking_status=TrackingStatus(TrackingState.TARGET_LOST if lost else TrackingState.TRACKING_ACTIVE,
                                           timestamp=stamp),
            coordinate_system=CoordinateSystem.GIMBAL_BODY, timestamp=stamp,
            angle_sample_monotonic=received, angle_sample_sequence=self.angle_sample_sequence,
            tracking_sample_monotonic=received,
        )

    def get_current_data(self):
        data = deepcopy(self._data)
        if not self.running or data is None:
            return None
        settings = self.settings
        if time.monotonic() - data.angle_sample_monotonic > settings['CONNECTION_TIMEOUT']:
            return None
        if time.monotonic() - data.tracking_sample_monotonic > settings['TRACKING_STATUS_TIMEOUT']:
            data.tracking_status = None
            data.tracking_sample_monotonic = None
        return data

    def get_connection_status(self):
        return 'connected' if self.get_current_data() is not None else 'disconnected'

    def get_statistics(self):
        return {'fixture_kind': self.protocol_name, 'angle_sample_sequence': self.angle_sample_sequence}

    def get_health_status(self):
        return {'status': self.get_connection_status(), 'recommendation': 'proceed'}

    def is_tracking_active(self):
        data = self.get_current_data()
        return data is not None and data.is_tracking_active()

    def get_provider_metadata(self):
        return {'provider': self.provider_id, 'protocol': self.protocol_name,
                'fixture_kind': 'simulated_boresight', 'physical_camera': False}


class SihGimbalWorldTarget:
    """Reuse production source/tracker contracts for a retained simulated sample."""

    def __init__(self, app, *, progress):
        self.app, self.progress = app, progress
        settings = dict(Parameters.GimbalTracker)
        self.mount = resolve_mount_type(settings, Parameters.GM_VELOCITY_CHASE, Parameters.GM_VELOCITY_VECTOR,
                                        allowed=('HORIZONTAL', 'VERTICAL'))
        if resolve_angle_geometry(settings, self.mount) != resolve_angle_geometry({}, self.mount):
            raise ValueError('sih_gimbal_fixture_requires_canonical_mount_preset')
        self.provider = _SihGimbalProvider(settings)
        self.runtime = CameraRuntime(app, {**settings, 'ENABLED': True, 'CONTROL_ENABLED': False})
        self.runtime.camera_id = 'sih-gimbal-world-target:' + self.runtime.camera_id
        self.runtime.provider = self.provider
        app.camera_runtime = self.runtime
        self.tracker = GimbalTracker(app_controller=app)
        app.tracker = self.tracker
        app.current_tracker_type = 'Gimbal'
        app.get_tracker_output = self.tracker.get_output
        self.tracker.start_tracking(None, None)
        if not self.tracker.monitoring_active:
            raise RuntimeError('sih_gimbal_source_start_failed')
        self._latest_components = None
        self._measurement = None
        self._invalid = False

    @property
    def measurement(self):
        return deepcopy(self._measurement)

    def observe(self, sample, target_ned, *, epoch_s, lost=False):
        """Only actual progress can create a sample; target motion alone cannot."""
        if self._invalid:
            raise ValueError('sih_gimbal_owner_invalid')
        try:
            source = tuple(sample['source_boot_ms'])
            if len(source) != 2 or any(type(value) is not int or value < 0 for value in source):
                raise ValueError('sih_gimbal_pose_source_invalid')
            position = tuple(finite_number(value, 'sih_position') for value in sample['position_ned'])
            quaternion = tuple(sample['quaternion_wxyz'])
            if len(position) != 3:
                raise ValueError('sih_gimbal_pose_invalid')
            Quaternion(*quaternion)
            received = finite_number(sample['monotonic_s'], 'sih_pose_receipt')
            epoch = finite_number(epoch_s, 'sih_projection_epoch')
            if not 0. <= time.monotonic() - received <= self.progress.timeout_s or epoch < 0.:
                raise ValueError('sih_gimbal_pose_stale')
            current = tuple(zip(source, (position, quaternion)))
            if self._latest_components is not None:
                for (stamp, value), (old_stamp, old_value) in zip(current, self._latest_components):
                    if stamp == old_stamp and value != old_value:
                        raise ValueError('sih_gimbal_pose_rewritten')
            self._latest_components = current
            if not self.progress.accept(source, received):
                return None
            angles = camera_angles_for_world_target(position, target_ned, quaternion, self.mount)
            self.provider.commit(angles, received, epoch, lost)
            success, output = self.tracker.update()
            if not success or output.gimbal_observation is None:
                raise ValueError('sih_gimbal_observation_refused')
            self._measurement = dict(source_boot_ms=source, position_ned=position,
                quaternion_wxyz=quaternion, target_ned=tuple(target_ned),
                received_at_monotonic_s=received, epoch_s=epoch,
                target_generation=self.app._tracking_session_generation)
            output.raw_data.update(fixture_kind='simulated_boresight', measurement_target_ned=tuple(target_ned),
                                   projection_pose=self.measurement)
            return output
        except Exception:
            self._invalid = True
            self.provider.stop_listening()
            raise

    def close(self):
        self.runtime.close()
