# src/classes/video_streamer.py

from flask import Flask, Response
import threading
import cv2

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

    def video_feed(self):
        """
        Flask route to serve the video feed.

        Yields:
            bytes: The next frame in JPEG format.
        """
        def generate():
            while True:
                frame = self.video_handler.get_frame()
                if frame is None:
                    break
                ret, buffer = cv2.imencode('.jpg', frame)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    def start(self, host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_HOST):
        """
        Start the Flask server in a new thread.

        Args:
            host (str): The hostname to listen on.
            port (int): The port to listen on.
        """
        if self.server is None:
            self.server = threading.Thread(target=self.app.run, kwargs={'host': host, 'port': port})
            self.server.start()

    def stop(self):
        """
        Stop the Flask server.
        """
        if self.server:
            # Logic to stop the Flask server
            self.server.join()
            self.server = None
