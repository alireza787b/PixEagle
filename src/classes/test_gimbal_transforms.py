# src/classes/test_gimbal_transforms.py

"""
Gimbal Transformation Test Utilities
===================================

Comprehensive test suite for the gimbal coordinate transformation pipeline.
Validates mount configurations, safety systems, and edge cases to ensure
reliable operation of the GimbalFollower system.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Test Coverage:
- Mount type transformations (VERTICAL/HORIZONTAL)
- Safety validation at multiple levels
- Edge case handling and error conditions
- Performance and consistency testing
- Integration with configuration system
"""

import math
import time
import logging
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass

# Import the transformation system
from gimbal_transforms import (
    create_gimbal_transformer, GimbalAngles, VelocityCommand,
    MountType, ControlMode, ValidationLevel, GimbalTransformationEngine,
    GimbalSafetyValidator, normalize_angle_180, angle_difference
)

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TestResult:
    """Container for individual test results."""
    name: str
    passed: bool
    details: str
    execution_time: float
    expected_result: Any = None
    actual_result: Any = None

class GimbalTransformTestSuite:
    """
    Comprehensive test suite for gimbal transformation system.

    Provides systematic testing of all transformation components including
    mount configurations, safety systems, and edge cases.
    """

    def __init__(self):
        """Initialize test suite with default configurations."""
        self.test_results: List[TestResult] = []

        # Base configuration for testing
        self.base_config = {
            'MOUNT_TYPE': 'VERTICAL',
            'CONTROL_MODE': 'BODY',
            'BASE_VELOCITY': 2.0,
            'MAX_VELOCITY': 8.0,
            'VELOCITY_FILTER_ALPHA': 0.7,
            'YAW_RATE_GAIN': 0.5,
            'MAX_YAW_RATE': 45.0,
            'ANGLE_DEADZONE': 2.0,
            'TRANSFORMATION_VALIDATION': True,
            'VALIDATION_LEVEL': 'STRICT',
            'MAX_ANGULAR_RATE': 30.0,
            'MAX_ACCELERATION': 5.0,
            'MAX_YAW_ACCELERATION': 90.0,
            'ENABLE_ANOMALY_DETECTION': True,
            'MAX_DATA_AGE': 1.0,
            'RATE_CHECK_WINDOW': 0.1,
            'ANOMALY_THRESHOLD': 3.0
        }

    def run_all_tests(self) -> Dict[str, Any]:
        """
        Run the complete test suite.

        Returns:
            Dictionary with test results summary and detailed results
        """
        logger.info("Starting Gimbal Transformation Test Suite")
        logger.info("=" * 50)

        start_time = time.time()

        # Core transformation tests
        self._test_basic_transformations()
        self._test_mount_type_differences()
        self._test_angle_validation()
        self._test_velocity_limits()
        self._test_deadzone_filtering()

        # Safety validation tests
        self._test_safety_validator()
        self._test_rate_limiting()
        self._test_anomaly_detection()

        # Edge case and robustness tests
        self._test_edge_cases()
        self._test_configuration_variations()
        self._test_state_management()

        # Performance tests
        self._test_performance()

        total_time = time.time() - start_time

        # Generate summary
        summary = self._generate_test_summary(total_time)

        logger.info(f"Test Suite Completed in {total_time:.2f}s")
        logger.info(f"Results: {summary['passed']}/{summary['total']} tests passed")

        return summary

    def _test_basic_transformations(self):
        """Test basic gimbal angle to velocity transformations."""
        logger.info("Testing basic transformations...")

        transformer = create_gimbal_transformer(self.base_config)

        # Test center position (should produce zero velocity)
        start_time = time.time()
        angles = GimbalAngles(0.0, 90.0, 0.0)  # Center for vertical mount
        velocity, success = transformer.transform_angles_to_velocity(angles)
        execution_time = time.time() - start_time

        expected_zero = abs(velocity.forward) < 0.01 and abs(velocity.right) < 0.01
        self.test_results.append(TestResult(
            name="Basic Transform - Center Position",
            passed=success and expected_zero,
            details=f"Center angles produced velocity: fwd={velocity.forward:.3f}, right={velocity.right:.3f}",
            execution_time=execution_time
        ))

        # Test right movement
        start_time = time.time()
        angles = GimbalAngles(20.0, 90.0, 0.0)  # Right movement
        velocity, success = transformer.transform_angles_to_velocity(angles)
        execution_time = time.time() - start_time

        right_movement_correct = velocity.right > 0.1  # Should have positive right velocity
        self.test_results.append(TestResult(
            name="Basic Transform - Right Movement",
            passed=success and right_movement_correct,
            details=f"Right angles ({angles.roll}°) produced right velocity: {velocity.right:.3f}",
            execution_time=execution_time
        ))

        # Test forward movement (vertical mount: pitch < 90°)
        start_time = time.time()
        angles = GimbalAngles(0.0, 75.0, 0.0)  # Forward movement
        velocity, success = transformer.transform_angles_to_velocity(angles)
        execution_time = time.time() - start_time

        forward_movement_correct = abs(velocity.forward) > 0.1  # Should have forward velocity
        self.test_results.append(TestResult(
            name="Basic Transform - Forward Movement",
            passed=success and forward_movement_correct,
            details=f"Forward angles ({angles.pitch}°) produced forward velocity: {velocity.forward:.3f}",
            execution_time=execution_time
        ))

    def _test_mount_type_differences(self):
        """Test differences between VERTICAL and HORIZONTAL mount transformations."""
        logger.info("Testing mount type differences...")

        # Create transformers for both mount types
        vertical_config = self.base_config.copy()
        vertical_config['MOUNT_TYPE'] = 'VERTICAL'

        horizontal_config = self.base_config.copy()
        horizontal_config['MOUNT_TYPE'] = 'HORIZONTAL'

        vertical_transformer = create_gimbal_transformer(vertical_config)
        horizontal_transformer = create_gimbal_transformer(horizontal_config)

        # Test same angles with both mounts
        test_angles = GimbalAngles(15.0, 75.0, 0.0)

        start_time = time.time()
        vertical_vel, vertical_success = vertical_transformer.transform_angles_to_velocity(test_angles)
        horizontal_vel, horizontal_success = horizontal_transformer.transform_angles_to_velocity(test_angles)
        execution_time = time.time() - start_time

        # Velocities should be different between mount types
        velocity_difference = (
            abs(vertical_vel.forward - horizontal_vel.forward) > 0.1 or
            abs(vertical_vel.right - horizontal_vel.right) > 0.1
        )

        self.test_results.append(TestResult(
            name="Mount Type Differences",
            passed=vertical_success and horizontal_success and velocity_difference,
            details=f"Vertical: fwd={vertical_vel.forward:.3f}, right={vertical_vel.right:.3f} | "
                   f"Horizontal: fwd={horizontal_vel.forward:.3f}, right={horizontal_vel.right:.3f}",
            execution_time=execution_time
        ))

    def _test_angle_validation(self):
        """Test gimbal angle validation."""
        logger.info("Testing angle validation...")

        transformer = create_gimbal_transformer(self.base_config)

        # Test valid angles
        start_time = time.time()
        valid_angles = GimbalAngles(45.0, 60.0, -30.0)
        velocity, success = transformer.transform_angles_to_velocity(valid_angles)
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Angle Validation - Valid Range",
            passed=success,
            details=f"Valid angles accepted: roll={valid_angles.roll}, pitch={valid_angles.pitch}, yaw={valid_angles.yaw}",
            execution_time=execution_time
        ))

        # Test invalid angles (should be clamped/normalized)
        start_time = time.time()
        extreme_angles = GimbalAngles(200.0, -100.0, 370.0)  # Out of normal ranges
        velocity, success = transformer.transform_angles_to_velocity(extreme_angles)
        execution_time = time.time() - start_time

        # After normalization, angles should be in valid ranges
        angles_normalized = (
            -180.0 <= extreme_angles.roll <= 180.0 and
            -90.0 <= extreme_angles.pitch <= 90.0 and
            -180.0 <= extreme_angles.yaw <= 180.0
        )

        self.test_results.append(TestResult(
            name="Angle Validation - Normalization",
            passed=angles_normalized,
            details=f"Extreme angles normalized: roll={extreme_angles.roll:.1f}, "
                   f"pitch={extreme_angles.pitch:.1f}, yaw={extreme_angles.yaw:.1f}",
            execution_time=execution_time
        ))

    def _test_velocity_limits(self):
        """Test velocity limiting and safety constraints."""
        logger.info("Testing velocity limits...")

        # Create transformer with low velocity limits for testing
        test_config = self.base_config.copy()
        test_config['MAX_VELOCITY'] = 1.0  # Very low limit
        test_config['MAX_YAW_RATE'] = 10.0  # Very low limit

        transformer = create_gimbal_transformer(test_config)

        # Test with extreme angles that should produce high velocities
        start_time = time.time()
        extreme_angles = GimbalAngles(45.0, 45.0, 45.0)
        velocity, success = transformer.transform_angles_to_velocity(extreme_angles)
        execution_time = time.time() - start_time

        # Velocities should be limited
        velocity_limited = (
            abs(velocity.forward) <= test_config['MAX_VELOCITY'] and
            abs(velocity.right) <= test_config['MAX_VELOCITY'] and
            abs(velocity.yaw_rate) <= test_config['MAX_YAW_RATE']
        )

        self.test_results.append(TestResult(
            name="Velocity Limits - Safety Constraints",
            passed=success and velocity_limited,
            details=f"Velocities limited: fwd={velocity.forward:.3f}, right={velocity.right:.3f}, "
                   f"yaw_rate={velocity.yaw_rate:.1f} (limits: {test_config['MAX_VELOCITY']}, {test_config['MAX_YAW_RATE']})",
            execution_time=execution_time
        ))

    def _test_deadzone_filtering(self):
        """Test deadzone filtering for noise reduction."""
        logger.info("Testing deadzone filtering...")

        # Create transformer with large deadzone
        test_config = self.base_config.copy()
        test_config['ANGLE_DEADZONE'] = 5.0  # Large deadzone

        transformer = create_gimbal_transformer(test_config)

        # Test with small angles (within deadzone)
        start_time = time.time()
        small_angles = GimbalAngles(2.0, 88.0, 1.0)  # Small movements from center
        velocity, success = transformer.transform_angles_to_velocity(small_angles)
        execution_time = time.time() - start_time

        # Should produce near-zero velocity due to deadzone
        deadzone_effective = (
            abs(velocity.forward) < 0.01 and
            abs(velocity.right) < 0.01 and
            abs(velocity.yaw_rate) < 0.1
        )

        self.test_results.append(TestResult(
            name="Deadzone Filtering - Noise Reduction",
            passed=success and deadzone_effective,
            details=f"Small angles filtered by deadzone: fwd={velocity.forward:.4f}, "
                   f"right={velocity.right:.4f}, yaw_rate={velocity.yaw_rate:.2f}",
            execution_time=execution_time
        ))

    def _test_safety_validator(self):
        """Test safety validation system."""
        logger.info("Testing safety validation...")

        # Create validator directly
        validator = GimbalSafetyValidator(self.base_config)

        # Test valid angles
        start_time = time.time()
        valid_angles = GimbalAngles(10.0, 85.0, -5.0, timestamp=time.time())
        is_valid, errors = validator.validate_gimbal_angles(valid_angles)
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Safety Validator - Valid Input",
            passed=is_valid and len(errors) == 0,
            details=f"Valid angles accepted with {len(errors)} errors",
            execution_time=execution_time
        ))

        # Test old timestamp (should fail)
        start_time = time.time()
        old_angles = GimbalAngles(10.0, 85.0, -5.0, timestamp=time.time() - 5.0)  # 5 seconds old
        is_valid, errors = validator.validate_gimbal_angles(old_angles)
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Safety Validator - Temporal Check",
            passed=not is_valid and len(errors) > 0,
            details=f"Old timestamp rejected with errors: {errors}",
            execution_time=execution_time
        ))

    def _test_rate_limiting(self):
        """Test rate limiting functionality."""
        logger.info("Testing rate limiting...")

        validator = GimbalSafetyValidator(self.base_config)

        # Add some history first
        current_time = time.time()
        angle1 = GimbalAngles(0.0, 90.0, 0.0, timestamp=current_time - 0.05)
        validator.validate_gimbal_angles(angle1)

        time.sleep(0.01)  # Small delay

        # Test rapid change (should trigger rate limit)
        start_time = time.time()
        rapid_angle = GimbalAngles(60.0, 30.0, 45.0, timestamp=current_time)  # Large change
        is_valid, errors = validator.validate_gimbal_angles(rapid_angle)
        execution_time = time.time() - start_time

        rate_limit_triggered = any("rate too high" in error.lower() for error in errors)

        self.test_results.append(TestResult(
            name="Rate Limiting - Rapid Movement",
            passed=rate_limit_triggered,
            details=f"Rapid movement detection: {len(errors)} errors, rate limit triggered: {rate_limit_triggered}",
            execution_time=execution_time
        ))

    def _test_anomaly_detection(self):
        """Test anomaly detection in safety validator."""
        logger.info("Testing anomaly detection...")

        # Create validator with anomaly detection
        test_config = self.base_config.copy()
        test_config['ENABLE_ANOMALY_DETECTION'] = True
        test_config['ANOMALY_THRESHOLD'] = 2.0  # Lower threshold for testing

        validator = GimbalSafetyValidator(test_config)

        # Build consistent history
        current_time = time.time()
        for i in range(15):  # Need at least 10 for anomaly detection
            normal_angle = GimbalAngles(5.0 + i * 0.1, 90.0 + i * 0.1, 0.0, timestamp=current_time - (15-i) * 0.1)
            validator.validate_gimbal_angles(normal_angle)

        # Test anomalous input
        start_time = time.time()
        anomalous_angle = GimbalAngles(100.0, 45.0, 0.0, timestamp=current_time)  # Very different
        is_valid, errors = validator.validate_gimbal_angles(anomalous_angle)
        execution_time = time.time() - start_time

        anomaly_detected = any("anomaly detected" in error.lower() for error in errors)

        self.test_results.append(TestResult(
            name="Anomaly Detection - Outlier Detection",
            passed=anomaly_detected,
            details=f"Anomaly detection: {len(errors)} errors, anomaly detected: {anomaly_detected}",
            execution_time=execution_time
        ))

    def _test_edge_cases(self):
        """Test edge cases and error conditions."""
        logger.info("Testing edge cases...")

        transformer = create_gimbal_transformer(self.base_config)

        # Test NaN values
        start_time = time.time()
        try:
            nan_angles = GimbalAngles(float('nan'), 90.0, 0.0)
            velocity, success = transformer.transform_angles_to_velocity(nan_angles)
            nan_handled = not success
        except:
            nan_handled = True
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Edge Cases - NaN Handling",
            passed=nan_handled,
            details="NaN values properly handled",
            execution_time=execution_time
        ))

        # Test infinity values
        start_time = time.time()
        try:
            inf_angles = GimbalAngles(0.0, float('inf'), 0.0)
            velocity, success = transformer.transform_angles_to_velocity(inf_angles)
            inf_handled = not success
        except:
            inf_handled = True
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Edge Cases - Infinity Handling",
            passed=inf_handled,
            details="Infinity values properly handled",
            execution_time=execution_time
        ))

    def _test_configuration_variations(self):
        """Test different configuration combinations."""
        logger.info("Testing configuration variations...")

        # Test minimal configuration
        minimal_config = {
            'MOUNT_TYPE': 'HORIZONTAL',
            'TRANSFORMATION_VALIDATION': False  # Disable validation
        }

        start_time = time.time()
        try:
            transformer = create_gimbal_transformer(minimal_config)
            angles = GimbalAngles(10.0, 80.0, 5.0)
            velocity, success = transformer.transform_angles_to_velocity(angles)
            minimal_config_works = success
        except:
            minimal_config_works = False
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="Configuration - Minimal Config",
            passed=minimal_config_works,
            details="Minimal configuration successfully created and used",
            execution_time=execution_time
        ))

    def _test_state_management(self):
        """Test state management and reset functionality."""
        logger.info("Testing state management...")

        transformer = create_gimbal_transformer(self.base_config)

        # Generate some state
        angles = GimbalAngles(15.0, 80.0, -10.0)
        transformer.transform_angles_to_velocity(angles)

        # Test state reset
        start_time = time.time()
        transformer.reset_state()

        # Check if state was reset (last velocity should be zero)
        health = transformer.get_system_health()
        last_vel = health['transformation_engine']['last_velocity']
        state_reset = (
            abs(last_vel['forward']) < 0.001 and
            abs(last_vel['right']) < 0.001 and
            abs(last_vel['yaw_rate']) < 0.001
        )
        execution_time = time.time() - start_time

        self.test_results.append(TestResult(
            name="State Management - Reset Functionality",
            passed=state_reset,
            details=f"State reset successfully: last_velocity={last_vel}",
            execution_time=execution_time
        ))

    def _test_performance(self):
        """Test performance of transformation operations."""
        logger.info("Testing performance...")

        transformer = create_gimbal_transformer(self.base_config)

        # Performance test: many transformations
        num_iterations = 1000
        angles = GimbalAngles(20.0, 75.0, -15.0)

        start_time = time.time()
        success_count = 0
        for _ in range(num_iterations):
            velocity, success = transformer.transform_angles_to_velocity(angles)
            if success:
                success_count += 1
        execution_time = time.time() - start_time

        avg_time_per_transform = execution_time / num_iterations * 1000  # ms
        performance_acceptable = avg_time_per_transform < 1.0  # Less than 1ms per transform

        self.test_results.append(TestResult(
            name="Performance - Transformation Speed",
            passed=performance_acceptable and success_count == num_iterations,
            details=f"{num_iterations} transformations in {execution_time:.3f}s "
                   f"({avg_time_per_transform:.3f}ms avg, {success_count}/{num_iterations} successful)",
            execution_time=execution_time
        ))

    def _generate_test_summary(self, total_time: float) -> Dict[str, Any]:
        """Generate comprehensive test summary."""
        passed_tests = [r for r in self.test_results if r.passed]
        failed_tests = [r for r in self.test_results if not r.passed]

        summary = {
            'total': len(self.test_results),
            'passed': len(passed_tests),
            'failed': len(failed_tests),
            'success_rate': len(passed_tests) / len(self.test_results) * 100,
            'total_execution_time': total_time,
            'average_test_time': sum(r.execution_time for r in self.test_results) / len(self.test_results),
            'failed_tests': [{'name': r.name, 'details': r.details} for r in failed_tests],
            'all_results': self.test_results
        }

        # Print summary
        logger.info("\nTest Summary:")
        logger.info(f"Total Tests: {summary['total']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Success Rate: {summary['success_rate']:.1f}%")
        logger.info(f"Total Time: {summary['total_execution_time']:.2f}s")
        logger.info(f"Average Test Time: {summary['average_test_time']*1000:.2f}ms")

        if failed_tests:
            logger.warning("\nFailed Tests:")
            for test in failed_tests:
                logger.warning(f"- {test.name}: {test.details}")

        return summary

def run_gimbal_transform_tests():
    """Convenience function to run all tests."""
    test_suite = GimbalTransformTestSuite()
    return test_suite.run_all_tests()

if __name__ == "__main__":
    # Run the complete test suite
    print("Running Gimbal Transformation Test Suite")
    print("="*60)

    results = run_gimbal_transform_tests()

    print(f"\nFINAL RESULT: {results['passed']}/{results['total']} tests passed ({results['success_rate']:.1f}%)")

    if results['success_rate'] >= 90:
        print("EXCELLENT: Gimbal transformation system is robust and ready!")
    elif results['success_rate'] >= 80:
        print("GOOD: System functional with minor issues")
    else:
        print("ATTENTION: Some critical issues need to be addressed")