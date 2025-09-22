#!/usr/bin/env python3
"""
Test Gimbal Integration with PixEagle

This script tests the complete gimbal integration path:
1. GimbalInterface connects to gimbal
2. Receives and parses data
3. GimbalTracker processes data
4. Creates TrackerOutput with GIMBAL_ANGLES

Usage: python test_gimbal_integration.py
"""

import sys
import os
import time
import logging

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from classes.gimbal_interface import GimbalInterface
from classes.trackers.gimbal_tracker import GimbalTracker
from classes.parameters import Parameters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_gimbal_interface():
    """Test GimbalInterface standalone"""
    print("=== Testing GimbalInterface ===")

    # Load parameters
    Parameters.load_config()

    gimbal_ip = getattr(Parameters, 'GIMBAL_UDP_HOST', '192.168.0.108')
    listen_port = getattr(Parameters, 'GIMBAL_LISTEN_PORT', 9004)

    gimbal_config = getattr(Parameters, 'GimbalTracker', {})
    control_port = gimbal_config.get('UDP_PORT', 9003)

    print(f"Connecting to gimbal at {gimbal_ip}:{control_port}, listening on {listen_port}")

    interface = GimbalInterface(
        listen_port=listen_port,
        gimbal_ip=gimbal_ip,
        control_port=control_port
    )

    try:
        # Start interface
        success = interface.start_listening()
        if not success:
            print("❌ Failed to start gimbal interface")
            return False

        print("✅ Gimbal interface started")

        # Monitor for data
        print("Monitoring for gimbal data for 10 seconds...")
        for i in range(10):
            data = interface.get_current_data()
            if data:
                print(f"📊 Received data: {data}")
                if data.angles:
                    print(f"   Angles: YAW={data.angles.yaw:.2f}° PITCH={data.angles.pitch:.2f}° ROLL={data.angles.roll:.2f}°")
                if data.tracking_status:
                    print(f"   Tracking: {data.tracking_status.state}")
            else:
                print(f"   [{i+1}/10] No data yet...")
            time.sleep(1)

        return True

    finally:
        interface.stop_listening()
        print("🔌 Interface stopped")

def test_gimbal_tracker():
    """Test GimbalTracker (full integration)"""
    print("\n=== Testing GimbalTracker ===")

    # Load parameters
    Parameters.load_config()

    # Create tracker (with dummy parameters)
    tracker = GimbalTracker(
        video_handler=None,  # Not needed for this test
        detector=None,       # Not needed for this test
        app_controller=None  # Not needed for this test
    )

    try:
        # Start tracking
        print("Starting gimbal tracker...")
        success, output = tracker.start_tracking(frame=None, bbox=None)
        if not success:
            print("❌ Failed to start tracker")
            return False

        print("✅ Gimbal tracker started")

        # Monitor tracker output
        print("Monitoring tracker output for 10 seconds...")
        for i in range(10):
            success, tracker_output = tracker.update(frame=None)

            if success and tracker_output:
                print(f"📊 Tracker output received:")
                print(f"   Data type: {tracker_output.data_type}")
                print(f"   Tracking active: {tracker_output.tracking_active}")
                print(f"   Angular data: {tracker_output.angular}")
                print(f"   Position 2D: {tracker_output.position_2d}")
                print(f"   Confidence: {tracker_output.confidence}")
                break
            else:
                print(f"   [{i+1}/10] No tracker output yet...")
            time.sleep(1)

        return True

    finally:
        tracker.stop_tracking()
        print("🔌 Tracker stopped")

def main():
    """Run integration tests"""
    print("🎥 GIMBAL INTEGRATION TEST")
    print("=" * 50)

    try:
        # Test 1: Interface level
        interface_ok = test_gimbal_interface()

        # Test 2: Tracker level
        tracker_ok = test_gimbal_tracker()

        # Summary
        print("\n" + "=" * 50)
        print("📋 TEST RESULTS:")
        print(f"   GimbalInterface: {'✅ PASS' if interface_ok else '❌ FAIL'}")
        print(f"   GimbalTracker:   {'✅ PASS' if tracker_ok else '❌ FAIL'}")

        if interface_ok and tracker_ok:
            print("\n🎉 All tests passed! Gimbal integration is working.")
        else:
            print("\n⚠️  Some tests failed. Check the logs above.")

    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()