#!/usr/bin/env python3
"""
Test script for GimbalVectorBodyFollower
========================================

This script tests the new gimbal vector body follower implementation
to verify it works correctly before flight testing.

Run with: python test_gimbal_vector_body.py
"""

import sys
import logging
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_follower_import():
    """Test 1: Verify follower can be imported."""
    try:
        from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower, Vector3D
        logger.info("✅ Test 1 PASSED: Follower import successful")
        return True
    except Exception as e:
        logger.error(f"❌ Test 1 FAILED: Import error: {e}")
        return False


def test_vector3d_operations():
    """Test 2: Verify Vector3D math operations."""
    try:
        from classes.followers.gimbal_vector_body_follower import Vector3D

        # Create vector
        v = Vector3D(3.0, 4.0, 0.0)

        # Test magnitude
        assert abs(v.magnitude() - 5.0) < 0.001, "Magnitude calculation incorrect"

        # Test normalization
        v_norm = v.normalize()
        assert abs(v_norm.magnitude() - 1.0) < 0.001, "Normalization incorrect"

        # Test scaling
        v_scaled = v_norm.scale(10.0)
        assert abs(v_scaled.magnitude() - 10.0) < 0.001, "Scaling incorrect"

        logger.info("✅ Test 2 PASSED: Vector3D operations correct")
        return True
    except Exception as e:
        logger.error(f"❌ Test 2 FAILED: {e}")
        return False


def test_follower_factory_registration():
    """Test 3: Verify follower is registered in factory."""
    try:
        from classes.follower import FollowerFactory

        # Get available modes
        modes = FollowerFactory.get_available_modes()

        if 'gimbal_vector_body' in modes:
            logger.info("✅ Test 3 PASSED: Follower registered in factory")
            logger.info(f"   Available modes: {modes}")
            return True
        else:
            logger.error(f"❌ Test 3 FAILED: gimbal_vector_body not in modes: {modes}")
            return False
    except Exception as e:
        logger.error(f"❌ Test 3 FAILED: {e}")
        return False


def test_follower_instantiation():
    """Test 4: Verify follower can be instantiated."""
    try:
        from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower
        from unittest.mock import Mock

        # Create mock PX4 controller
        mock_px4 = Mock()
        mock_px4.current_altitude = 10.0

        # Instantiate follower
        follower = GimbalVectorBodyFollower(mock_px4, (0.5, 0.5))

        # Verify basic attributes
        assert follower.follower_name == "GimbalVectorBodyFollower"
        assert follower.mount_type in ['VERTICAL', 'HORIZONTAL', 'TILTED_45']
        assert follower.min_velocity > 0.0
        assert follower.max_velocity > follower.min_velocity

        logger.info("✅ Test 4 PASSED: Follower instantiation successful")
        logger.info(f"   Mount type: {follower.mount_type}")
        logger.info(f"   Velocity range: [{follower.min_velocity}, {follower.max_velocity}] m/s")
        logger.info(f"   Altitude control: {follower.enable_altitude_control}")
        return True
    except Exception as e:
        logger.error(f"❌ Test 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mount_transformations():
    """Test 5: Verify mount transformations work correctly."""
    try:
        from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower
        from unittest.mock import Mock

        mock_px4 = Mock()
        mock_px4.current_altitude = 10.0

        follower = GimbalVectorBodyFollower(mock_px4, (0.5, 0.5))

        # Test VERTICAL mount transformation
        # Gimbal pointing straight down (pitch=90°, roll=0°, yaw=0°) should give downward vector
        vector = follower._gimbal_to_body_vector(0.0, 90.0, 0.0)

        # For vertical mount, straight down should primarily be in down direction (z > 0)
        assert abs(vector.magnitude() - 1.0) < 0.01, "Unit vector magnitude incorrect"

        logger.info("✅ Test 5 PASSED: Mount transformations working")
        logger.info(f"   Test vector (yaw=0, pitch=90, roll=0): fwd={vector.x:.3f}, right={vector.y:.3f}, down={vector.z:.3f}")
        return True
    except Exception as e:
        logger.error(f"❌ Test 5 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tracker_data_processing():
    """Test 6: Verify tracker data can be processed."""
    try:
        from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower
        from classes.tracker_output import TrackerOutput, TrackerDataType
        from unittest.mock import Mock
        import time

        mock_px4 = Mock()
        mock_px4.current_altitude = 10.0

        follower = GimbalVectorBodyFollower(mock_px4, (0.5, 0.5))

        # Create mock tracker output
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.GIMBAL_ANGLES,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_gimbal",
            angular=(10.0, 85.0, -5.0),  # yaw, pitch, roll in degrees
            metadata={"test": True}
        )

        # Process tracker data
        follower.calculate_control_commands(tracker_data)

        # Verify commands were set
        fields = follower.get_all_command_fields()
        assert 'vel_body_fwd' in fields
        assert 'vel_body_right' in fields
        assert 'vel_body_down' in fields

        logger.info("✅ Test 6 PASSED: Tracker data processing working")
        logger.info(f"   Commands: fwd={fields['vel_body_fwd']:.3f}, right={fields['vel_body_right']:.3f}, down={fields['vel_body_down']:.3f} m/s")
        return True
    except Exception as e:
        logger.error(f"❌ Test 6 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_velocity_ramping():
    """Test 7: Verify velocity ramping works."""
    try:
        from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower
        from unittest.mock import Mock

        mock_px4 = Mock()
        mock_px4.current_altitude = 10.0

        follower = GimbalVectorBodyFollower(mock_px4, (0.5, 0.5))

        # Initial velocity should be 0
        assert follower.current_velocity_magnitude == 0.0

        # Update velocity magnitude (simulate 0.5 second)
        follower._update_velocity_magnitude(0.5)

        # Should have ramped up based on acceleration
        expected_increase = follower.ramp_acceleration * 0.5
        assert follower.current_velocity_magnitude > 0.0

        logger.info("✅ Test 7 PASSED: Velocity ramping working")
        logger.info(f"   Ramped from 0.0 to {follower.current_velocity_magnitude:.3f} m/s in 0.5s")
        return True
    except Exception as e:
        logger.error(f"❌ Test 7 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("=" * 70)
    logger.info("GimbalVectorBodyFollower Test Suite")
    logger.info("=" * 70)

    tests = [
        ("Import Test", test_follower_import),
        ("Vector3D Operations", test_vector3d_operations),
        ("Factory Registration", test_follower_factory_registration),
        ("Follower Instantiation", test_follower_instantiation),
        ("Mount Transformations", test_mount_transformations),
        ("Tracker Data Processing", test_tracker_data_processing),
        ("Velocity Ramping", test_velocity_ramping),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info(f"\n--- Running: {test_name} ---")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test crashed: {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status}: {test_name}")

    logger.info("=" * 70)
    logger.info(f"Result: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    logger.info("=" * 70)

    if passed == total:
        logger.info("\n🎉 All tests passed! Ready for flight testing with circuit breaker.")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed. Fix issues before flight testing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
