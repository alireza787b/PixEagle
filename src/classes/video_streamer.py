import cv2
import base64
import logging
from classes.websocket_manager import websocket_manager
from classes.parameters import Parameters

class VideoStreamer:
    def __init__(self, compression_quality=Parameters.STREAM_COMPRESSION_QUALITY, 
                 resize_dim=Parameters.STREAM_RESIZE_DIM, target_fps=Parameters.STREAM_FPS):
        self.compression_quality = compression_quality
        self.resize_dim = resize_dim
        self.target_fps = target_fps
        self.last_frame_time = 0
        logging.info(f"VideoStreamer initialized with compression_quality: {self.compression_quality}, resize_dim: {self.resize_dim}, target_fps: {self.target_fps}")

    def process_frame(self, frame):
        logging.debug("Processing frame")
        try:
            frame_resized = cv2.resize(frame, self.resize_dim)
            logging.debug(f"Frame resized to: {self.resize_dim}")
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compression_quality]
            _, buffer = cv2.imencode('.jpg', frame_resized, encode_param)
            logging.debug("Frame encoded to JPEG format")
            frame_encoded = base64.b64encode(buffer).decode('utf-8')
            logging.debug("Frame encoded to base64")
            return frame_encoded
        except Exception as e:
            logging.error(f"Error in processing frame: {e}")
            return None

    async def send_frame(self, frame):
        current_time = cv2.getTickCount() / cv2.getTickFrequency()
        if current_time - self.last_frame_time < 1.0 / self.target_fps:
            return
        logging.debug("Sending frame to WebSocket")
        frame_encoded = self.process_frame(frame)
        if frame_encoded:
            await websocket_manager.broadcast(frame_encoded)
        self.last_frame_time = current_time
        logging.debug("Frame sent to WebSocket")
