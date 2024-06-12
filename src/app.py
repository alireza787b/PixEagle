from flask import Flask, render_template
from flask_socketio import SocketIO
import socket
import json
import threading
import signal
import sys
import logging
import time
from classes.parameters import Parameters

# Initialize Flask and SocketIO
app = Flask(__name__)
socketio = SocketIO(app)

# Initialize UDP socket
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind((Parameters.FLASK_HOST, Parameters.FLASK_PORT))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag to control the listener thread
run_listener = True

def print_welcome_message():
    print("""
    ===========================================
    Welcome to the PixEagle Data Handler Script
    This script facilitates data handling between
    the PixEagle core system and the web app GUI.
    
    To stop the script, press 'Ctrl+C' or type 'q' and hit Enter.
    ===========================================
    """)

def udp_listener():
    global run_listener
    logger.info("UDP Listener started on %s:%d", Parameters.FLASK_HOST, Parameters.FLASK_PORT)
    while run_listener:
        try:
            udp_socket.settimeout(1)  # Set timeout to avoid blocking indefinitely
            try:
                message, _ = udp_socket.recvfrom(4096)
                data = json.loads(message.decode('utf-8'))
                if app.debug:
                    logger.debug(f"Received message: {message}")
                    logger.debug(f"Decoded data: {data}")
                socketio.emit('tracker_data', data)
                logger.info("Data received and emitted")
            except socket.timeout:
                continue  # Continue if timeout occurs
        except socket.error as e:
            if run_listener:
                logger.error("Socket error: %s", e)
            else:
                break
        time.sleep(0.01)  # Add a short sleep to reduce CPU usage
    logger.info("UDP Listener stopped")

@socketio.on('connect')
def handle_connect():
    logger.info('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Client disconnected')

def signal_handler(sig, frame):
    global run_listener
    logger.info("Shutting down gracefully...")
    run_listener = False
    udp_socket.close()
    socketio.stop()
    sys.exit(0)

def input_listener():
    global run_listener
    while run_listener:
        user_input = input()
        if user_input.strip().lower() == 'q':
            logger.info("Received 'q' input. Shutting down gracefully...")
            run_listener = False
            udp_socket.close()
            socketio.stop()
            sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
    print_welcome_message()
    listener_thread = threading.Thread(target=udp_listener)
    listener_thread.daemon = True
    listener_thread.start()

    input_thread = threading.Thread(target=input_listener)
    input_thread.daemon = True
    input_thread.start()

    try:
        socketio.run(app, host=Parameters.FLASK_HOST, port=Parameters.FLASK_PORT)
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        run_listener = False
        udp_socket.close()
        socketio.stop()
    finally:
        listener_thread.join()
        input_thread.join()
        logger.info("Shutdown complete")
        sys.exit(0)
