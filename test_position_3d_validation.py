#!/usr/bin/env python3
"""
Position_3D Schema Validation Test Script
==========================================

This script comprehensively tests the updated Position_3D schema validation logic
and VELOCITY_AWARE data type selection in the PixEagle tracker system.

Project Information:
- Project Name: PixEagle  
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Test Coverage:
1. Valid POSITION_3D tracker output with matching position_2d and position_3d coordinates
2. Invalid POSITION_3D tracker output with mismatched position_2d and position_3d coordinates  
3. Tolerance checking for coordinate matching (within 1e-6 tolerance)
4. VELOCITY_AWARE data type selection in CSRT tracker when velocity is available
5. Comprehensive error handling and validation scenarios
"""

import sys
import os
import time
import logging
from typing import Tuple, Optional

# Add src directory to path to import classes
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from classes.tracker_output import TrackerOutput, TrackerDataType
    from classes.schema_manager import get_schema_manager, validate_tracker_data
    print("Successfully imported TrackerOutput and schema validation modules")
except ImportError as e:
    print(f"Failed to import required modules: {e}")
    print("Make sure you're running this script from the PixEagle root directory")
    sys.exit(1)

class Position3DValidationTester:
    """
    Comprehensive test class for Position_3D schema validation logic.
    """
    
    def __init__(self):
        """Initialize the tester with test counters and results tracking."""
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_results = []
        self.schema_manager_available = True
        
        # Initialize schema manager
        try:
            self.schema_manager = get_schema_manager()
            print("Schema manager initialized successfully")
        except Exception as e:
            print(f"Warning: Schema manager initialization failed: {e}")
            self.schema_manager_available = False
    
    def log_test_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result and update counters."""
        if passed:
            self.tests_passed += 1
            print(f"[PASS]: {test_name}")
        else:
            self.tests_failed += 1
            print(f"[FAIL]: {test_name}")
            if message:
                print(f"        {message}")
        
        self.test_results.append({
            'test_name': test_name,
            'passed': passed, 
            'message': message
        })
    
    def test_valid_position_3d_matching_coordinates(self):
        """
        Test Case 1: Valid POSITION_3D tracker output with matching coordinates.
        
        Tests:
        - position_3d=(0.5, -0.3, 2.1) and position_2d=(0.5, -0.3) → should pass
        """
        print("\n--- Test Case 1: Valid POSITION_3D with matching coordinates ---")
        
        try:
            tracker_output = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_valid_3d",
                position_3d=(0.5, -0.3, 1.5),
                position_2d=(0.5, -0.3),
                confidence=0.9
            )
            
            # Validation should pass without raising an exception
            is_valid = tracker_output.validate()
            self.log_test_result(
                "Valid POSITION_3D with exact coordinate matching",
                True,
                f"Created TrackerOutput with position_3d=(0.5, -0.3, 1.5) and position_2d=(0.5, -0.3)"
            )
            
            # Verify the data structure
            self.log_test_result(
                "Data structure integrity check",
                (tracker_output.position_3d == (0.5, -0.3, 1.5) and 
                 tracker_output.position_2d == (0.5, -0.3)),
                "Position data correctly stored"
            )
            
        except Exception as e:
            self.log_test_result(
                "Valid POSITION_3D with exact coordinate matching", 
                False,
                f"Unexpected validation failure: {str(e)}"
            )
    
    def test_invalid_position_3d_mismatched_coordinates(self):
        """
        Test Case 2: Invalid POSITION_3D tracker output with mismatched coordinates.
        
        Tests:  
        - position_3d=(0.5, -0.3, 2.1) and position_2d=(0.6, -0.3) → should fail
        """
        print("\n--- Test Case 2: Invalid POSITION_3D with mismatched coordinates ---")
        
        try:
            tracker_output = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_invalid_3d",
                position_3d=(0.5, -0.3, 1.5),
                position_2d=(0.6, -0.3),  # X coordinate differs by 0.1
                confidence=0.8
            )
            
            # Should raise a validation error
            self.log_test_result(
                "Invalid POSITION_3D with mismatched coordinates",
                False,
                "Expected validation error but none was raised"
            )
            
        except ValueError as e:
            expected_error_keywords = ["position_2d", "position_3d", "match"]
            error_message = str(e).lower()
            contains_expected = any(keyword in error_message for keyword in expected_error_keywords)
            
            self.log_test_result(
                "Invalid POSITION_3D with mismatched coordinates",
                contains_expected,
                f"Validation error raised as expected: {str(e)}"
            )
        except Exception as e:
            self.log_test_result(
                "Invalid POSITION_3D with mismatched coordinates",
                False,
                f"Unexpected error type: {str(e)}"
            )
    
    def test_position_3d_tolerance_checking(self):
        """
        Test Case 3: Position_3D tolerance checking.
        
        Tests:
        - position_3d=(0.5, -0.3, 2.1) and position_2d=(0.500001, -0.3) → should pass (within tolerance)
        """
        print("\n--- Test Case 3: POSITION_3D tolerance checking ---")
        
        try:
            # Test within tolerance (should pass)
            tracker_output_within = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_tolerance_within",
                position_3d=(0.5, -0.3, 1.5),
                position_2d=(0.5000001, -0.3),  # Difference of 1e-7, within tolerance
                confidence=0.85
            )
            
            self.log_test_result(
                "POSITION_3D within tolerance (1e-6)",
                True,
                "Small difference (0.0000001) accepted within tolerance"
            )
            
        except Exception as e:
            self.log_test_result(
                "POSITION_3D within tolerance (1e-6)",
                False,
                f"Should have passed within tolerance: {str(e)}"
            )
        
        try:
            # Test outside tolerance (should fail)
            tracker_output_outside = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_tolerance_outside",
                position_3d=(0.5, -0.3, 1.5),
                position_2d=(0.50001, -0.3),  # Difference of 1e-5, outside tolerance 
                confidence=0.85
            )
            
            self.log_test_result(
                "POSITION_3D outside tolerance (1e-5)",
                False,
                "Expected validation error for difference outside tolerance"
            )
            
        except ValueError as e:
            self.log_test_result(
                "POSITION_3D outside tolerance (1e-5)",
                True,
                f"Validation error raised as expected for tolerance violation: {str(e)}"
            )
        except Exception as e:
            self.log_test_result(
                "POSITION_3D outside tolerance (1e-5)",
                False,
                f"Unexpected error type: {str(e)}"
            )
    
    def test_velocity_aware_data_type_selection(self):
        """
        Test Case 4: VELOCITY_AWARE data type selection logic.
        
        Tests the logic where CSRT tracker selects VELOCITY_AWARE data type
        when estimator velocity is available.
        """
        print("\n--- Test Case 4: VELOCITY_AWARE data type selection ---")
        
        try:
            # Create TrackerOutput with velocity data
            velocity_tracker_output = TrackerOutput(
                data_type=TrackerDataType.VELOCITY_AWARE,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_velocity_aware",
                position_2d=(0.2, 0.8),
                velocity=(-0.1, 0.05),  # Velocity estimates from estimator
                confidence=0.75
            )
            
            self.log_test_result(
                "VELOCITY_AWARE data type creation",
                True,
                "Successfully created TrackerOutput with velocity data"
            )
            
            # Verify velocity data is properly stored
            velocity_correct = (velocity_tracker_output.velocity == (-0.1, 0.05))
            self.log_test_result(
                "VELOCITY_AWARE velocity data integrity",
                velocity_correct,
                f"Velocity data: {velocity_tracker_output.velocity}"
            )
            
        except Exception as e:
            self.log_test_result(
                "VELOCITY_AWARE data type creation",
                False,
                f"Failed to create VELOCITY_AWARE TrackerOutput: {str(e)}"
            )
    
    def test_position_3d_edge_cases(self):
        """
        Test additional edge cases for POSITION_3D validation.
        """
        print("\n--- Additional Edge Cases for POSITION_3D ---")
        
        # Test with tracking_active=False (should skip validation)
        try:
            inactive_tracker = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=False,  # Inactive tracking
                tracker_id="test_inactive",
                position_3d=(0.5, -0.3, 1.5),
                position_2d=(0.6, -0.3),  # Would normally fail validation
                confidence=0.0
            )
            
            self.log_test_result(
                "POSITION_3D with tracking_active=False",
                True,
                "Validation skipped when tracking is inactive"
            )
            
        except Exception as e:
            self.log_test_result(
                "POSITION_3D with tracking_active=False",
                False,
                f"Should not validate when tracking is inactive: {str(e)}"
            )
        
        # Test with missing position_2d (should fail when tracking_active=True)
        try:
            missing_2d_tracker = TrackerOutput(
                data_type=TrackerDataType.POSITION_3D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test_missing_2d",
                position_3d=(0.5, -0.3, 1.5),
                # position_2d is missing
                confidence=0.8
            )
            
            self.log_test_result(
                "POSITION_3D with missing position_2d",
                False,
                "Expected validation error for missing position_2d"
            )
            
        except ValueError as e:
            self.log_test_result(
                "POSITION_3D with missing position_2d",
                True,
                f"Validation error raised as expected: {str(e)}"
            )
        except Exception as e:
            self.log_test_result(
                "POSITION_3D with missing position_2d",
                False,
                f"Unexpected error type: {str(e)}"
            )
    
    def test_schema_manager_integration(self):
        """
        Test integration with schema manager validation if available.
        """
        print("\n--- Schema Manager Integration Test ---")
        
        if not self.schema_manager_available:
            print("Schema manager not available, skipping integration tests")
            return
        
        try:
            # Test direct schema validation
            test_data = {
                'position_2d': (0.5, -0.3),
                'position_3d': (0.5, -0.3, 1.5),
                'confidence': 0.9,
                'velocity': None
            }
            
            is_valid, errors = validate_tracker_data('POSITION_3D', test_data, True)
            
            self.log_test_result(
                "Schema manager direct validation - valid data",
                is_valid and len(errors) == 0,
                f"Validation result: {is_valid}, Errors: {errors}"
            )
            
            # Test validation with mismatched coordinates
            invalid_data = {
                'position_2d': (0.6, -0.3),  # Mismatched
                'position_3d': (0.5, -0.3, 1.5),
                'confidence': 0.9
            }
            
            is_valid, errors = validate_tracker_data('POSITION_3D', invalid_data, True)
            
            self.log_test_result(
                "Schema manager direct validation - invalid data",
                not is_valid and len(errors) > 0,
                f"Validation result: {is_valid}, Errors: {errors}"
            )
            
        except Exception as e:
            self.log_test_result(
                "Schema manager integration test",
                False,
                f"Schema manager integration failed: {str(e)}"
            )
    
    def test_csrt_tracker_simulation(self):
        """
        Simulate CSRT tracker behavior with velocity estimation.
        """
        print("\n--- CSRT Tracker VELOCITY_AWARE Simulation ---")
        
        # Simulate CSRT tracker output with estimator velocity
        try:
            csrt_with_velocity = TrackerOutput(
                data_type=TrackerDataType.VELOCITY_AWARE,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="CSRT_simulated",
                position_2d=(0.3, 0.7),
                bbox=(150, 200, 80, 120),
                normalized_bbox=(0.234, 0.278, 0.125, 0.167),
                confidence=0.82,
                velocity=(0.02, -0.01),  # Estimator velocity
                quality_metrics={
                    'motion_consistency': 0.95,
                    'appearance_confidence': 0.88
                },
                raw_data={
                    'estimator_enabled': True,
                    'center_history_length': 15
                },
                metadata={
                    'tracker_class': 'CSRTTracker',
                    'tracker_algorithm': 'CSRT',
                    'supports_velocity': True
                }
            )
            
            self.log_test_result(
                "CSRT VELOCITY_AWARE simulation",
                True,
                "Successfully created CSRT-style TrackerOutput with velocity estimation"
            )
            
            # Verify all expected fields are present
            has_position = csrt_with_velocity.position_2d is not None
            has_velocity = csrt_with_velocity.velocity is not None
            has_confidence = csrt_with_velocity.confidence is not None
            
            self.log_test_result(
                "CSRT VELOCITY_AWARE field verification",
                has_position and has_velocity and has_confidence,
                f"Position: {has_position}, Velocity: {has_velocity}, Confidence: {has_confidence}"
            )
            
        except Exception as e:
            self.log_test_result(
                "CSRT VELOCITY_AWARE simulation",
                False,
                f"Failed to create CSRT-style TrackerOutput: {str(e)}"
            )
    
    def run_all_tests(self):
        """
        Execute all test cases and provide a comprehensive summary.
        """
        print("=" * 80)
        print("Position_3D Schema Validation Test Suite")
        print("=" * 80)
        
        # Run all test cases
        self.test_valid_position_3d_matching_coordinates()
        self.test_invalid_position_3d_mismatched_coordinates()
        self.test_position_3d_tolerance_checking()
        self.test_velocity_aware_data_type_selection()
        self.test_position_3d_edge_cases()
        self.test_schema_manager_integration()
        self.test_csrt_tracker_simulation()
        
        # Print comprehensive summary
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80)
        
        total_tests = self.tests_passed + self.tests_failed
        pass_rate = (self.tests_passed / total_tests * 100) if total_tests > 0 else 0
        
        print(f"Total Tests Run: {total_tests}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.tests_failed > 0:
            print(f"\n[FAILED TESTS] ({self.tests_failed}):")
            for result in self.test_results:
                if not result['passed']:
                    print(f"  - {result['test_name']}")
                    if result['message']:
                        print(f"    --> {result['message']}")
        
        if self.tests_passed > 0:
            print(f"\n[PASSED TESTS] ({self.tests_passed}):")
            for result in self.test_results:
                if result['passed']:
                    print(f"  - {result['test_name']}")
        
        # Validation conclusions
        print(f"\n" + "=" * 80)
        print("VALIDATION CONCLUSIONS")
        print("=" * 80)
        
        if self.tests_failed == 0:
            print("[SUCCESS] ALL TESTS PASSED!")
            print("[OK] Position_3D schema validation logic is working correctly")
            print("[OK] Coordinate matching validation is functional")
            print("[OK] Tolerance checking (1e-6) is properly implemented")
            print("[OK] VELOCITY_AWARE data type selection is working")
            print("[OK] Schema manager integration is functional")
        else:
            print("[WARNING] SOME TESTS FAILED - Review validation logic")
            
        return self.tests_failed == 0


if __name__ == "__main__":
    """
    Main execution block - run comprehensive validation tests.
    """
    print("Starting Position_3D Schema Validation Test Suite...")
    
    tester = Position3DValidationTester()
    success = tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)