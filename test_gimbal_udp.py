#!/usr/bin/env python3
"""
Simple Gimbal UDP Test Script

This script tests UDP communication with the gimbal using the SIP protocol
to verify that the gimbal is responding before testing with PixEagle.

Usage:
    python test_gimbal_udp.py

Expected behavior:
1. Script starts listening on port 9004
2. Sends commands to gimbal on port 9003
3. Displays any responses received
4. Shows tracking status and angles if gimbal is active
"""

import socket
import time
import threading
from datetime import datetime

# Configuration - adjust these to match your gimbal
GIMBAL_IP = "192.168.144.108"
CONTROL_PORT = 9003
LISTEN_PORT = 9004

def build_command(address_dest: str, control: str, command: str, data: str = "00") -> str:
    """Build SIP protocol command"""
    frame = "#TP"
    src = "P"
    length = "2"

    cmd = f"{frame}{src}{address_dest}{length}{control}{command}{data}"
    crc = sum(cmd.encode('ascii')) & 0xFF
    cmd += f"{crc:02X}"

    return cmd

def send_command(sock: socket.socket, command: str) -> bool:
    """Send command to gimbal"""
    try:
        sock.sendto(command.encode('ascii'), (GIMBAL_IP, CONTROL_PORT))
        print(f"📤 Sent: {command}")
        return True
    except Exception as e:
        print(f"❌ Send failed: {e}")
        return False

def listen_for_responses(listen_sock: socket.socket):
    """Listen for gimbal responses"""
    print("🔄 Starting response listener...")

    while True:
        try:
            data, addr = listen_sock.recvfrom(4096)
            response = data.decode('utf-8', errors='replace').strip()

            if response:
                timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                print(f"📥 [{timestamp}] From {addr}: {response}")

                # Parse response type
                if "GAC" in response or "GIC" in response:
                    print(f"   └─ ✅ ANGLE DATA RECEIVED")
                elif "TRC" in response:
                    print(f"   └─ 🎯 TRACKING STATUS RECEIVED")

        except socket.timeout:
            continue
        except Exception as e:
            print(f"⚠️ Listen error: {e}")

def main():
    print("=" * 60)
    print("🎥 GIMBAL UDP COMMUNICATION TEST")
    print("=" * 60)
    print(f"Gimbal IP: {GIMBAL_IP}")
    print(f"Control Port: {CONTROL_PORT}")
    print(f"Listen Port: {LISTEN_PORT}")
    print("=" * 60)

    # Create sockets
    try:
        # Control socket for sending commands
        control_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Listen socket for receiving responses
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind(('0.0.0.0', LISTEN_PORT))
        listen_sock.settimeout(0.1)

        print("✅ Sockets created successfully")

    except Exception as e:
        print(f"❌ Socket setup failed: {e}")
        return

    # Start response listener in background
    listener_thread = threading.Thread(target=listen_for_responses, args=(listen_sock,), daemon=True)
    listener_thread.start()

    print("\n🚀 Starting gimbal communication test...")
    print("Press Ctrl+C to stop\n")

    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"\n--- Test Iteration {iteration} ---")

            # Test 1: Query spatial fixed angles (absolute coordinates)
            print("1️⃣ Querying spatial fixed angles (GIC)...")
            cmd = build_command("G", "r", "GIC", "00")
            send_command(control_sock, cmd)
            time.sleep(1)

            # Test 2: Query tracking status
            print("2️⃣ Querying tracking status (TRC)...")
            cmd = build_command("D", "r", "TRC", "00")
            send_command(control_sock, cmd)
            time.sleep(1)

            # Test 3: Query gimbal body angles (relative coordinates)
            print("3️⃣ Querying gimbal body angles (GAC)...")
            cmd = build_command("G", "r", "GAC", "00")
            send_command(control_sock, cmd)
            time.sleep(1)

            print("⏳ Waiting for responses...")
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n⏹️ Test stopped by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
    finally:
        try:
            control_sock.close()
            listen_sock.close()
        except:
            pass
        print("👋 Test completed")

if __name__ == "__main__":
    main()