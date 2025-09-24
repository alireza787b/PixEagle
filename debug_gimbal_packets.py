#!/usr/bin/env python3
"""
Debug Gimbal UDP Packets
========================

This script captures and logs the exact UDP packets sent by your gimbal
to help debug the parsing differences between test_gimbal_udp.py and production code.
"""

import socket
import time
import threading
from datetime import datetime

def capture_gimbal_packets():
    """Capture and display raw gimbal packets"""
    print("=== Gimbal Packet Debugger ===")
    print("Listening on UDP port 9004 for gimbal packets...")
    print("Press Ctrl+C to stop\n")

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', 9004))
    sock.settimeout(1.0)  # 1 second timeout

    packet_count = 0

    try:
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                packet_count += 1
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                # Decode as UTF-8 string
                try:
                    packet_str = data.decode('utf-8', errors='replace')
                    print(f"[{timestamp}] Packet #{packet_count} from {addr}:")
                    print(f"  String: '{packet_str}'")
                    print(f"  Length: {len(data)} bytes")
                    print(f"  Raw bytes: {data.hex()}")

                    # Check for known identifiers
                    identifiers_found = []
                    for identifier in ['GAC', 'GIC', 'TRC', 'OFT', '#tp', '#TP']:
                        if identifier in packet_str:
                            identifiers_found.append(identifier)

                    if identifiers_found:
                        print(f"  Identifiers found: {identifiers_found}")

                        # Try to extract angle data if GAC or GIC found
                        for id_str in ['GAC', 'GIC']:
                            if id_str in packet_str:
                                id_pos = packet_str.find(id_str)
                                if id_pos != -1:
                                    angle_start = id_pos + 3
                                    angle_data = packet_str[angle_start:angle_start + 12]
                                    print(f"  Angle data after {id_str}: '{angle_data}' (length: {len(angle_data)})")

                    print()  # Empty line for readability

                except UnicodeDecodeError:
                    print(f"[{timestamp}] Packet #{packet_count} from {addr} (Binary data):")
                    print(f"  Raw bytes: {data.hex()}")
                    print()

            except socket.timeout:
                continue

    except KeyboardInterrupt:
        print(f"\nCapture stopped. Total packets received: {packet_count}")
    finally:
        sock.close()

def test_parsing_logic():
    """Test parsing logic with sample data"""
    print("\n=== Testing Parsing Logic ===")

    # Sample data formats that might be sent
    test_packets = [
        "#tpPG2rGAC00640259FFE426",  # Standard GAC response format
        "#tpPG2rGIC00640259FFE426",  # Standard GIC response format
        "#tpDP9wOFT64025910",        # Broadcast format
        "#TP0G2rGAC00640259FFE426",  # Variation with #TP
    ]

    for i, packet in enumerate(test_packets, 1):
        print(f"Test packet {i}: '{packet}'")

        # Test GAC parsing
        if 'GAC' in packet:
            gac_pos = packet.find('GAC') + 3
            angle_data = packet[gac_pos:gac_pos + 12]
            print(f"  GAC angle data: '{angle_data}' (length: {len(angle_data)})")

            if len(angle_data) == 12:
                try:
                    # Parse hex values
                    yaw_hex = angle_data[0:4]
                    pitch_hex = angle_data[4:8]
                    roll_hex = angle_data[8:12]

                    # Convert to signed integers
                    yaw_raw = int(yaw_hex, 16)
                    pitch_raw = int(pitch_hex, 16)
                    roll_raw = int(roll_hex, 16)

                    # Handle signed 16-bit conversion
                    if yaw_raw > 32767: yaw_raw -= 65536
                    if pitch_raw > 32767: pitch_raw -= 65536
                    if roll_raw > 32767: roll_raw -= 65536

                    # Convert to degrees
                    yaw = yaw_raw / 100.0
                    pitch = pitch_raw / 100.0
                    roll = roll_raw / 100.0

                    print(f"  Parsed angles: yaw={yaw:.2f}°, pitch={pitch:.2f}°, roll={roll:.2f}°")

                except Exception as e:
                    print(f"  Parsing error: {e}")
        print()

if __name__ == "__main__":
    # Test parsing logic first
    test_parsing_logic()

    # Then start packet capture
    input("Press Enter to start packet capture (make sure gimbal is sending data)...")
    capture_gimbal_packets()