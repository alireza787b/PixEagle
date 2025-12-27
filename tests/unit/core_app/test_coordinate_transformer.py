"""
CoordinateTransformer Unit Tests

Tests for coordinate transformation utilities used in gimbal-based tracking.
"""

import pytest
import math
import numpy as np
from unittest.mock import MagicMock, patch

from classes.coordinate_transformer import (
    CoordinateTransformer,
    CameraParameters,
    FrameType,
    TransformationMatrix
)


pytestmark = [pytest.mark.unit, pytest.mark.core_app]


class TestCameraParameters:
    """Tests for CameraParameters dataclass."""

    def test_default_values(self):
        """Test default camera parameters."""
        params = CameraParameters()

        assert params.mount_offset_roll == 0.0
        assert params.mount_offset_pitch == 0.0
        assert params.mount_offset_yaw == 0.0
        assert params.fov_horizontal == 60.0
        assert params.fov_vertical == 45.0
        assert params.focal_length_x == 1.0
        assert params.focal_length_y == 1.0

    def test_custom_values(self):
        """Test custom camera parameters."""
        params = CameraParameters(
            mount_offset_pitch=-10.0,
            fov_horizontal=82.0,
            fov_vertical=52.0
        )

        assert params.mount_offset_pitch == -10.0
        assert params.fov_horizontal == 82.0
        assert params.fov_vertical == 52.0


class TestFrameType:
    """Tests for FrameType enum."""

    def test_frame_types_exist(self):
        """Test all frame types are defined."""
        assert FrameType.GIMBAL_BODY.value == "gimbal_body"
        assert FrameType.AIRCRAFT_BODY.value == "aircraft_body"
        assert FrameType.NED.value == "ned"
        assert FrameType.NORMALIZED.value == "normalized"


class TestCoordinateTransformerInit:
    """Tests for CoordinateTransformer initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        transformer = CoordinateTransformer()

        assert transformer.camera_params is not None
        assert transformer.camera_params.fov_horizontal == 60.0

    def test_custom_params(self):
        """Test initialization with custom parameters."""
        params = CameraParameters(fov_horizontal=90.0)
        transformer = CoordinateTransformer(params)

        assert transformer.camera_params.fov_horizontal == 90.0

    def test_empty_cache(self):
        """Test transform cache starts empty."""
        transformer = CoordinateTransformer()
        assert len(transformer._transform_cache) == 0


class TestGimbalAnglesToBodyVector:
    """Tests for gimbal_angles_to_body_vector method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_forward_pointing(self, transformer):
        """Test gimbal pointing straight forward."""
        vector = transformer.gimbal_angles_to_body_vector(0, 0, 0)

        # Should be [1, 0, 0] (forward)
        np.testing.assert_array_almost_equal(vector, [1.0, 0.0, 0.0], decimal=5)

    def test_right_yaw(self, transformer):
        """Test gimbal yawed right."""
        vector = transformer.gimbal_angles_to_body_vector(45, 0, 0)

        # Should have positive y component (right)
        assert vector[0] > 0  # Still forward
        assert vector[1] > 0  # Right
        assert abs(vector[2]) < 0.01  # No vertical

    def test_left_yaw(self, transformer):
        """Test gimbal yawed left."""
        vector = transformer.gimbal_angles_to_body_vector(-45, 0, 0)

        # Should have negative y component (left)
        assert vector[0] > 0  # Still forward
        assert vector[1] < 0  # Left
        assert abs(vector[2]) < 0.01  # No vertical

    def test_pitch_up(self, transformer):
        """Test gimbal pitched up."""
        vector = transformer.gimbal_angles_to_body_vector(0, 30, 0)

        # Should have negative z component (up in down-positive frame)
        assert vector[0] > 0  # Still forward
        assert abs(vector[1]) < 0.01  # No lateral
        assert vector[2] < 0  # Up (negative in down-positive)

    def test_pitch_down(self, transformer):
        """Test gimbal pitched down."""
        vector = transformer.gimbal_angles_to_body_vector(0, -30, 0)

        # Should have positive z component (down)
        assert vector[0] > 0  # Still forward
        assert abs(vector[1]) < 0.01  # No lateral
        assert vector[2] > 0  # Down

    def test_unit_vector(self, transformer):
        """Test output is always unit vector."""
        for yaw in [-90, -45, 0, 45, 90]:
            for pitch in [-45, 0, 45]:
                vector = transformer.gimbal_angles_to_body_vector(yaw, pitch, 0)
                magnitude = np.linalg.norm(vector)
                assert abs(magnitude - 1.0) < 0.0001

    def test_mount_offset_applied(self, transformer):
        """Test mount offset is applied."""
        transformer.camera_params.mount_offset_yaw = 10.0

        # With offset applied, 0 yaw should look slightly right
        vector = transformer.gimbal_angles_to_body_vector(0, 0, 0, include_mount_offset=True)

        assert vector[1] > 0  # Should be right due to offset

    def test_mount_offset_skipped(self, transformer):
        """Test mount offset can be skipped."""
        transformer.camera_params.mount_offset_yaw = 10.0

        # Without offset, should be straight forward
        vector = transformer.gimbal_angles_to_body_vector(0, 0, 0, include_mount_offset=False)

        np.testing.assert_array_almost_equal(vector, [1.0, 0.0, 0.0], decimal=5)


class TestBodyToNedVector:
    """Tests for body_to_ned_vector method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_no_rotation(self, transformer):
        """Test with aircraft heading north (0 yaw)."""
        body_vector = np.array([1.0, 0.0, 0.0])  # Forward
        ned_vector = transformer.body_to_ned_vector(body_vector, 0.0)

        # Forward in body should be North in NED
        np.testing.assert_array_almost_equal(ned_vector, [1.0, 0.0, 0.0], decimal=5)

    def test_90_degree_yaw(self, transformer):
        """Test with aircraft heading east (90° yaw)."""
        body_vector = np.array([1.0, 0.0, 0.0])  # Forward
        ned_vector = transformer.body_to_ned_vector(body_vector, math.radians(90))

        # Forward should now be East
        np.testing.assert_array_almost_equal(ned_vector, [0.0, 1.0, 0.0], decimal=5)

    def test_180_degree_yaw(self, transformer):
        """Test with aircraft heading south (180° yaw)."""
        body_vector = np.array([1.0, 0.0, 0.0])  # Forward
        ned_vector = transformer.body_to_ned_vector(body_vector, math.radians(180))

        # Forward should now be South (negative North)
        np.testing.assert_array_almost_equal(ned_vector, [-1.0, 0.0, 0.0], decimal=5)

    def test_right_component(self, transformer):
        """Test right component transforms correctly."""
        body_vector = np.array([0.0, 1.0, 0.0])  # Right
        ned_vector = transformer.body_to_ned_vector(body_vector, 0.0)

        # Right should be East when heading north
        np.testing.assert_array_almost_equal(ned_vector, [0.0, 1.0, 0.0], decimal=5)

    def test_down_unchanged(self, transformer):
        """Test down component is unchanged."""
        body_vector = np.array([0.0, 0.0, 1.0])  # Down
        ned_vector = transformer.body_to_ned_vector(body_vector, math.radians(45))

        # Down should remain down regardless of yaw
        np.testing.assert_array_almost_equal(ned_vector, [0.0, 0.0, 1.0], decimal=5)


class TestNedToBodyVector:
    """Tests for ned_to_body_vector method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_inverse_of_body_to_ned(self, transformer):
        """Test NED to body is inverse of body to NED."""
        body_original = np.array([0.5, 0.3, 0.2])
        yaw = math.radians(45)

        ned = transformer.body_to_ned_vector(body_original, yaw)
        body_recovered = transformer.ned_to_body_vector(ned, yaw)

        np.testing.assert_array_almost_equal(body_recovered, body_original, decimal=5)

    def test_north_to_forward(self, transformer):
        """Test North becomes forward when heading north."""
        ned_vector = np.array([1.0, 0.0, 0.0])  # North
        body_vector = transformer.ned_to_body_vector(ned_vector, 0.0)

        np.testing.assert_array_almost_equal(body_vector, [1.0, 0.0, 0.0], decimal=5)


class TestVectorToNormalizedCoords:
    """Tests for vector_to_normalized_coords method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_forward_is_center(self, transformer):
        """Test forward vector maps to center."""
        vector = np.array([1.0, 0.0, 0.0])
        norm_x, norm_y = transformer.vector_to_normalized_coords(vector)

        assert abs(norm_x) < 0.01
        assert abs(norm_y) < 0.01

    def test_right_is_positive_x(self, transformer):
        """Test right offset gives positive x."""
        vector = np.array([1.0, 0.5, 0.0])  # Forward-right
        norm_x, norm_y = transformer.vector_to_normalized_coords(vector)

        assert norm_x > 0

    def test_left_is_negative_x(self, transformer):
        """Test left offset gives negative x."""
        vector = np.array([1.0, -0.5, 0.0])  # Forward-left
        norm_x, norm_y = transformer.vector_to_normalized_coords(vector)

        assert norm_x < 0

    def test_up_is_positive_y(self, transformer):
        """Test up offset gives positive y."""
        vector = np.array([1.0, 0.0, -0.5])  # Forward-up (negative z is up)
        norm_x, norm_y = transformer.vector_to_normalized_coords(vector)

        assert norm_y > 0

    def test_output_clamped(self, transformer):
        """Test output is clamped to reasonable range."""
        vector = np.array([0.1, 1.0, 0.0])  # Extreme right
        norm_x, norm_y = transformer.vector_to_normalized_coords(vector)

        assert abs(norm_x) <= 2.0
        assert abs(norm_y) <= 2.0


class TestNormalizedCoordsToAngles:
    """Tests for normalized_coords_to_angles method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_center_is_zero_angles(self, transformer):
        """Test center maps to zero angles."""
        yaw, pitch = transformer.normalized_coords_to_angles(0.0, 0.0)

        assert abs(yaw) < 0.01
        assert abs(pitch) < 0.01

    def test_fov_edge(self, transformer):
        """Test FOV edge maps correctly."""
        # At normalized 1.0, should be at half FOV
        yaw, pitch = transformer.normalized_coords_to_angles(1.0, 1.0)

        assert abs(yaw - transformer.camera_params.fov_horizontal / 2) < 0.01
        assert abs(pitch - transformer.camera_params.fov_vertical / 2) < 0.01


class TestTransformationMatrix:
    """Tests for get_transformation_matrix method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_identity_for_same_frame(self, transformer):
        """Test identity matrix when source equals target."""
        matrix = transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.AIRCRAFT_BODY
        )

        np.testing.assert_array_almost_equal(matrix, np.eye(3), decimal=5)

    def test_body_to_ned_is_rotation(self, transformer):
        """Test body to NED is a rotation matrix."""
        matrix = transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.NED,
            math.radians(45)
        )

        # Rotation matrix should be orthogonal
        should_be_identity = matrix @ matrix.T
        np.testing.assert_array_almost_equal(should_be_identity, np.eye(3), decimal=5)

    def test_caching(self, transformer):
        """Test matrix caching."""
        # First call
        matrix1 = transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.NED,
            math.radians(45)
        )

        # Second call should use cache
        matrix2 = transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.NED,
            math.radians(45)
        )

        assert len(transformer._transform_cache) == 1
        np.testing.assert_array_equal(matrix1, matrix2)


class TestVelocityCalculation:
    """Tests for calculate_velocity_from_vector method."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_velocity_magnitude(self, transformer):
        """Test velocity has correct magnitude."""
        vector = np.array([1.0, 0.0, 0.0])
        velocity = transformer.calculate_velocity_from_vector(vector, 5.0)

        magnitude = np.linalg.norm(velocity)
        assert abs(magnitude - 5.0) < 0.01

    def test_velocity_direction(self, transformer):
        """Test velocity maintains direction."""
        vector = np.array([1.0, 1.0, 0.0])
        velocity = transformer.calculate_velocity_from_vector(vector, 10.0)

        # Should maintain direction
        unit_vector = vector / np.linalg.norm(vector)
        velocity_direction = velocity / np.linalg.norm(velocity)
        np.testing.assert_array_almost_equal(unit_vector, velocity_direction, decimal=5)

    def test_zero_vector(self, transformer):
        """Test zero vector returns zero velocity."""
        vector = np.array([0.0, 0.0, 0.0])
        velocity = transformer.calculate_velocity_from_vector(vector, 5.0)

        np.testing.assert_array_equal(velocity, [0.0, 0.0, 0.0])


class TestParameterManagement:
    """Tests for parameter management methods."""

    @pytest.fixture
    def transformer(self):
        return CoordinateTransformer()

    def test_update_camera_parameters(self, transformer):
        """Test updating camera parameters."""
        transformer.update_camera_parameters(fov_horizontal=90.0)

        assert transformer.camera_params.fov_horizontal == 90.0

    def test_update_clears_cache(self, transformer):
        """Test cache is cleared on parameter update."""
        # Create cache entry
        transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.NED,
            0.0
        )
        assert len(transformer._transform_cache) > 0

        # Update parameters
        transformer.update_camera_parameters(fov_horizontal=90.0)

        # Cache should be cleared
        assert len(transformer._transform_cache) == 0

    def test_get_camera_parameters(self, transformer):
        """Test getting camera parameters."""
        params = transformer.get_camera_parameters()

        assert isinstance(params, CameraParameters)
        assert params == transformer.camera_params

    def test_clear_cache(self, transformer):
        """Test manual cache clearing."""
        # Create cache entry
        transformer.get_transformation_matrix(
            FrameType.AIRCRAFT_BODY,
            FrameType.NED,
            0.0
        )

        transformer.clear_cache()

        assert len(transformer._transform_cache) == 0

    def test_get_cache_info(self, transformer):
        """Test getting cache info."""
        info = transformer.get_cache_info()

        assert 'total_entries' in info
        assert 'valid_entries' in info
        assert 'cache_timeout' in info
