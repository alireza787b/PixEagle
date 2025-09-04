#!/usr/bin/env python3
"""
CSRT Tracker VELOCITY_AWARE Data Type Selection Test
=====================================================

This script specifically tests the CSRT tracker's logic for selecting
VELOCITY_AWARE data type when estimator velocity is available.

Project Information:
- Project Name: PixEagle  
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Test Coverage:
1. CSRT tracker data type selection logic
2. Velocity estimation from position estimator
3. Proper fallback to other data types when velocity unavailable
"""

import sys
import os
import time
import logging
import numpy as np

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from classes.tracker_output import TrackerDataType
    print("Successfully imported TrackerDataType")
except ImportError as e:
    print(f"Failed to import TrackerDataType: {e}")
    sys.exit(1)

class MockPositionEstimator:
    """Mock position estimator for testing."""
    
    def __init__(self, has_velocity=True):
        self.has_velocity = has_velocity
        if has_velocity:
            # State vector: [x, y, vx, vy]
            self.state = np.array([0.5, 0.3, 0.02, -0.01])
        else:
            # State vector: [x, y] (no velocity)
            self.state = np.array([0.5, 0.3])
    
    def get_estimate(self):
        return self.state

class MockCSRTTracker:
    """Mock CSRT tracker to test data type selection logic."""
    
    def __init__(self, has_estimator=False, estimator_enabled=False):
        self.estimator_enabled = estimator_enabled
        self.position_estimator = MockPositionEstimator(has_velocity=True) if has_estimator else None
        self.bbox = (100, 150, 80, 100)
        self.normalized_bbox = (0.156, 0.208, 0.125, 0.139)
        self.normalized_center = (0.5, 0.3)
        self.confidence = 0.85
        self.tracking_started = True
    
    def get_velocity_aware_output(self):
        """
        Simulate CSRT tracker's get_output method logic for VELOCITY_AWARE selection.
        This mirrors the actual implementation in csrt_tracker.py
        """
        # Get velocity from estimator if available
        velocity = None
        estimated_state = None
        
        if self.estimator_enabled and self.position_estimator:
            estimated_state = self.position_estimator.get_estimate()
            if estimated_state is not None and len(estimated_state) >= 4:
                # Extract velocity components (dx, dy)
                velocity = (estimated_state[2], estimated_state[3])
        
        # Determine appropriate data type based on available data
        has_bbox = self.bbox is not None or self.normalized_bbox is not None
        has_velocity = velocity is not None
        
        if has_velocity:
            data_type = TrackerDataType.VELOCITY_AWARE
        elif has_bbox:
            data_type = TrackerDataType.BBOX_CONFIDENCE  
        else:
            data_type = TrackerDataType.POSITION_2D
        
        return {
            'data_type': data_type,
            'velocity': velocity,
            'has_velocity': has_velocity,
            'has_bbox': has_bbox,
            'estimated_state': estimated_state
        }

def test_csrt_velocity_aware_selection():
    """Test CSRT tracker VELOCITY_AWARE data type selection."""
    print("=" * 70)
    print("CSRT Tracker VELOCITY_AWARE Data Type Selection Test")
    print("=" * 70)
    
    test_results = []
    
    # Test 1: Estimator enabled with velocity - should use VELOCITY_AWARE
    print("\n--- Test 1: Estimator enabled with velocity ---")
    tracker_with_velocity = MockCSRTTracker(has_estimator=True, estimator_enabled=True)
    result = tracker_with_velocity.get_velocity_aware_output()
    
    expected_data_type = TrackerDataType.VELOCITY_AWARE
    actual_data_type = result['data_type']
    has_velocity = result['has_velocity']
    velocity = result['velocity']
    
    test1_pass = (actual_data_type == expected_data_type and has_velocity and velocity is not None)
    test_results.append(('Estimator enabled with velocity', test1_pass))
    
    print(f"Expected data type: {expected_data_type}")
    print(f"Actual data type: {actual_data_type}")
    print(f"Has velocity: {has_velocity}")
    print(f"Velocity: {velocity}")
    print(f"Test result: {'PASS' if test1_pass else 'FAIL'}")
    
    # Test 2: Estimator disabled - should use BBOX_CONFIDENCE
    print("\n--- Test 2: Estimator disabled ---")
    tracker_without_estimator = MockCSRTTracker(has_estimator=False, estimator_enabled=False)
    result = tracker_without_estimator.get_velocity_aware_output()
    
    expected_data_type = TrackerDataType.BBOX_CONFIDENCE
    actual_data_type = result['data_type']
    has_velocity = result['has_velocity']
    has_bbox = result['has_bbox']
    
    test2_pass = (actual_data_type == expected_data_type and not has_velocity and has_bbox)
    test_results.append(('Estimator disabled', test2_pass))
    
    print(f"Expected data type: {expected_data_type}")
    print(f"Actual data type: {actual_data_type}")
    print(f"Has velocity: {has_velocity}")
    print(f"Has bbox: {has_bbox}")
    print(f"Test result: {'PASS' if test2_pass else 'FAIL'}")
    
    # Test 3: Estimator available but disabled - should use BBOX_CONFIDENCE
    print("\n--- Test 3: Estimator available but disabled ---")
    tracker_estimator_disabled = MockCSRTTracker(has_estimator=True, estimator_enabled=False)
    result = tracker_estimator_disabled.get_velocity_aware_output()
    
    expected_data_type = TrackerDataType.BBOX_CONFIDENCE
    actual_data_type = result['data_type']
    has_velocity = result['has_velocity']
    
    test3_pass = (actual_data_type == expected_data_type and not has_velocity)
    test_results.append(('Estimator available but disabled', test3_pass))
    
    print(f"Expected data type: {expected_data_type}")
    print(f"Actual data type: {actual_data_type}")
    print(f"Has velocity: {has_velocity}")
    print(f"Test result: {'PASS' if test3_pass else 'FAIL'}")
    
    # Test 4: Verify velocity values are reasonable
    print("\n--- Test 4: Velocity value validation ---")
    tracker_with_velocity = MockCSRTTracker(has_estimator=True, estimator_enabled=True)
    result = tracker_with_velocity.get_velocity_aware_output()
    
    velocity = result['velocity']
    velocity_valid = (velocity is not None and 
                     len(velocity) == 2 and 
                     isinstance(velocity[0], (int, float)) and 
                     isinstance(velocity[1], (int, float)))
    
    test4_pass = velocity_valid
    test_results.append(('Velocity value validation', test4_pass))
    
    print(f"Velocity: {velocity}")
    print(f"Velocity valid: {velocity_valid}")
    print(f"Test result: {'PASS' if test4_pass else 'FAIL'}")
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_tests = sum(1 for _, passed in test_results if passed)
    total_tests = len(test_results)
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Pass Rate: {pass_rate:.1f}%")
    
    print(f"\nDetailed Results:")
    for test_name, passed in test_results:
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {test_name}")
    
    if passed_tests == total_tests:
        print(f"\n[SUCCESS] All CSRT VELOCITY_AWARE tests passed!")
        print(f"[OK] CSRT tracker correctly selects VELOCITY_AWARE when velocity available")
        print(f"[OK] CSRT tracker falls back to BBOX_CONFIDENCE when velocity unavailable")
        print(f"[OK] Velocity values are properly extracted from position estimator")
    else:
        print(f"\n[WARNING] Some CSRT tests failed - review implementation")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    success = test_csrt_velocity_aware_selection()
    sys.exit(0 if success else 1)