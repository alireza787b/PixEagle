import socket
import json
import threading
import time
from datetime import datetime
from classes.parameters import Parameters  # Adjust the import based on your file structure
import signal
import sys

# Read the UDP host and port from the Parameters class
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

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    listener_thread = threading.Thread(target=input_listener)
    listener_thread.daemon = True
    listener_thread.start()

    while run:
        data = {
            'bounding_box': [time.time() % 10, (time.time() % 10) + 1, (time.time() % 10) + 2, (time.time() % 10) + 3],
            'center': [time.time() % 10, (time.time() % 10) + 1],
            'timestamp': datetime.utcnow().isoformat(),
            'tracker_started': True
        }
        message = json.dumps(data)
        udp_socket.sendto(message.encode('utf-8'), server_address)
        print(f"Sent data: {data}")
        time.sleep(1)
