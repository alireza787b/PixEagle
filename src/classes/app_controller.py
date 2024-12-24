# src/classes/app_controller.py

import asyncio
import logging
import time
import numpy as np
from typing import Dict, Optional, Tuple
import cv2

from classes.parameters import Parameters
from classes.follower import Follower
from classes.setpoint_sender import SetpointSender
from classes.video_handler import VideoHandler
from classes.trackers.csrt_tracker import CSRTTracker
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.px4_interface_manager import PX4InterfaceManager
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler
from classes.osd_handler import OSDHandler
from classes.gstreamer_handler import GStreamerHandler  # QGC pipeline
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator
from classes.detectors.detector_factory import create_detector
from classes.webrtc_handler import WebRTCHandler


# We'll define an import for the new GStreamerHTTPHandler below.
# If you keep it in a separate file, import from that file. For simplicity, we'll import from fastapi_handler if needed.
try:
    from classes.fastapi_handler import GStreamerHTTPHandler
except ImportError:
    GStreamerHTTPHandler = None


class AppController:
    def __init__(self):
        """
        Initializes the AppController with necessary components and starts the FastAPI handler.
        """
        logging.debug("Initializing AppController...")

        # MAVLink Manager
        self.mavlink_data_manager = MavlinkDataManager(
            mavlink_host=Parameters.MAVLINK_HOST,
            mavlink_port=Parameters.MAVLINK_PORT,
            polling_interval=Parameters.MAVLINK_POLLING_INTERVAL,
            data_points=Parameters.MAVLINK_DATA_POINTS,
            enabled=Parameters.MAVLINK_ENABLED
        )
        if Parameters.MAVLINK_ENABLED:
            self.mavlink_data_manager.start_polling()

        # Frame Preprocessor
        self.preprocessor = FramePreprocessor() if Parameters.ENABLE_PREPROCESSING else None

        # Estimator
        self.estimator = create_estimator(Parameters.ESTIMATOR_TYPE)

        # Video + Tracking + Segmentor
        self.video_handler = VideoHandler()
        self.detector = create_detector(Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(
            Parameters.DEFAULT_TRACKING_ALGORITHM,
            self.video_handler,
            self.detector,
            self
        )
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)

        # State variables
        self.tracking_failure_start_time = None
        self.frame_counter = 0
        self.tracking_started = False
        self.segmentation_active = False
        self.current_frame = None

        # If we show a video window
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.namedWindow("Video")
            cv2.setMouseCallback("Video", self.on_mouse_click)

        # PX4 / Telemetry
        self.px4_interface = PX4InterfaceManager(app_controller=self)
        self.following_active = False
        self.follower = None
        self.setpoint_sender = None
        self.telemetry_handler = TelemetryHandler(self, lambda: self.tracking_started)

        # Start FastAPI
        logging.debug("Initializing FastAPIHandler...")
        self.api_handler = FastAPIHandler(self)
        logging.debug("FastAPIHandler initialized.")

        # OSD
        self.osd_handler = OSDHandler(self)

        # GStreamer pipelines
        self.gstreamer_handler = None  # QGC pipeline
        self.gstreamer_http_handler = None  # HTTP pipeline
        if Parameters.ENABLE_GSTREAMER_STREAM:
            # Decide which pipeline to use based on a new parameter GSTREAMER_MODE
            # 'QGC' for QGroundControl, 'HTTP' for chunked streaming, etc.
            mode = getattr(Parameters, "GSTREAMER_MODE", "QGC")  # default to QGC if not in config
            if mode == "QGC":
                self.gstreamer_handler = GStreamerHandler()
                self.gstreamer_handler.initialize_stream()
                logging.info("QGC GStreamer pipeline initialized.")
            elif mode == "HTTP":
                # Attempt to create the GStreamerHTTPHandler
                from classes.gstreamer_http_handler import get_http_handler_or_none
                self.gstreamer_http_handler = get_http_handler_or_none()
                if self.gstreamer_http_handler:
                    logging.info("HTTP-based GStreamer pipeline initialized.")
                else:
                    logging.warning("Could not initialize GStreamerHTTPHandler, skipping.")
            else:
                logging.warning(f"Unknown GSTREAMER_MODE='{mode}'. No pipeline started.")


        # WebRTC
        if getattr(Parameters, "ENABLE_WEBRTC", False):
            self.webrtc_handler = WebRTCHandler()
            self.webrtc_handler.start()
        else:
            self.webrtc_handler = None

        logging.info("AppController initialized.")

    def on_mouse_click(self, event: int, x: int, y: int, flags: int, param: any):
        """
        If segmentation is active, pass clicks to handle_user_click().
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame: np.ndarray):
        """
        Toggles the tracking state. If not tracking, let user select ROI or start automatically.
        If already tracking, stop tracking.
        """
        if not self.tracking_started:
            bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
                self.frame_counter = 0
                if self.detector:
                    self.detector.extract_features(frame, bbox)
                    logging.debug("Detector's initial features set.")
                logging.info("Tracking activated.")
            else:
                logging.info("Invalid ROI or canceled.")
        else:
            self.cancel_activities()
            logging.info("Tracking deactivated.")

    def toggle_segmentation(self) -> bool:
        """
        Toggles segmentation on/off.
        """
        self.segmentation_active = not self.segmentation_active
        logging.info(f"Segmentation {'activated' if self.segmentation_active else 'deactivated'}.")
        return self.segmentation_active

    async def start_tracking(self, bbox: Dict[str, int]):
        """
        Start tracking from an external bounding box (API call).
        """
        if not self.tracking_started:
            bbox_tuple = (bbox['x'], bbox['y'], bbox['width'], bbox['height'])
            self.tracker.start_tracking(self.current_frame, bbox_tuple)
            self.tracking_started = True
            if hasattr(self.tracker, 'detector') and self.tracker.detector:
                self.tracker.detector.extract_features(self.current_frame, bbox_tuple)
            logging.info("Tracking activated via API.")
        else:
            logging.info("Tracking already active.")

    async def stop_tracking(self):
        """
        Stop tracking (API call).
        """
        if self.tracking_started:
            self.cancel_activities()
            logging.info("Tracking deactivated via API.")
        else:
            logging.info("Tracking is not active.")

    def cancel_activities(self):
        """
        Cancel both tracking and segmentation.
        """
        self.tracking_started = False
        self.segmentation_active = False
        if self.setpoint_sender:
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None
        logging.info("All activities cancelled.")

    async def update_loop(self, frame: np.ndarray) -> np.ndarray:
        """
        Main loop, called once per frame from your capture/reading logic.
        Applies preprocessing, segmentation, tracking, OSD drawing, GStreamer streaming, etc.
        """
        try:
            # Preprocessing
            if Parameters.ENABLE_PREPROCESSING and self.preprocessor:
                frame = self.preprocessor.preprocess(frame)

            # Segmentation
            if self.segmentation_active:
                frame = self.segmentor.segment_frame(frame)

            # Tracking
            if self.tracking_started:
                frame = await self._handle_tracking(frame)

            # Telemetry
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            # Update frames
            self.current_frame = frame
            self.video_handler.current_osd_frame = frame

            # Draw OSD
            frame = self.osd_handler.draw_osd(frame)

            # GStreamer QGC pipeline
            if self.gstreamer_handler:
                self.gstreamer_handler.stream_frame(frame)

            # GStreamer HTTP pipeline
            if self.gstreamer_http_handler:
                self.gstreamer_http_handler.push_frame(frame)

            # If WebRTC is enabled, push frames
            if self.webrtc_handler:
                self.webrtc_handler.push_frame(frame)

            # Single-point resizing
            self.video_handler.update_resized_frames(
                Parameters.STREAM_WIDTH, Parameters.STREAM_HEIGHT
            )

        except Exception as e:
            logging.exception(f"Error in update_loop: {e}")

        return frame

    async def _handle_tracking(self, frame: np.ndarray) -> np.ndarray:
        """
        Internal method for updating the tracker and handling tracking failures.
        """
        if self.tracking_failure_start_time is None:
            success, _ = self.tracker.update(frame)
        else:
            success = False

        if success:
            self.tracking_failure_start_time = None
            frame = self.tracker.draw_tracking(frame, tracking_successful=True)
            if Parameters.ENABLE_DEBUGGING:
                self.tracker.print_normalized_center()
            if self.tracker.position_estimator:
                frame = self.tracker.draw_estimate(frame, tracking_successful=True)
            if self.following_active:
                await self.follow_target()
                await self.check_failsafe()

            # Handle template updates
            self.frame_counter += 1
            if self._should_update_template():
                bbox = self.tracker.bbox
                if bbox:
                    self.detector.update_template(frame, bbox)
                    logging.debug("Template updated during tracking.")
        else:
            frame = await self._handle_tracking_failure(frame)

        return frame

    def _should_update_template(self) -> bool:
        """
        Decide if we should update the template (confidence + frame interval).
        """
        tracker_conf = self.tracker.get_confidence()
        if tracker_conf >= Parameters.TRACKER_CONFIDENCE_THRESHOLD_FOR_TEMPLATE_UPDATE:
            if self.frame_counter % Parameters.TEMPLATE_UPDATE_INTERVAL == 0:
                return True
        return False

    async def _handle_tracking_failure(self, frame: np.ndarray) -> np.ndarray:
        """
        Logic for dealing with partial or total tracking failure.
        """
        self.frame_counter = 0
        if self.tracking_failure_start_time is None:
            self.tracking_failure_start_time = time.time()
            logging.warning("Tracking lost. Starting failure timer.")
        else:
            elapsed = time.time() - self.tracking_failure_start_time
            if elapsed > Parameters.TRACKING_FAILURE_TIMEOUT:
                logging.error("Tracking lost too long. Stopping tracking.")
                self.tracking_started = False
                self.tracking_failure_start_time = None
            else:
                logging.warning(f"Tracking lost. Attempting recovery ({elapsed:.2f}s).")
                self.tracker.update_estimator_without_measurement()
                frame = self.tracker.draw_estimate(frame, tracking_successful=False)
                if self.following_active:
                    await self.follow_target()
                    await self.check_failsafe()

                redetect_result = self.handle_tracking_failure()
                if redetect_result and redetect_result.get("success"):
                    self.tracking_failure_start_time = None
        return frame

    def handle_tracking_failure(self):
        """
        Try re-detecting if auto-redetect is enabled.
        """
        if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
            logging.info("Attempting to re-detect target with the detector.")
            result = self.initiate_redetection()
            if result["success"]:
                logging.info("Target re-detected.")
            else:
                logging.info("Re-detection failed, will keep trying.")
            return result
        return {"success": False, "message": "Detector not enabled or auto-redetect off."}

    async def check_failsafe(self):
        if self.px4_interface.failsafe_active:
            await self.handle_failsafe()
            self.px4_interface.failsafe_active = False

    async def handle_failsafe(self):
        # For now, simply disconnect PX4
        await self.disconnect_px4()

    async def handle_key_input_async(self, key: int, frame: np.ndarray):
        """
        Keyboard shortcuts for toggling features.
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        elif key == ord('d'):
            self.initiate_redetection()
        elif key == ord('f'):
            await self.connect_px4()
        elif key == ord('x'):
            await self.disconnect_px4()
        elif key == ord('c'):
            self.cancel_activities()

    def handle_key_input(self, key: int, frame: np.ndarray):
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x: int, y: int):
        """
        If segmentation is active, identify object in segmented area and start tracking.
        """
        if not self.segmentation_active:
            return
        detections = self.segmentor.get_last_detections()
        selected_bbox = self.identify_clicked_object(detections, x, y)
        if selected_bbox:
            selected_bbox = tuple(map(lambda a: int(round(a)), selected_bbox))
            self.tracker.reinitialize_tracker(self.current_frame, selected_bbox)
            self.tracking_started = True
            logging.info(f"User selected object: {selected_bbox}")

    def identify_clicked_object(self, detections: list, x: int, y: int) -> Tuple[int, int, int, int]:
        for det in detections:
            x1, y1, x2, y2 = det
            if x1 <= x <= x2 and y1 <= y <= y2:
                return det
        return None

    def initiate_redetection(self) -> Dict[str, any]:
        """
        Attempt re-detection using the existing detector, focusing around estimated position if available.
        """
        if Parameters.USE_DETECTOR:
            estimate = self.tracker.get_estimated_position()
            if estimate:
                ex, ey = estimate[:2]
                r = Parameters.REDETECTION_SEARCH_RADIUS
                x_min = max(0, int(ex - r))
                x_max = min(self.video_handler.width, int(ex + r))
                y_min = max(0, int(ey - r))
                y_max = min(self.video_handler.height, int(ey + r))
                search_region = (x_min, y_min, x_max - x_min, y_max - y_min)
                result = self.detector.smart_redetection(self.current_frame, self.tracker, roi=search_region)
            else:
                result = self.detector.smart_redetection(self.current_frame, self.tracker)

            if result:
                bbox = self.detector.get_latest_bbox()
                self.tracker.reinitialize_tracker(self.current_frame, bbox)
                self.tracking_started = True
                logging.info("Re-detection success.")
                return {"success": True, "message": "Re-detected.", "bounding_box": bbox}
            else:
                logging.info("Re-detection failed, no object found.")
                return {"success": False, "message": "No new object found."}
        return {"success": False, "message": "Detector disabled."}

    def show_current_frame(self, frame_title: str = Parameters.FRAME_TITLE) -> np.ndarray:
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def connect_px4(self) -> Dict[str, any]:
        """
        Connect to PX4 for following if not already connected.
        """
        result = {"steps": [], "errors": []}
        if not self.following_active:
            try:
                logging.debug("Activating Follow Mode (PX4).")
                await self.px4_interface.connect()
                logging.debug("PX4 connected.")
                initial_target_coords = (
                    tuple(self.tracker.normalized_center)
                    if Parameters.TARGET_POSITION_MODE == 'initial'
                    else tuple(Parameters.DESIRE_AIM)
                )
                self.follower = Follower(self.px4_interface, initial_target_coords)
                self.telemetry_handler.follower = self.follower
                await self.px4_interface.set_hover_throttle()
                await self.px4_interface.send_initial_setpoint()
                await self.px4_interface.start_offboard_mode()
                self.following_active = True
                result["steps"].append("Offboard mode started.")
            except Exception as e:
                logging.error(f"Failed to connect PX4: {e}")
                result["errors"].append(str(e))
        else:
            result["steps"].append("Already following.")
        return result

    async def disconnect_px4(self) -> Dict[str, any]:
        """
        Stop offboard mode + disconnect PX4 if following is active.
        """
        result = {"steps": [], "errors": []}
        if self.following_active:
            try:
                await self.px4_interface.stop_offboard_mode()
                result["steps"].append("Offboard mode stopped.")
                self.following_active = False
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                    self.setpoint_sender = None
            except Exception as e:
                logging.error(f"Failed to stop offboard mode: {e}")
                result["errors"].append(str(e))
        else:
            result["steps"].append("Follow mode not active.")
        return result

    async def follow_target(self):
        """
        Called during tracking to update PX4 setpoints.
        """
        if self.tracking_started and self.following_active:
            target_coords: Optional[Tuple[float, float]] = None
            if Parameters.USE_ESTIMATOR_FOR_FOLLOWING and self.tracker.position_estimator:
                w, h = self.video_handler.width, self.video_handler.height
                est = self.tracker.position_estimator.get_normalized_estimate(w, h)
                if est:
                    target_coords = est
                else:
                    logging.warning("Estimator no normalized coords, falling back.")
            if not target_coords:
                target_coords = self.tracker.normalized_center
            if target_coords:
                self.follower.follow_target(target_coords)
                self.px4_interface.update_setpoint()
                ctrl_type = self.follower.get_control_type()
                if ctrl_type == 'attitude_rate':
                    await self.px4_interface.send_attitude_rate_commands()
                elif ctrl_type == 'velocity_body':
                    await self.px4_interface.send_body_velocity_commands()
                else:
                    logging.warning(f"Unknown control type: {ctrl_type}")
            else:
                logging.warning("No target coords to follow.")
            return True
        return False

    async def shutdown(self) -> Dict[str, any]:
        """
        Gracefully stop all processes: MAVLink, PX4, streaming, etc.
        """
        result = {"steps": [], "errors": []}
        try:
            if Parameters.MAVLINK_ENABLED:
                self.mavlink_data_manager.stop_polling()

            if self.following_active:
                await self.px4_interface.stop_offboard_mode()
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                self.following_active = False

            # Release QGC pipeline
            if self.gstreamer_handler:
                self.gstreamer_handler.release()
            # Release HTTP pipeline
            if self.gstreamer_http_handler:
                self.gstreamer_http_handler.stop()

            if self.webrtc_handler:
                self.webrtc_handler.stop()


            self.video_handler.release()
            result["steps"].append("Shutdown complete.")
            logging.debug("Shutdown finished successfully.")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            result["errors"].append(str(e))
        return result
