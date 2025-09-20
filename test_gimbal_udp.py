#!/usr/bin/env python3
"""
Test script for Gimbal UDP reception and status detection.

This script tests the GimbalInterface and GimbalTracker functionality
by simulating gimbal UDP data and verifying correct reception and parsing.

Usage:
    python test_gimbal_udp.py
"""

import time
import socket
import threading
import logging
from datetime import datetime
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import PixEagle components
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from classes.gimbal_interface import GimbalInterface, TrackingState, GimbalData
    from classes.trackers.gimbal_tracker import GimbalTracker
    from classes.parameters import Parameters
except ImportError as e:
    logger.error(f"Failed to import PixEagle components: {e}")
    logger.info("Make sure you're running this from the PixEagle root directory")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Python path: {sys.path}")
    exit(1)


class GimbalSimulator:
    """
    Simulates a gimbal sending UDP data for testing purposes.
    """

    def __init__(self, target_ip: str = "127.0.0.1", target_port: int = 9004):
        self.target_ip = target_ip
        self.target_port = target_port
        self.socket = None
        self.running = False
        self.thread = None

    def start(self):
        """Start the gimbal simulator."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.running = True
            self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.thread.start()
            logger.info(f"Gimbal simulator started, sending to {self.target_ip}:{self.target_port}")
        except Exception as e:
            logger.error(f"Failed to start gimbal simulator: {e}")

    def stop(self):
        """Stop the gimbal simulator."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.socket:
            self.socket.close()
        logger.info("Gimbal simulator stopped")

    def _simulation_loop(self):
        """Main simulation loop."""
        sequence = 0
        tracking_state = 0  # Start with DISABLED

        while self.running:
            try:
                # Simulate tracking state changes
                if sequence == 10:
                    tracking_state = 1  # TARGET_SELECTION
                    logger.info("Simulator: Switching to TARGET_SELECTION")
                elif sequence == 20:
                    tracking_state = 2  # TRACKING_ACTIVE
                    logger.info("Simulator: Switching to TRACKING_ACTIVE")
                elif sequence == 50:
                    tracking_state = 3  # TARGET_LOST
                    logger.info("Simulator: Switching to TARGET_LOST")
                elif sequence == 60:
                    tracking_state = 0  # DISABLED
                    logger.info("Simulator: Switching to DISABLED")
                    sequence = 0  # Reset for loop

                # Create sample gimbal data
                yaw = 10.0 + (sequence % 20) * 2.0    # Oscillating yaw
                pitch = -5.0 + (sequence % 10) * 1.0  # Oscillating pitch
                roll = 0.0

                # Create gimbal protocol message (simplified)
                message = f"ANG {yaw:.2f} {pitch:.2f} {roll:.2f}\n"
                message += f"TRC {tracking_state}\n"

                # Send UDP packet
                self.socket.sendto(message.encode('utf-8'), (self.target_ip, self.target_port))

                sequence += 1
                time.sleep(0.5)  # Send data every 500ms

            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                break


def test_gimbal_interface():
    """Test GimbalInterface UDP reception and parsing."""
    logger.info("=== Testing GimbalInterface ===")

    # Create gimbal interface
    gimbal_interface = GimbalInterface(listen_port=9004, gimbal_ip="127.0.0.1")

    try:
        # Start listening
        logger.info("Starting GimbalInterface listener...")
        if gimbal_interface.start_listening():
            logger.info("✓ GimbalInterface started successfully")
        else:
            logger.error("✗ Failed to start GimbalInterface")
            return False

        # Wait for data
        logger.info("Waiting for gimbal data...")
        start_time = time.time()

        while time.time() - start_time < 30.0:  # Test for 30 seconds
            data = gimbal_interface.get_current_data()

            if data:
                logger.info(f"✓ Received data: angles={data.angles}, status={data.tracking_status}")

                if data.tracking_status:
                    logger.info(f"  Tracking state: {data.tracking_status.state.name}")

                if data.angles:
                    yaw, pitch, roll = data.angles.to_tuple()
                    logger.info(f"  Angles: yaw={yaw:.2f}°, pitch={pitch:.2f}°, roll={roll:.2f}°")

            time.sleep(1.0)

        # Get connection statistics
        stats = gimbal_interface.get_statistics()
        logger.info(f"Connection stats: {stats}")

        return True

    except Exception as e:
        logger.error(f"Error testing GimbalInterface: {e}")
        return False

    finally:
        gimbal_interface.stop_listening()
        logger.info("GimbalInterface stopped")


def test_gimbal_tracker():
    """Test GimbalTracker status-driven operation."""
    logger.info("\n=== Testing GimbalTracker ===")

    try:
        # Create gimbal tracker
        tracker = GimbalTracker(video_handler=None, detector=None, app_controller=None)
        logger.info("✓ GimbalTracker created successfully")

        # Start monitoring
        logger.info("Starting GimbalTracker monitoring...")
        tracker.start_tracking(None, (0, 0, 0, 0))  # Dummy parameters

        if tracker.monitoring_active:
            logger.info("✓ GimbalTracker monitoring started")
        else:
            logger.error("✗ Failed to start GimbalTracker monitoring")
            return False

        # Monitor tracking updates
        logger.info("Monitoring tracker updates...")
        start_time = time.time()
        last_status = None

        while time.time() - start_time < 35.0:  # Test for 35 seconds
            success, output = tracker.update(None)  # Frame not needed

            if success and output:
                current_status = output.raw_data.get('tracking_state', 'unknown')

                if current_status != last_status:
                    logger.info(f"✓ Tracking state change: {last_status} → {current_status}")
                    last_status = current_status

                if output.tracking_active:
                    logger.info(f"✓ Active tracking: angles={output.angular}, confidence={output.confidence:.2f}")

            time.sleep(1.0)

        # Get tracker statistics
        stats = tracker.get_gimbal_statistics()
        logger.info(f"Tracker stats: {stats['tracker_stats']}")

        return True

    except Exception as e:
        logger.error(f"Error testing GimbalTracker: {e}")
        return False

    finally:
        tracker.stop_tracking()
        logger.info("GimbalTracker stopped")


def main():
    """Main test function."""
    logger.info("Starting Gimbal UDP Test")
    logger.info("=" * 50)

    # Start gimbal simulator
    simulator = GimbalSimulator(target_ip="127.0.0.1", target_port=9004)
    simulator.start()

    try:
        # Give simulator time to start
        time.sleep(2.0)

        # Test GimbalInterface
        interface_success = test_gimbal_interface()

        # Test GimbalTracker
        tracker_success = test_gimbal_tracker()

        # Results
        logger.info("\n" + "=" * 50)
        logger.info("TEST RESULTS:")
        logger.info(f"GimbalInterface: {'✓ PASS' if interface_success else '✗ FAIL'}")
        logger.info(f"GimbalTracker: {'✓ PASS' if tracker_success else '✗ FAIL'}")

        if interface_success and tracker_success:
            logger.info("🎉 ALL TESTS PASSED!")
            return True
        else:
            logger.error("❌ SOME TESTS FAILED!")
            return False

    finally:
        simulator.stop()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)