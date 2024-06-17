# src/classes/video_streamer.py

from flask import Flask, Response
import threading
import cv2
import logging
import time
from werkzeug.serving import make_server
from classes.parameters import Parameters

class VideoStreamer:
    def __init__(self, video_handler):
        """
        Initialize the VideoStreamer with a video handler.

        Args:
            video_handler (VideoHandler): An instance of the VideoHandler class.
        """
        self.video_handler = video_handler
        self.app = Flask(__name__)
        self.app.add_url_rule('/video_feed', 'video_feed', self.video_feed)
        self.server = None
        self.server_thread = None
        self.frame_rate = Parameters.STREAM_FPS
        self.width = Parameters.STREAM_WIDTH
        self.height = Parameters.STREAM_HEIGHT
        self.quality = Parameters.STREAM_QUALITY
        self.processed_osd = Parameters.STREAM_PROCESSED_OSD
        self.last_frame_time = 0
        self.frame_interval = 1.0 / self.frame_rate

    def video_feed(self):
        """
        Flask route to serve the video feed.

        Yields:
            bytes: The next frame in JPEG format.
        """
        def generate():
            while True:
                current_time = time.time()
                if current_time - self.last_frame_time >= self.frame_interval:
                    if self.processed_osd:
                        frame = self.video_handler.current_osd_frame
                    else:
                        frame = self.video_handler.current_raw_frame

                    if frame is None:
                        break

                    frame = cv2.resize(frame, (self.width, self.height))
                    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
                    frame = buffer.tobytes()
                    self.last_frame_time = current_time
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    time.sleep(self.frame_interval - (current_time - self.last_frame_time))
        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def start(self, host='0.0.0.0', port=5000):
        """
        Start the Flask server in a new thread.

        Args:
            host (str): The hostname to listen on.
            port (int): The port to listen on.
        """
        if self.server is None:
            self.server = make_server(host, port, self.app)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.start()
            logging.info(f"Started Flask server on {host}:{port}")

    def stop(self):
        """
        Stop the Flask server.
        """
        if self.server:
            self.server.shutdown()
            self.server_thread.join()
            self.server = None
            logging.info("Stopped Flask server")
