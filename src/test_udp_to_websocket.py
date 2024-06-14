import socket
import json
import threading
import time
from datetime import datetime
import signal
import sys
from classes.parameters import Parameters

# UDP server configuration
UDP_HOST = Parameters.UDP_HOST
UDP_PORT = Parameters.UDP_PORT

# Create a UDP socket
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_address = (UDP_HOST, UDP_PORT)

run = True

def signal_handler(sig, frame):
    global run
    print("Exiting...")
    run = False
    udp_socket.close()
    sys.exit(0)

def input_listener():
    global run
    while run:
        user_input = input()
        if user_input.strip().lower() == 'q':
            print("Received 'q' input. Exiting...")
            run = False
            udp_socket.close()
            sys.exit(0)

def normalize(value, min_value, max_value):
    return (value - min_value) / (max_value - min_value) * 2 - 1

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    listener_thread = threading.Thread(target=input_listener)
    listener_thread.daemon = True
    listener_thread.start()

    while run:
        # Simulate bounding box and center
        x = time.time() % 10
        y = (time.time() % 10) + 1
        width = (time.time() % 10) + 2
        height = (time.time() % 10) + 3

        # Calculate center
        center_x = x + width / 2
        center_y = y + height / 2

        # Normalize bounding box and center
        normalized_bounding_box = [
            normalize(x, 0, 30),
            normalize(y, 0, 30),
            normalize(width, 0, 30),
            normalize(height, 0, 30)
        ]
        normalized_center = [
            normalize(center_x, 0, 30),
            normalize(center_y, 0, 30)
        ]

        data = {
            'bounding_box': normalized_bounding_box,
            'center': normalized_center,
            'timestamp': datetime.utcnow().isoformat(),
            'tracker_started': True
        }
        message = json.dumps(data)
        udp_socket.sendto(message.encode('utf-8'), server_address)
        print(f"Sent data: {data}")
        time.sleep(1)
