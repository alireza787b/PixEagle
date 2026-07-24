# src/classes/app_controller.py

import asyncio
import dataclasses
import logging
import time
import numpy as np
import cv2
import threading
from pathlib import Path

from classes.parameters import Parameters
from classes.logging_manager import logging_manager
from classes.runtime_logging import redact_text
from classes.follower import Follower
from classes.command_intent import CommandIntent
from classes.command_preview import (
    COMMAND_PREVIEW_EXECUTION_MODE,
    CommandPreviewCommander,
    CommandPreviewController,
    PX4_EXECUTION_MODE,
)
from classes.offboard_commander import OffboardCommander
from classes.video_handler import VideoHandler
from classes.trackers.csrt_tracker import CSRTTracker  # Import other trackers as necessary
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.px4_interface_manager import PX4InterfaceManager  # Updated import path
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler  # Correct import
from typing import Dict, Optional, Tuple, Any
from classes.osd_handler import OSDHandler
from classes.osd_pipeline import OSDPipeline
from classes.osd_mode_manager import OSDModeManager
from classes.gstreamer_handler import GStreamerHandler
from classes.recording_manager import RecordingManager
from classes.storage_manager import StorageManager
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_publisher import FramePublisher
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator
from classes.detectors.detector_factory import create_detector
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.tracker_trace import TrackerTraceRecorder
from classes.tracking_roi import (
    TrackingROIError,
    tracking_roi_to_pixels,
    tracking_xyxy_to_pixels,
)
from classes.circuit_breaker import FollowerCircuitBreaker
from classes.following_readiness import (
    evaluate_command_preview_start_readiness,
    evaluate_following_start_readiness,
    get_configured_follower_execution_mode,
)
from classes.tracker_runtime_status import evaluate_tracker_command_freshness

# Import the SmartTracker module (conditional - may not be available without AI packages)
try:
    from classes.smart_tracker import SmartTracker
    try:
        from classes.backends.ultralytics_backend import ULTRALYTICS_AVAILABLE
    except ImportError:
        ULTRALYTICS_AVAILABLE = False
    SMART_TRACKER_AVAILABLE = ULTRALYTICS_AVAILABLE
except ImportError:
    SmartTracker = None
    SMART_TRACKER_AVAILABLE = False
    logging.warning("SmartTracker not available - AI packages not installed")


class AppController:
    FOLLOW_START_CANCEL_TIMEOUT_S = 2.0

    def __init__(self):
        """
        Initializes the AppController with necessary components and starts the FastAPI handler.
        Also sets up flags for both classic and smart tracking modes.
        """
        logging.debug("Initializing AppController...")
        self._startup_component_lock = threading.Lock()
        self._startup_components: Dict[str, Dict[str, Any]] = {}
        self._flight_event_loop = None
        self._flight_event_loop_bind_lock = threading.Lock()
        # Compatibility alias retained for bounded callback tests and older
        # integrations. It always points at the stable flight owner loop.
        self._app_event_loop = None
        self._follow_start_task = None
        self._shutdown_task = None
        # A supervised backend restart must survive every shutdown path,
        # including the main-loop watchdog and a graceful main() return.
        self.requested_process_exit_code = None
        self.following_active = False
        # The active mode is a runtime claim boundary. It is reset to PX4 after
        # every local preview session so a stale preview cannot authorize a
        # later vehicle start.
        self.following_execution_mode = PX4_EXECUTION_MODE
        # Serializes target selection with detector-model replacement across
        # the API event loop and the optional OpenCV UI callback thread.
        self._tracker_model_state_lock = threading.RLock()
        # Invalidates in-flight recovery work whenever the operator selects or
        # clears a target. Recovery from an older target must never mutate a
        # newer target session after an await boundary.
        self._tracking_session_generation = 0
        # Orders rapid operator clicks before they enter the flight-owner
        # coroutine.  This is separate from the applied tracking-session
        # generation: a request can be superseded before it mutates state.
        self._smart_selection_generation = 0
        self._smart_selection_generation_lock = threading.Lock()

        # Initialize MAVLink Data Manager
        self.mavlink_data_manager = MavlinkDataManager(
            mavlink_host=Parameters.MAVLINK_HOST,
            mavlink_port=Parameters.MAVLINK_PORT,
            polling_interval=Parameters.MAVLINK_POLLING_INTERVAL,
            data_points=Parameters.MAVLINK_DATA_POINTS,
            enabled=Parameters.MAVLINK_ENABLED
        )
        
        # Initialize frame preprocessor if enabled
        if Parameters.ENABLE_PREPROCESSING:
            self.preprocessor = FramePreprocessor()
        else:
            self.preprocessor = None
        
        # External workers start only after every synchronous controller
        # component, including the API handler, has been constructed.
        if Parameters.MAVLINK_ENABLED:
            self._set_startup_component(
                "mavlink_telemetry",
                "initializing",
                "deferred_until_controller_ready",
            )
        else:
            self._set_startup_component(
                "mavlink_telemetry",
                "disabled",
                "disabled_by_configuration",
            )

        # Initialize the estimator
        try:
            self.estimator = create_estimator(Parameters.ESTIMATOR_TYPE)
            self._set_startup_component(
                "estimator",
                "ready" if self.estimator is not None else "disabled",
                str(Parameters.ESTIMATOR_TYPE),
            )
        except Exception as exc:
            self.estimator = None
            self._set_startup_component(
                "estimator",
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logging.exception(
                "Estimator startup failed; tracking will remain fail-closed until corrected"
            )

        # Initialize video processing components
        self.video_handler = VideoHandler(initialize_source=False)
        self._set_startup_component(
            "video_input",
            "initializing",
            "deferred_until_api_ready",
        )
        self.video_streamer = None
        try:
            self.detector = create_detector(Parameters.DETECTION_ALGORITHM)
            self._set_startup_component(
                "detector",
                "ready" if self.detector is not None else "disabled",
                str(Parameters.DETECTION_ALGORITHM),
            )
        except Exception as exc:
            self.detector = None
            self._set_startup_component(
                "detector",
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logging.exception(
                "Detector startup failed; dashboard and tracker configuration remain available"
            )

        try:
            self.tracker = create_tracker(
                Parameters.DEFAULT_TRACKING_ALGORITHM,
                self.video_handler,
                self.detector,
                self,
            )
            self._start_external_tracker_monitoring(
                self.tracker,
                context="application startup",
            )
            self._set_startup_component(
                "tracker",
                "ready",
                self.tracker.__class__.__name__,
            )
        except Exception as exc:
            self.tracker = None
            self._set_startup_component(
                "tracker",
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logging.exception(
                "Configured tracker startup failed; tracking is unavailable, but "
                "dashboard settings and tracker-switch recovery remain available"
            )

        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)
                    
        # Monotonic, bounded classic-tracker loss recovery state. The original
        # implementation reset this deadline for any non-empty result dict,
        # including {"success": False}, which could retry re-detection forever.
        self.tracking_failure_start_time = None
        self._tracking_recovery_attempts = 0
        self._tracking_next_recovery_attempt_at = None

        # Initialize frame counter and tracking flags
        self.frame_counter = 0
        self.tracking_started = False
        self.segmentation_active = False
        
        # System status tracking for periodic updates
        self.last_system_status_time = 0
        self.system_status_interval = 15  # Report system status every 15 seconds
        
        # Flags and attributes for Smart Mode (AI-based)
        self.smart_mode_active = False
        self.last_smart_mode_error: Optional[str] = None
        self.smart_tracker: Optional[SmartTracker] = None
        self.selected_bbox: Optional[Tuple[int, int, int, int]] = None
        
        # Current tracker type configuration for UI selection
        self.current_tracker_type = Parameters.DEFAULT_TRACKING_ALGORITHM

        # Setup video window and mouse callback if enabled
        self.local_video_window_available = False
        if Parameters.SHOW_VIDEO_WINDOW:
            try:
                cv2.namedWindow("Video")
                cv2.setMouseCallback("Video", self.on_mouse_click)
                self.local_video_window_available = True
                self._set_startup_component(
                    "local_video_window",
                    "ready",
                    "opencv_window_ready",
                )
            except Exception as exc:
                self._set_startup_component(
                    "local_video_window",
                    "degraded",
                    f"{type(exc).__name__}: {exc}",
                )
                logging.exception(
                    "Local OpenCV window startup failed; browser operation remains available"
                )
        else:
            self._set_startup_component(
                "local_video_window",
                "disabled",
                "disabled_by_configuration",
            )
        self.current_frame = None
        self.tracking_input_frame = None
        self.segmentation_selection_frame = None
        self.segmentation_selection_detections = ()

        # Initialize PX4 interface and following mode components
        try:
            self.px4_interface = PX4InterfaceManager(
                app_controller=self,
                on_connection_lost=self._handle_px4_connection_loss,
            )
            self._set_startup_component(
                "px4_interface",
                "ready",
                "initialized_disconnected",
            )
        except Exception as exc:
            self.px4_interface = None
            self._set_startup_component(
                "px4_interface",
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logging.exception(
                "PX4 interface startup failed; all flight commands remain unavailable"
            )
        self._active_following_controller = self.px4_interface
        self.follower = None
        self.setpoint_sender = None
        self.offboard_commander = None
        self.last_offboard_commander_failure = None
        self.tracker_trace_recorder = None
        self._tracker_trace_frame_index = 0
        self._offboard_trace_sequence = 0

        # Thread safety lock for follower state management
        # Prevents race conditions when multiple API calls modify follower state
        self._follower_state_lock = asyncio.Lock()

        # Initialize telemetry handler with tracker and follower
        self.telemetry_handler = TelemetryHandler(self, lambda: self.tracking_started)

        # Thread-safe frame publisher for streaming consumers
        self.frame_publisher = FramePublisher()

        # Pipeline performance metrics (updated by FlowController, read by API)
        self._pipeline_metrics = {
            'preprocess_ms': 0.0,
            'tracking_ms': 0.0,
            'osd_ms': 0.0,
            'publish_ms': 0.0,
            'total_processing_ms': 0.0,
            'frame_pacing_ms': 0.0,
            'loop_total_ms': 0.0,
            'fps_actual': 0.0,
            'fps_target': 0.0,
            'budget_utilization': 0.0,
            'pipeline_mode': str(getattr(Parameters, 'PIPELINE_MODE', 'REALTIME')),
            'capture_mode': '',
            'frame_id': 0,
            'overrun_count': 0,
            'total_frames': 0,
        }

        # Initialize the FastAPI handler
        logging.debug("Initializing FastAPIHandler...")
        self.api_handler = FastAPIHandler(self)
        logging.debug("FastAPIHandler initialized.")

        # Initialize OSD handler for overlay graphics
        self.osd_handler = OSDHandler(self)
        self.osd_pipeline = OSDPipeline(self.osd_handler)
        self.gstreamer_osd_pipeline = OSDPipeline(self.osd_handler)
        self.osd_mode_manager = OSDModeManager(self)
        
        # Initialize GStreamer streaming if enabled
        self.gstreamer_handler = None
        if Parameters.ENABLE_GSTREAMER_STREAM:
            try:
                candidate_gstreamer_handler = GStreamerHandler()
                if candidate_gstreamer_handler.initialize_stream():
                    self.gstreamer_handler = candidate_gstreamer_handler
                    self._set_startup_component(
                        "gstreamer_output",
                        "ready",
                        "writer_started",
                    )
                else:
                    self._set_startup_component(
                        "gstreamer_output",
                        "degraded",
                        str(
                            candidate_gstreamer_handler.encoder_status.get(
                                "last_error"
                            )
                            or "pipeline_unavailable"
                        ),
                    )
            except Exception as exc:
                self._set_startup_component(
                    "gstreamer_output",
                    "degraded",
                    f"{type(exc).__name__}: {exc}",
                )
                logging.exception(
                    "Optional GStreamer output startup failed; browser media remains available"
                )
        else:
            self._set_startup_component(
                "gstreamer_output",
                "disabled",
                "disabled_by_configuration",
            )

        # Initialize recording system if enabled
        self.recording_manager = None
        self.storage_manager = None
        if getattr(Parameters, 'ENABLE_RECORDING', False):
            try:
                self.recording_manager = RecordingManager()
                self.storage_manager = StorageManager(self.recording_manager)
                self.storage_manager.start_monitoring()
                self._set_startup_component(
                    "recording",
                    "ready",
                    "storage_monitor_started",
                )
                logging.info("Recording system initialized")
            except Exception as exc:
                self.recording_manager = None
                self.storage_manager = None
                self._set_startup_component(
                    "recording",
                    "degraded",
                    f"{type(exc).__name__}: {exc}",
                )
                logging.exception(
                    "Recording startup failed; live operation and settings remain available"
                )
        else:
            self._set_startup_component(
                "recording",
                "disabled",
                "disabled_by_configuration",
            )

        self._start_degradable_background_workers()
        logging.info("AppController initialized.")

    def _set_startup_component(self, name: str, status: str, detail: str) -> None:
        """Record sanitized process-local capability startup state."""
        with self._startup_component_lock:
            self._startup_components[str(name)] = {
                "status": str(status),
                "detail": redact_text(detail)[:500],
                "updated_at": time.time(),
            }

    def get_startup_status(self) -> Dict[str, Any]:
        """Return startup capability state without exposing secrets or paths."""
        video_handler = getattr(self, "video_handler", None)
        if video_handler is not None:
            try:
                health = video_handler.get_connection_health()
                capture_mode = str(health.get("capture_mode") or "")
                with self._startup_component_lock:
                    current_video_state = self._startup_components.get(
                        "video_input",
                        {},
                    ).get("status")
                if capture_mode != "uninitialized" or current_video_state != "initializing":
                    health_status = str(health.get("status") or "unavailable")
                    self._set_startup_component(
                        "video_input",
                        (
                            "ready"
                            if health_status == "healthy"
                            else "initializing"
                            if health_status in {"initializing", "recovering"}
                            else "degraded"
                        ),
                        str(
                            health.get("last_capture_error")
                            or health.get("capture_mode")
                            or health_status
                        ),
                    )
            except Exception as exc:
                self._set_startup_component(
                    "video_input",
                    "degraded",
                    f"health_snapshot_failed:{type(exc).__name__}",
                )

        with self._startup_component_lock:
            components = {
                name: dict(state)
                for name, state in self._startup_components.items()
            }
        degraded = sorted(
            name
            for name, state in components.items()
            if state.get("status") == "degraded"
        )
        initializing = sorted(
            name
            for name, state in components.items()
            if state.get("status") == "initializing"
        )
        return {
            "status": (
                "degraded"
                if degraded
                else "initializing"
                if initializing
                else "ready"
            ),
            "degraded_components": degraded,
            "initializing_components": initializing,
            "components": components,
        }

    def initialize_video_source(self) -> bool:
        """Activate media after the API control plane is accepting requests."""
        try:
            success = self.video_handler.initialize_source(max_retries=1)
            health = self.video_handler.get_connection_health()
        except Exception as exc:
            success = False
            health = {"last_capture_error": f"{type(exc).__name__}: {exc}"}
            logging.exception(
                "Unexpected video activation failure; control plane remains available"
            )
        self._set_startup_component(
            "video_input",
            "ready" if success else "degraded",
            str(
                health.get("capture_mode")
                if success
                else health.get("last_capture_error") or "source_unavailable"
            ),
        )
        return success

    def _start_degradable_background_workers(self) -> None:
        """Start optional workers after synchronous construction has completed."""
        if Parameters.MAVLINK_ENABLED:
            try:
                self.mavlink_data_manager.start_polling()
                self.mavlink_data_manager.register_offboard_exit_callback(
                    self._schedule_offboard_mode_exit
                )
                self._set_startup_component(
                    "mavlink_telemetry",
                    "ready",
                    "polling_started",
                )
            except Exception as exc:
                self._set_startup_component(
                    "mavlink_telemetry",
                    "degraded",
                    f"{type(exc).__name__}: {exc}",
                )
                logging.exception(
                    "MAVLink telemetry startup failed; dashboard and configuration "
                    "remain available"
                )

        try:
            self._start_system_summary_thread()
            self._set_startup_component(
                "system_summary",
                "ready",
                "background_worker_started",
            )
        except Exception as exc:
            self._set_startup_component(
                "system_summary",
                "degraded",
                f"{type(exc).__name__}: {exc}",
            )
            logging.exception(
                "System summary worker startup failed; runtime logs remain available"
            )

    def _start_external_tracker_monitoring(
        self,
        tracker: object,
        *,
        context: str,
    ) -> bool:
        """Start the provider lifecycle required by any external tracker."""
        if not getattr(tracker, "is_external_tracker", False):
            return False

        start_tracking = getattr(tracker, "start_tracking", None)
        tracker_name = tracker.__class__.__name__
        if not callable(start_tracking):
            raise RuntimeError(
                f"{tracker_name} cannot start external monitoring during {context}: "
                "start_tracking is unavailable"
            )

        try:
            start_tracking(None, (0, 0, 0, 0))
        except Exception as exc:
            raise RuntimeError(
                f"{tracker_name} external monitoring failed during {context}: {exc}"
            ) from exc

        monitoring_active = getattr(tracker, "monitoring_active", None)
        if monitoring_active is False:
            raise RuntimeError(
                f"{tracker_name} external monitoring did not become active during "
                f"{context}; review provider configuration and socket availability"
            )

        logging.info(
            "%s external monitoring active (%s)",
            tracker_name,
            context,
        )
        return True

    def on_mouse_click(self, event: int, x: int, y: int, flags: int, param: any):
        """
        Mouse callback for user interactions.
        In smart mode, selects the closest AI detection.
        Otherwise, handles segmentation click events.
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            logging.info("clicked")
            if getattr(self, "smart_mode_active", False):
                self.handle_smart_click(x, y)
            elif self.segmentation_active:
                self.handle_user_click(x, y)

    def handle_smart_click(self, x: int, y: int):
        """
        Handle a synchronous SmartTracker click from the optional OpenCV UI.

        HTTP callers must use :meth:`select_smart_target`, which acquires the
        async follower lifecycle barrier before mutating target state.
        """
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {
                "success": False,
                "reason": "follower_state_barrier_unavailable",
                "message": "Follower state barrier is unavailable.",
            }
        if follower_lock.locked():
            return {
                "success": False,
                "reason": "follower_lifecycle_busy",
                "message": "Follower lifecycle transition is in progress.",
            }
        if self.following_active:
            return {
                "success": False,
                "reason": "following_active",
                "message": "Stop follow mode before selecting a different target.",
            }
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            message = "Tracker/model state barrier is unavailable."
            logging.error(message)
            return {
                "success": False,
                "reason": "tracker_model_state_barrier_unavailable",
                "message": message,
            }
        with state_lock:
            self._next_smart_selection_generation()
            return self._handle_smart_click_locked(x, y)

    async def select_smart_target(self, x: int, y: int) -> Dict[str, Any]:
        """Select or replace the SmartTracker target on the flight owner loop."""
        selection_generation = self._next_smart_selection_generation()
        return await self._run_on_flight_event_loop(
            lambda: self._select_smart_target_on_flight_loop(
                x,
                y,
                selection_generation=selection_generation,
            )
        )

    async def _select_smart_target_on_flight_loop(
        self,
        x: int,
        y: int,
        *,
        selection_generation: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Apply one SmartTracker selection while follower lifecycle is excluded."""
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {
                "success": False,
                "reason": "follower_state_barrier_unavailable",
                "message": "Follower state barrier is unavailable.",
            }

        async with follower_lock:
            if (
                selection_generation is not None
                and not self._smart_selection_generation_is_current(selection_generation)
            ):
                return {
                    "success": False,
                    "reason": "selection_superseded",
                    "message": "A newer target selection is being applied.",
                    "selection_generation": selection_generation,
                }
            if not self.smart_mode_active:
                return {
                    "success": False,
                    "reason": "smart_mode_inactive",
                    "message": "Smart mode changed before target selection.",
                }

            state_lock = getattr(self, "_tracker_model_state_lock", None)
            if state_lock is None:
                return {
                    "success": False,
                    "reason": "tracker_model_state_barrier_unavailable",
                    "message": "Tracker/model state barrier is unavailable.",
                }
            with state_lock:
                if (
                    selection_generation is not None
                    and not self._smart_selection_generation_is_current(selection_generation)
                ):
                    return {
                        "success": False,
                        "reason": "selection_superseded",
                        "message": "A newer target selection is being applied.",
                        "selection_generation": selection_generation,
                    }
                transition = self._prepare_following_target_transition(
                    "operator_smart_target_retarget"
                )
                if not transition["prepared"]:
                    return {
                        "success": False,
                        "reason": transition["reason"],
                        "message": (
                            "The current command could not be placed in a safe hold; "
                            "target selection was refused."
                        ),
                        "target_transition": transition,
                    }
                result = self._handle_smart_click_locked(x, y)
                if transition["command_hold_applied"]:
                    result["target_transition"] = transition
                return result

    def _handle_smart_click_locked(self, x: int, y: int):
        """Apply one SmartTracker selection while model replacement is excluded."""
        if self.current_frame is None or self.smart_tracker is None:
            message = "SmartTracker unavailable or frame not ready."
            logging.warning(message)
            return {
                "success": False,
                "reason": "smart_tracker_unavailable",
                "message": message,
            }

        selection_status_getter = getattr(
            self.smart_tracker,
            "get_selection_snapshot_status",
            None,
        )
        if callable(selection_status_getter):
            selection_status = selection_status_getter()
        else:
            selection_status = {
                "available": bool(self.smart_tracker.last_detections),
                "source": "current" if self.smart_tracker.last_detections else "none",
            }
        if not selection_status.get("available", False):
            message = "SmartTracker has no recent detection available for selection."
            logging.warning(message)
            return {
                "success": False,
                "reason": "no_detections",
                "message": message,
                "selection_snapshot": selection_status,
            }
        selected = self.smart_tracker.select_object_by_click(x, y)

        if selected and self.smart_tracker.selected_bbox and self.smart_tracker.selected_center:
            self.selected_bbox = tuple(map(int, self.smart_tracker.selected_bbox))
            self.tracker.set_external_override(
                self.smart_tracker.selected_bbox,
                self.smart_tracker.selected_center
            )
            self._advance_tracking_session_generation()
            logging.info(f"Smart tracking override activated with bbox: {self.selected_bbox}")
            result = {
                "success": True,
                "reason": "override_applied",
                "message": "Smart tracking override activated.",
                "selected_bbox": list(self.selected_bbox),
                "selected_center": list(map(int, self.smart_tracker.selected_center)),
            }
            selection_info_getter = getattr(
                self.smart_tracker,
                "get_last_selection_info",
                None,
            )
            if callable(selection_info_getter):
                result["selection"] = selection_info_getter()
            return result
        else:
            message = "No AI detection selected. Override not applied."
            logging.info(message)
            return {
                "success": False,
                "reason": "no_detection_selected",
                "message": message,
            }

    def _track_and_draw_smart_frame(self, frame: np.ndarray) -> np.ndarray:
        """Run one SmartTracker frame while model and target state are stable."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")
        with state_lock:
            smart_tracker = self.smart_tracker
            if smart_tracker is None:
                return frame
            return smart_tracker.track_and_draw(frame)


    def toggle_tracking(self, frame: np.ndarray):
        """
        Toggles classic tracking (CSRT-based) state.
        If starting tracking, uses a user-drawn ROI.
        """
        if not self.tracking_started:
            bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
                self._advance_tracking_session_generation()
                self._reset_tracking_failure_state()
                self.frame_counter = 0  # Reset frame counter
                if self.detector:
                    # Initialize detector features and template
                    self.detector.extract_features(frame, bbox)
                    logging.debug("Detector's features and template set.")
                logging.info("Classic tracking activated.")
            else:
                logging.info("Tracking canceled or invalid ROI.")
        else:
            self.cancel_activities()
            logging.info("Classic tracking deactivated.")


    def toggle_smart_mode(self):
        """
        Toggles the AI-based smart tracking mode.
        If enabling for the first time, initializes SmartTracker (with GPU/CPU config + fallback).
        """
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            self.last_smart_mode_error = (
                "Smart mode is unavailable because its state barrier is not ready."
            )
            logging.error(
                "Smart mode change refused: tracker/model state barrier unavailable"
            )
            return False
        with state_lock:
            return self._toggle_smart_mode_locked()

    def _toggle_smart_mode_locked(self):
        """Change SmartTracker lifecycle while model replacement is excluded."""
        if not self.smart_mode_active:
            # Check if SmartTracker is available (requires ultralytics/torch)
            if not SMART_TRACKER_AVAILABLE:
                self.last_smart_mode_error = (
                    "SmartTracker dependencies are not installed. Run the Full AI setup "
                    "profile, then retry."
                )
                logging.error(
                    "SmartTracker not available - AI packages (ultralytics/torch) not installed. "
                    "Re-run 'make init' and select 'Full' profile, or install manually: "
                    "bash scripts/setup/setup-pytorch.sh --mode auto && "
                    "bash scripts/setup/install-ai-deps.sh"
                )
                return False

            self.cancel_activities()
            self.smart_mode_active = True

            if self.smart_tracker is None:
                try:
                    self.smart_tracker = SmartTracker(app_controller=self)
                    self.last_smart_mode_error = None
                    logging.info("SMART TRACKER MODE: Activated (AI-based multi-target tracking)")
                except Exception as e:
                    logging.error(f"Failed to activate SmartTracker: {e}")
                    self.last_smart_mode_error = (
                        "The selected detection model could not be loaded. "
                        "Select a trusted compatible model in Models and retry."
                    )
                    self.smart_mode_active = False
                    return False
            else:
                self.last_smart_mode_error = None
                logging.info("SMART TRACKER MODE: Re-activated")
            return True

        else:
            self.smart_mode_active = False
            self.last_smart_mode_error = None
            if self.smart_tracker:
                self.smart_tracker.clear_selection()
                self.smart_tracker = None
            logging.info("SmartTracker mode deactivated.")
            return True



    def toggle_segmentation(self) -> bool:
        """
        Toggles the segmentation state.
        """
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            logging.error("Segmentation change refused: tracker state barrier unavailable")
            return False
        with state_lock:
            if not self.segmentation_active:
                capability = self.segmentor.get_capability_status()
                if not capability["available"]:
                    logging.warning(
                        "Segmentation activation refused: %s",
                        capability["unavailable_reason"],
                    )
                    return False
            self.segmentation_active = not self.segmentation_active
            if not self.segmentation_active:
                self.segmentation_selection_frame = None
                self.segmentation_selection_detections = ()
            logging.info(
                "Segmentation %s.",
                "activated" if self.segmentation_active else "deactivated",
            )
            return self.segmentation_active

    def _segment_frame_for_selection(
        self,
        analysis_frame: np.ndarray,
        tracking_frame_snapshot: np.ndarray,
    ) -> np.ndarray:
        """Run segmentation and publish its paired selection snapshot atomically."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")
        with state_lock:
            if not self.segmentation_active or self.smart_tracker is not None:
                self.segmentation_selection_frame = None
                self.segmentation_selection_detections = ()
                return analysis_frame.copy()
            display_frame = self.segmentor.segment_frame(analysis_frame)
            self.segmentation_selection_frame = tracking_frame_snapshot
            self.segmentation_selection_detections = tuple(
                tuple(box) for box in self.segmentor.get_last_detections()
            )
            return display_frame

    def _publish_tracking_input_frame(self, frame: np.ndarray) -> np.ndarray:
        """Publish one clean pre-overlay frame for operator target selection."""
        snapshot = frame.copy()
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")
        with state_lock:
            self.tracking_input_frame = snapshot
        return snapshot

    def _publish_segmentation_selection_snapshot(
        self,
        frame_snapshot: np.ndarray,
        detections: list,
    ) -> None:
        """Atomically pair ``xyxy`` detections with their clean analysis frame."""
        normalized_detections = tuple(tuple(box) for box in detections)
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")
        with state_lock:
            self.segmentation_selection_frame = frame_snapshot
            self.segmentation_selection_detections = normalized_detections

    def _clear_segmentation_selection_snapshot(self) -> None:
        """Clear segmentation selection state so stale boxes cannot be clicked."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            self.segmentation_selection_frame = None
            self.segmentation_selection_detections = ()
            return
        with state_lock:
            self.segmentation_selection_frame = None
            self.segmentation_selection_detections = ()

    def get_segmentation_selection_snapshot(
        self,
    ) -> Tuple[Optional[np.ndarray], list]:
        """Return one coherent clean frame and its segmentation ``xyxy`` boxes."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            return None, []
        with state_lock:
            frame = getattr(self, "segmentation_selection_frame", None)
            detections = getattr(self, "segmentation_selection_detections", ())
            return (
                frame.copy() if frame is not None else None,
                [tuple(box) for box in detections],
            )

    def get_tracking_input_frame_snapshot(self) -> Optional[np.ndarray]:
        """Return a coherent clean frame copy for tracker initialization."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            return None
        with state_lock:
            source = getattr(self, "tracking_input_frame", None)
            if source is None:
                source = getattr(self, "current_frame", None)
            return source.copy() if source is not None else None

    def _update_classic_tracker(self, frame: np.ndarray):
        """Serialize classic tracker mutation with API selection/reinitialization."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")
        with state_lock:
            return self.tracker.update(frame)

    async def start_tracking(
        self,
        bbox: Dict[str, int],
        frame: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Starts tracking with the provided bounding box.

        Note: For external trackers, manual tracking initiation is not supported.
        External trackers use external control and monitor automatically.
        """
        return await self._run_on_flight_event_loop(
            lambda: self._start_tracking_on_flight_loop(bbox, frame=frame)
        )

    async def _start_tracking_on_flight_loop(
        self,
        bbox: Dict[str, int],
        *,
        frame: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Start tracking while the flight lifecycle barrier is loop-owned."""
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {"started": False, "reason": "follower_state_barrier_unavailable"}
        async with follower_lock:
            if getattr(self, "smart_mode_active", False):
                return {"started": False, "reason": "smart_mode_active"}
            return self._start_tracking_with_follower_barrier(bbox, frame=frame)

    def _prepare_following_target_transition(self, reason: str) -> Dict[str, Any]:
        """Invalidate the active command before tracker target state is mutated."""
        execution_mode = getattr(
            self,
            "following_execution_mode",
            PX4_EXECUTION_MODE,
        )
        if not getattr(self, "following_active", False):
            return {
                "prepared": True,
                "command_hold_applied": False,
                "following_continued": False,
                "execution_mode": execution_mode,
            }

        follower = getattr(self, "follower", None)
        prepare_follower = getattr(follower, "prepare_for_target_transition", None)
        commander = getattr(self, "offboard_commander", None)
        activate_defaults = getattr(commander, "activate_failsafe_defaults", None)
        if not callable(prepare_follower) or not callable(activate_defaults):
            logging.error(
                "Target transition refused while following: follower or commander "
                "transition contract is unavailable"
            )
            return {
                "prepared": False,
                "reason": "target_transition_hold_unavailable",
                "command_hold_applied": False,
                "following_continued": True,
                "execution_mode": execution_mode,
            }

        try:
            if not prepare_follower(reason):
                raise RuntimeError("follower rejected target-transition preparation")
            activate_defaults(reason)
            commander_status_getter = getattr(commander, "get_status", None)
            commander_status = (
                commander_status_getter()
                if callable(commander_status_getter)
                else None
            )
            if (
                isinstance(commander_status, dict)
                and commander_status.get("failsafe_defaults_active") is False
            ):
                raise RuntimeError("commander did not confirm fail-closed defaults")
        except Exception as exc:
            logging.error("Target transition hold failed for %s: %s", reason, exc)
            return {
                "prepared": False,
                "reason": "target_transition_hold_failed",
                "error": str(exc),
                "command_hold_applied": False,
                "following_continued": True,
                "execution_mode": execution_mode,
            }

        logging.warning(
            "Following remains active with fail-closed command defaults during %s",
            reason,
        )
        return {
            "prepared": True,
            "command_hold_applied": True,
            "following_continued": True,
            "execution_mode": execution_mode,
        }

    def _start_tracking_with_follower_barrier(
        self,
        bbox: Dict[str, int],
        *,
        frame: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Initialize one classic target while follower lifecycle is excluded."""
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None or not follower_lock.locked():
            raise RuntimeError("Follower state barrier must be held for target selection")
        # Check if we're using an external tracker
        if getattr(self.tracker, 'is_external_tracker', False):
            tracker_name = self.tracker.__class__.__name__
            logging.warning(f"Manual tracking control not supported for {tracker_name}")
            logging.info(f"{tracker_name} requires external control from camera UI application")
            logging.info("Tracker is monitoring automatically - no manual start needed")
            return {"started": False, "reason": "external_tracker"}

        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            raise RuntimeError("Tracker/model state barrier is unavailable")

        with state_lock:
            tracking_frame = frame
            if tracking_frame is None:
                tracking_frame = getattr(self, "tracking_input_frame", None)
            if tracking_frame is None:
                tracking_frame = self.current_frame
            if tracking_frame is None:
                return {"started": False, "reason": "frame_unavailable"}

            bbox_tuple = (bbox['x'], bbox['y'], bbox['width'], bbox['height'])
            transition = self._prepare_following_target_transition(
                "operator_target_retarget"
            )
            if not transition["prepared"]:
                return {
                    "started": False,
                    "reason": transition["reason"],
                    "target_transition": transition,
                }
            retargeted = bool(self.tracking_started)
            self._advance_tracking_session_generation()
            self.tracking_started = False
            self._reset_tracking_failure_state()
            try:
                reset_tracker = getattr(self.tracker, "reset", None)
                if not callable(reset_tracker):
                    raise RuntimeError(
                        "Classic tracker does not provide the required reset contract"
                    )
                reset_tracker()
                self.tracker.start_tracking(tracking_frame, bbox_tuple)
            except Exception:
                self.tracking_started = False
                stop_tracking = getattr(self.tracker, "stop_tracking", None)
                if callable(stop_tracking):
                    stop_tracking()
                self._reset_tracking_failure_state()
                raise

            self.tracking_started = True
            self._reset_tracking_failure_state()
            logging.info(
                "Tracking target %s.",
                "replaced" if retargeted else "activated",
            )
            result = {
                "started": True,
                "retargeted": retargeted,
                "bbox": bbox_tuple,
            }
            if transition["command_hold_applied"]:
                result["target_transition"] = transition
            return result

    async def stop_tracking(self):
        """
        Stops tracking if active.

        Note: For external trackers, manual tracking stop is not supported.
        External trackers stop automatically when external system stops tracking.
        """
        result = await self._stop_following_for_operator_action("stop_tracking")

        # Check if we're using an external tracker
        if getattr(self.tracker, 'is_external_tracker', False):
            tracker_name = self.tracker.__class__.__name__
            logging.warning(f"Manual tracking control not supported for {tracker_name}")
            logging.info(f"{tracker_name} stops automatically when external tracking ends")
            logging.info("Control tracking from camera UI application")
            result["external_tracker"] = True
            result["steps"].append(f"{tracker_name} continues external monitoring")
            return result

        if self.tracking_started:
            self.cancel_activities()
            logging.info("Tracking deactivated.")
            result["steps"].append("Tracking deactivated")
        else:
            logging.info("Tracking is not active.")
            result["steps"].append("Tracking was not active")
        return result

    async def _stop_following_for_operator_action(self, action_name: str) -> Dict[str, Any]:
        """Stop PX4 following before operator actions clear tracking state."""
        result = {"steps": [], "errors": [], "action": action_name}
        if not self.following_active:
            return result

        logging.warning(
            "Operator action '%s' requested while following is active; "
            "disconnecting PX4 follow mode first",
            action_name,
        )
        try:
            disconnect_result = await self.disconnect_px4()
            result["steps"].extend(
                f"[follow-stop] {step}"
                for step in disconnect_result.get("steps", [])
            )
            result["errors"].extend(
                f"[follow-stop] {error}"
                for error in disconnect_result.get("errors", [])
            )
        except Exception as e:
            error_msg = f"Failed to stop following before {action_name}: {e}"
            logging.error(error_msg)
            result["errors"].append(error_msg)
        return result

    async def cancel_activities_async(self) -> Dict[str, Any]:
        """Cancel activities through the operator-safe async path."""
        result = await self._stop_following_for_operator_action("cancel_activities")
        self.cancel_activities()
        result["steps"].append("Tracker activities canceled")
        return result

    def cancel_activities(self):
        """Cancel tracker activities without racing model replacement/inference."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            # Model mutation already fails closed without this barrier. Preserve
            # the safety-critical ability to cancel activities on a damaged or
            # partially constructed controller.
            logging.critical(
                "Canceling activities without tracker/model state barrier"
            )
            return self._cancel_activities_locked()
        with state_lock:
            return self._cancel_activities_locked()

    def _cancel_activities_locked(self):
        """
        Cancels tracking, segmentation, and smart mode activities.

        Note: External trackers continue monitoring even when activities are canceled
        since they operate independently via external control.
        """
        self._advance_tracking_session_generation()
        self.tracking_started = False
        self._reset_tracking_failure_state()
        self.segmentation_active = False
        self.segmentation_selection_frame = None
        self.segmentation_selection_detections = ()
        # self.smart_mode_active = False
        self.selected_bbox = None

        # Reset tracker state (except for external trackers which should keep monitoring)
        if self.tracker and hasattr(self.tracker, 'stop_tracking'):
            if getattr(self.tracker, 'is_external_tracker', False):
                tracker_name = self.tracker.__class__.__name__
                logging.info(f"{tracker_name} continues monitoring - use external control to stop")
            else:
                self.tracker.stop_tracking()

        logging.info("TRACKING STOPPED: All tracker activities canceled")

        if self.setpoint_sender:
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None

        if self.smart_tracker:
            self.smart_tracker.clear_selection()
            # self.smart_tracker = None  # <<< FULL reset


        if self.tracker:
            self.tracker.clear_external_override()  # <<< NEW LINE to disable override when cancelling
            self.tracker.reset()  

        logging.info("All activities cancelled.")


    def is_smart_override_active(self) -> bool:
        return self.smart_mode_active and self.tracker and self.tracker.override_active

    def _log_system_status(self):
        """
        Logs comprehensive system status including tracking, following, and connection states.
        """
        try:
            # Determine active tracking mode
            tracking_status = "Inactive"
            if self.smart_mode_active and self.smart_tracker:
                if hasattr(self.smart_tracker, 'is_tracking_active') and self.smart_tracker.is_tracking_active():
                    tracking_status = "SMART (Active)"
                else:
                    tracking_status = "SMART (Standby)"
            elif self.tracking_started:
                tracker_name = self.tracker.__class__.__name__.replace("Tracker", "")
                tracking_status = f"CLASSIC ({tracker_name})"
            elif self.segmentation_active:
                tracking_status = "Segmentation"
            
            # Following status
            following_status = "Active" if self.following_active else "Inactive"
            
            # MAVLink status
            mavlink_status = "Disabled"
            if Parameters.MAVLINK_ENABLED and self.mavlink_data_manager:
                mavlink_status = self.mavlink_data_manager.connection_state.title()
            
            # PX4 status
            px4_status = "Disconnected"
            if hasattr(self.px4_interface, 'connected') and self.px4_interface.connected:
                px4_status = "Connected"
            
            # Log comprehensive status
            logging.info(f"SYSTEM: Tracking: {tracking_status} | Following: {following_status} | "
                        f"MAVLink: {mavlink_status} | PX4: {px4_status}")
            
        except Exception as e:
            logging.error(f"Error generating system status: {e}")

    def _submit_gstreamer_output_frame(
        self,
        frame: np.ndarray,
    ) -> bool:
        """Submit only frames due at the independent GCS output cadence."""
        submitted_at = time.monotonic()
        if not self.gstreamer_handler.is_frame_due(submitted_at):
            return False
        prepared = False
        output_frame = frame
        if bool(getattr(Parameters, "GSTREAMER_INCLUDE_OSD", True)):
            output_frame = self.gstreamer_handler.prepare_frame_for_osd(frame)
            if output_frame is None:
                return False
            output_frame = self.gstreamer_osd_pipeline.compose(output_frame)
            prepared = True
        return bool(
            self.gstreamer_handler.stream_frame(
                output_frame,
                submitted_at=submitted_at,
                prepared=prepared,
            )
        )

    async def update_loop(self, frame: np.ndarray) -> np.ndarray:
        """
        Main update loop for processing each video frame.
        In classic mode, runs the usual tracker and estimator logic.
        In smart mode, runs AI detection and draws bounding boxes.
        """
        self._capture_app_event_loop()

        # DEBUG: Log every 100th frame to verify update_loop is running
        if not hasattr(self, '_frame_count_debug'):
            self._frame_count_debug = 0
        self._frame_count_debug += 1
        if self._frame_count_debug % 100 == 0:
            logging.info(f"UPDATE_LOOP RUNNING: Frame #{self._frame_count_debug}")

        try:
            # Per-stage timing instrumentation
            _t0 = time.monotonic()

            # Periodic system status update
            current_time = time.time()
            if current_time - self.last_system_status_time > self.system_status_interval:
                self._log_system_status()
                self.last_system_status_time = current_time

            # Preprocess the frame if enabled
            if Parameters.ENABLE_PREPROCESSING and self.preprocessor:
                frame = self.preprocessor.preprocess(frame)
            _t_preprocess = time.monotonic()
            
            # Preserve one clean, processed frame before segmentation, tracker,
            # or OSD drawing. All vision inference and tracker mutation use this
            # analysis frame; overlays are drawn on a separate display copy.
            analysis_frame = frame
            tracking_frame_snapshot = self._publish_tracking_input_frame(
                analysis_frame
            )
            frame = analysis_frame.copy()

            if self.segmentation_active and not self.smart_tracker:
                frame = self._segment_frame_for_selection(
                    analysis_frame,
                    tracking_frame_snapshot,
                )
            else:
                self._clear_segmentation_selection_snapshot()
            
            # # Smart Tracker: always draw overlays if instantiated
            # if self.smart_tracker is None and self.smart_mode_active:
            #     try:
            #         self.smart_tracker = SmartTracker(app_controller=self)
            #         logging.info("SmartTracker instantiated successfully.")
            #     except Exception as e:
            #         logging.error(f"Failed to initialize SmartTracker: {e}")
            #         self.smart_mode_active = False

            if self.smart_tracker:
                frame = self._track_and_draw_smart_frame(analysis_frame.copy())

            # Always-Reporting Trackers (schema-based) - Process when available regardless of manual start
            is_always_reporting = self._is_always_reporting_tracker()

            # DEBUG: Log control flow decisions (only when debug enabled)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"🔍 Control loop: always_reporting={is_always_reporting}, has_tracker={self.tracker is not None}, following_active={self.following_active}")
            # Check tracker type for appropriate handling
            if self.tracker and logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"🔍 Tracker: {self.tracker.__class__.__name__}, external={getattr(self.tracker, 'is_external_tracker', False)}")

            if is_always_reporting and self.tracker:
                # Handle always-reporting trackers (e.g., GimbalTracker)
                try:
                    # Always-reporting trackers update regardless of manual tracking state
                    success, tracker_output = self._update_classic_tracker(analysis_frame)

                    if tracker_output:
                        # Draw tracking overlay for always-reporting trackers
                        frame = self.tracker.draw_tracking(frame, tracking_successful=success)

                        # Handle following if following is active
                        if self.following_active:
                            await self._follow_tracker_output(tracker_output)
                            await self.check_failsafe()
                    else:
                        logging.warning(f"🚨 Always-reporting tracker update failed or no data: success={success}, output={tracker_output}")
                except Exception as e:
                    logging.error(f"Error updating always-reporting tracker: {e}")
            else:
                # Only log this decision when debugging tracker selection
                logging.debug(f"Taking classic tracker path: is_always_reporting={is_always_reporting}, has_tracker={self.tracker is not None}")

            # Classic Tracker (normal tracking or smart override)
            # Smart override mode: SmartTracker controls the classic tracker via external override
            is_smart_override = self.is_smart_override_active()
            classic_active = (self.tracking_started and not self.smart_mode_active)

            # Only process classic trackers if not always-reporting tracker
            if (classic_active or is_smart_override) and not is_always_reporting:
                # Keep evaluating the visual tracker while loss recovery is active.
                # A fresh measured frame can recover naturally; a prediction-only
                # result can never reset the original loss deadline.
                if is_smart_override:
                    success = True
                    measurement_usable = True
                    logging.debug("Smart override active: using SmartTracker-provided tracking data")
                else:
                    success, tracker_output = self._update_classic_tracker(analysis_frame)
                    measurement_usable = self._classic_tracker_update_is_usable(
                        success,
                        tracker_output,
                    )

                if measurement_usable:
                    if self.tracking_failure_start_time is not None:
                        logging.info(
                            "Classic tracker recovered with a fresh measured target "
                            "after %.2f seconds",
                            time.monotonic() - self.tracking_failure_start_time,
                        )
                    self._reset_tracking_failure_state()
                    frame = self.tracker.draw_tracking(frame, tracking_successful=True)
                    if Parameters.ENABLE_DEBUGGING:
                        self.tracker.print_normalized_center()
                    if self.tracker.position_estimator:
                        frame = self.tracker.draw_estimate(frame, tracking_successful=True)
                    if self.following_active:
                        await self.follow_target()
                        await self.check_failsafe()

                    self.frame_counter += 1
                    tracker_confidence = self.tracker.get_confidence()
                    if not self.smart_mode_active:
                        if (tracker_confidence >= Parameters.TRACKER_CONFIDENCE_THRESHOLD_FOR_TEMPLATE_UPDATE and
                            self.frame_counter % Parameters.TEMPLATE_UPDATE_INTERVAL == 0):
                            bbox = self.tracker.bbox
                            if bbox:
                                self.detector.update_template(analysis_frame, bbox)
                                logging.debug(f"TEMPLATE: Updated (Conf: {tracker_confidence:.2f}, Frame: {self.frame_counter})")

                else:
                    frame = await self._handle_classic_tracking_loss(
                        analysis_frame,
                        display_frame=frame,
                    )


            _t_track = time.monotonic()

            # Telemetry handling
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            # Update current frame for app controller
            self.current_frame = frame

            stream_width = Parameters.STREAM_WIDTH
            stream_height = Parameters.STREAM_HEIGHT
            stream_processed = bool(getattr(Parameters, "STREAM_PROCESSED_OSD", True))
            target_resolution = str(
                getattr(Parameters, "OSD_TARGET_LAYER_RESOLUTION", "stream")
            ).strip().lower()

            capture_osd_frame = None
            stream_osd_frame = None

            # Maintain raw resized frame only when stream is configured for non-OSD output.
            self.video_handler.update_resized_frames(
                stream_width,
                stream_height,
                resize_raw=not stream_processed,
                resize_osd=False,
                raw_frame=self.video_handler.current_raw_frame if self.video_handler.current_raw_frame is not None else frame,
            )

            if stream_processed:
                if target_resolution == "capture":
                    capture_osd_frame = self.osd_pipeline.compose(frame.copy())
                    stream_osd_frame = self.video_handler.resize_frame(
                        capture_osd_frame, stream_width, stream_height
                    )
                    self.video_handler.current_osd_frame = capture_osd_frame
                else:
                    stream_base = self.video_handler.resize_frame(frame, stream_width, stream_height)
                    stream_osd_frame = self.osd_pipeline.compose(stream_base)
                    # Keep compatibility for code paths that inspect current_osd_frame.
                    self.video_handler.current_osd_frame = frame

                self.video_handler.current_resized_osd_frame = stream_osd_frame
                # Publish to thread-safe frame publisher for streaming consumers
                self.frame_publisher.publish(
                    osd_frame=stream_osd_frame,
                    raw_frame=self.video_handler.current_resized_raw_frame,
                )
            else:
                self.video_handler.current_osd_frame = frame
                self.video_handler.current_resized_osd_frame = None
                # Publish raw frame when OSD is disabled
                self.frame_publisher.publish(
                    osd_frame=None,
                    raw_frame=self.video_handler.current_resized_raw_frame,
                )

            _t_osd = time.monotonic()

            # Optional secondary GStreamer output
            if (
                Parameters.ENABLE_GSTREAMER_STREAM
                and self.gstreamer_handler is not None
            ):
                self._submit_gstreamer_output_frame(
                    frame=frame,
                )

            # Optional local video recording (non-blocking)
            if hasattr(self, 'recording_manager') and self.recording_manager and self.recording_manager.is_recording:
                if self.recording_manager._include_osd:
                    if capture_osd_frame is not None:
                        # OSD already composed at capture resolution
                        self.recording_manager.write_frame(capture_osd_frame)
                    elif stream_processed and hasattr(self, 'osd_pipeline'):
                        # OSD was composed at stream resolution only — compose
                        # at capture resolution for recording
                        rec_frame = self.osd_pipeline.compose(frame.copy())
                        self.recording_manager.write_frame(rec_frame)
                    else:
                        self.recording_manager.write_frame(frame)
                else:
                    self.recording_manager.write_frame(frame)

            _t_publish = time.monotonic()

            # Update per-stage pipeline metrics
            self._pipeline_metrics['preprocess_ms'] = round((_t_preprocess - _t0) * 1000, 2)
            self._pipeline_metrics['tracking_ms'] = round((_t_track - _t_preprocess) * 1000, 2)
            self._pipeline_metrics['osd_ms'] = round((_t_osd - _t_track) * 1000, 2)
            self._pipeline_metrics['publish_ms'] = round((_t_publish - _t_osd) * 1000, 2)

        except Exception as e:
            logging.exception(f"Error in update_loop: {e}")
        return frame

    def _reset_tracking_failure_state(self) -> None:
        """Reset controller-owned classic tracker recovery bookkeeping."""
        self.tracking_failure_start_time = None
        self._tracking_recovery_attempts = 0
        self._tracking_next_recovery_attempt_at = None

    def _advance_tracking_session_generation(self) -> int:
        """Invalidate asynchronous work associated with the previous target."""
        generation = int(getattr(self, "_tracking_session_generation", 0)) + 1
        self._tracking_session_generation = generation
        return generation

    def _next_smart_selection_generation(self) -> int:
        """Reserve an ordering ticket before a smart-click await boundary."""
        lock = getattr(self, "_smart_selection_generation_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._smart_selection_generation_lock = lock
        with lock:
            generation = int(getattr(self, "_smart_selection_generation", 0)) + 1
            self._smart_selection_generation = generation
            return generation

    def _smart_selection_generation_is_current(self, generation: int) -> bool:
        """Return whether a queued smart-click is still the newest request."""
        return int(getattr(self, "_smart_selection_generation", 0)) == int(generation)

    def _tracking_session_is_current(self, generation: int) -> bool:
        """Return whether recovery work still belongs to the active target."""
        return (
            bool(getattr(self, "tracking_started", False))
            and int(getattr(self, "_tracking_session_generation", 0)) == generation
        )

    def _classic_tracker_update_is_usable(
        self,
        update_success: bool,
        tracker_output: Optional[TrackerOutput] = None,
    ) -> bool:
        """Accept only an explicitly command-usable measured tracker update."""
        if not update_success or not self.tracker:
            return False

        if not isinstance(tracker_output, TrackerOutput):
            output_getter = getattr(self.tracker, "get_output", None)
            if not callable(output_getter):
                logging.error(
                    "Classic tracker reported success without a typed output contract"
                )
                return False
            try:
                tracker_output = output_getter()
            except Exception as exc:
                logging.error("Could not validate classic tracker output: %s", exc)
                return False

        if not isinstance(tracker_output, TrackerOutput):
            return False

        freshness = evaluate_tracker_command_freshness(tracker_output)
        return bool(freshness["usable_for_following"])

    @staticmethod
    def _classic_tracking_recovery_policy() -> Tuple[float, int]:
        """Return bounded recovery timeout and attempt count from canonical config."""
        try:
            timeout = max(0.0, float(Parameters.TRACKING_FAILURE_TIMEOUT))
        except (TypeError, ValueError):
            timeout = 0.0
        try:
            attempts = max(0, int(Parameters.REDETECTION_ATTEMPTS))
        except (TypeError, ValueError):
            attempts = 0
        return timeout, attempts

    async def _handle_classic_tracking_loss(
        self,
        analysis_frame: Optional[np.ndarray],
        *,
        display_frame: Optional[np.ndarray] = None,
        failure_reason: Optional[str] = None,
        frame_status: Optional[Dict[str, Any]] = None,
    ) -> Optional[np.ndarray]:
        """Fail closed and perform bounded detector-assisted target recovery."""
        frame = analysis_frame if display_frame is None else display_frame
        expected_generation = int(
            getattr(self, "_tracking_session_generation", 0)
        )
        if not self._tracking_session_is_current(expected_generation):
            return frame

        now = time.monotonic()
        timeout, max_attempts = self._classic_tracking_recovery_policy()

        if getattr(self, "tracking_failure_start_time", None) is None:
            self.tracking_failure_start_time = now
            self._tracking_recovery_attempts = 0
            initial_interval = (
                timeout / (max_attempts + 1)
                if timeout > 0 and max_attempts > 0
                else timeout
            )
            self._tracking_next_recovery_attempt_at = now + initial_interval
            logging.warning(
                "Classic tracker lost a command-usable measurement; starting "
                "a bounded %.2f second recovery window",
                timeout,
            )

        elapsed = now - self.tracking_failure_start_time
        self.frame_counter = 0

        estimator_update = getattr(
            self.tracker, "update_estimator_without_measurement", None
        )
        if callable(estimator_update):
            estimator_update()
        estimate_drawer = getattr(self.tracker, "draw_estimate", None)
        if frame is not None and callable(estimate_drawer):
            frame = estimate_drawer(frame, tracking_successful=False)

        if self.following_active:
            reason = failure_reason or (
                "classic_tracker_update_failed"
                if elapsed == 0.0
                else "classic_tracker_recovery_prediction"
            )
            await self._dispatch_unusable_tracker_output(
                reason=reason,
                frame_status=frame_status,
            )
            await self.check_failsafe()

        if not self._tracking_session_is_current(expected_generation):
            return frame

        if elapsed >= timeout:
            self._terminate_classic_tracking_loss(
                reason="recovery_timeout",
                elapsed=elapsed,
                expected_generation=expected_generation,
            )
            return frame

        detector_recovery_enabled = bool(
            Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT and max_attempts > 0
        )
        next_attempt_at = getattr(self, "_tracking_next_recovery_attempt_at", None)
        if (
            detector_recovery_enabled
            and analysis_frame is not None
            and getattr(self, "_tracking_recovery_attempts", 0) < max_attempts
            and (next_attempt_at is None or now >= next_attempt_at)
        ):
            self._tracking_recovery_attempts += 1
            attempt = self._tracking_recovery_attempts
            result = self.handle_tracking_failure(analysis_frame)
            if not self._tracking_session_is_current(expected_generation):
                return frame
            interval = timeout / (max_attempts + 1) if max_attempts else timeout
            self._tracking_next_recovery_attempt_at = (
                self.tracking_failure_start_time + ((attempt + 1) * interval)
            )

            if isinstance(result, dict) and result.get("success") is True:
                logging.info(
                    "Re-detection candidate initialized on bounded attempt %d/%d; "
                    "waiting for a fresh measured tracker update",
                    attempt,
                    max_attempts,
                )
            elif attempt == max_attempts:
                logging.warning(
                    "Re-detection attempts exhausted (%d/%d); tracker remains "
                    "fail-closed until the original recovery deadline",
                    attempt,
                    max_attempts,
                )

        return frame

    def _terminate_classic_tracking_loss(
        self,
        reason: str,
        elapsed: float,
        *,
        expected_generation: int,
    ) -> bool:
        """End one failed session only if the operator has not replaced it."""
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is not None:
            with state_lock:
                return self._terminate_classic_tracking_loss_locked(
                    reason,
                    elapsed,
                    expected_generation=expected_generation,
                )
        return self._terminate_classic_tracking_loss_locked(
            reason,
            elapsed,
            expected_generation=expected_generation,
        )

    def _terminate_classic_tracking_loss_locked(
        self,
        reason: str,
        elapsed: float,
        *,
        expected_generation: int,
    ) -> bool:
        """Clear target geometry while holding the tracker state barrier."""
        if not self._tracking_session_is_current(expected_generation):
            logging.info(
                "Ignoring stale classic-tracker recovery termination for session %d",
                expected_generation,
            )
            return False
        attempts = getattr(self, "_tracking_recovery_attempts", 0)
        logging.error(
            "Classic tracking stopped after %.2f seconds (%s, %d re-detection attempts)",
            elapsed,
            reason,
            attempts,
        )
        self.tracking_started = False
        stop_tracking = getattr(self.tracker, "stop_tracking", None)
        if callable(stop_tracking):
            stop_tracking()
        self._reset_tracking_failure_state()
        self._advance_tracking_session_generation()
        return True

    def handle_tracking_failure(self, frame: Optional[np.ndarray] = None):
        """
        Handles tracking failure by attempting re-detection using the detector.
        Only used in classic mode.
        """
        # Don't use classic detector re-detection when smart tracker is active
        if self.smart_mode_active:
            logging.debug("Smart tracker is active, skipping classic re-detection")
            return {"success": False, "message": "Smart tracker mode - classic re-detection disabled."}
            
        if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
            logging.info("Attempting to re-detect the target using the detector.")
            redetect_result = self.initiate_redetection(frame=frame)
            if redetect_result["success"]:
                logging.info("Target re-detected and tracker re-initialized.")
            else:
                logging.info("Re-detection attempt failed. Retrying...")
            return redetect_result
        return {"success": False, "message": "Detector not enabled or auto-redetect off."}

    async def check_failsafe(self):
        if getattr(getattr(self, "px4_interface", None), "failsafe_active", False):
            await self.handle_failsafe()
            self.px4_interface.failsafe_active = False

    async def handle_failsafe(self):
        await self.disconnect_px4()

    async def _handle_offboard_mode_exit(self, old_mode, new_mode):
        """Route observed Offboard-exit cleanup to the flight owner loop."""
        return await self._run_on_flight_event_loop(
            lambda: self._handle_offboard_mode_exit_on_flight_loop(old_mode, new_mode)
        )

    async def _handle_offboard_mode_exit_on_flight_loop(self, old_mode, new_mode):
        """
        Automatically disable follow mode when drone exits Offboard mode.

        This method is called by the MAVLink data manager when it detects a flight
        mode transition from Offboard to any other mode. This ensures that the
        follow mode state is automatically synchronized with the drone's actual
        flight mode, regardless of how the mode was changed (pilot, failsafe, etc.).

        Args:
            old_mode (int): Previous flight mode code (393216 for Offboard)
            new_mode (int): New flight mode code

        Affected components:
        - following_active flag → Set to False
        - OSD scope color → Changes from red (active) to yellow (inactive)
        - Dashboard UI → Updates to show follow mode disabled
        - Telemetry → Updates following_active status
        """
        if not self.following_active:
            # Follow mode already inactive, no action needed
            return

        try:
            # Get human-readable mode names for logging
            mode_name = self.px4_interface.get_flight_mode_text(new_mode)

            logging.warning(
                f"OFFBOARD MODE EXITED: Drone switched to {mode_name} ({new_mode}). "
                f"Automatically disabling follow mode for safety."
            )

            # Gracefully stop follow mode using existing disconnect logic
            # This will:
            # - Stop the Offboard commander and legacy setpoint sender monitor
            # - Stop offboard mode (if still active)
            # - Clean up follower instance
            # - Set following_active = False
            # - Update all UI indicators (OSD scope color, dashboard status, etc.)
            await self._disconnect_px4_on_flight_loop(
                commander_publish_final=False,
                attempt_offboard_stop=False,
                cancel_pending_start=True,
            )

            logging.info("Follow mode automatically disabled due to Offboard mode exit")

        except Exception as e:
            logging.error(f"Error handling Offboard mode exit: {e}")
            # Ensure following_active is set to False even if cleanup fails
            self.following_active = False

    async def _handle_px4_connection_loss(self, connection_status: Dict[str, Any]):
        """Route MAVSDK link-loss cleanup to the flight owner loop."""
        return await self._run_on_flight_event_loop(
            lambda: self._handle_px4_connection_loss_on_flight_loop(connection_status)
        )

    async def _handle_px4_connection_loss_on_flight_loop(
        self,
        connection_status: Dict[str, Any],
    ):
        """Stop local following after MAVSDK reports loss of the PX4 vehicle."""
        logging.error(
            "PX4 CONNECTION LOST: %s. Stopping local follow mode without sending "
            "commands over the failed link.",
            connection_status.get("last_error", "unknown MAVSDK connection loss"),
        )
        await self._disconnect_px4_on_flight_loop(
            commander_publish_final=False,
            attempt_offboard_stop=False,
            cancel_pending_start=True,
        )

    def bind_flight_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind the one event loop that owns PX4 and Offboard lifecycle tasks."""
        if loop is None or loop.is_closed():
            raise RuntimeError("Cannot bind a missing or closed flight event loop")

        bind_lock = getattr(self, "_flight_event_loop_bind_lock", None)
        if bind_lock is None:
            bind_lock = threading.Lock()
            self._flight_event_loop_bind_lock = bind_lock

        with bind_lock:
            existing = getattr(self, "_flight_event_loop", None)
            if existing is not None and existing is not loop:
                raise RuntimeError(
                    "PixEagle flight event loop is already bound to another loop"
                )
            self._flight_event_loop = loop
            self._app_event_loop = loop

    def _capture_app_event_loop(self) -> None:
        """Bind the current loop only when no explicit flight owner exists yet."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        existing = getattr(self, "_flight_event_loop", None)
        if existing is None:
            self.bind_flight_event_loop(loop)

    def _get_flight_event_loop(self):
        """Return the stable owner loop, including the compatibility alias."""
        return (
            getattr(self, "_flight_event_loop", None)
            or getattr(self, "_app_event_loop", None)
        )

    async def _run_on_flight_event_loop(self, operation):
        """Execute one coroutine factory on the stable flight owner loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError("Flight operation requires a running event loop") from exc

        owner_loop = self._get_flight_event_loop()
        if owner_loop is None:
            self.bind_flight_event_loop(current_loop)
            owner_loop = current_loop

        if owner_loop is current_loop:
            return await operation()
        if owner_loop.is_closed() or not owner_loop.is_running():
            raise RuntimeError("PixEagle flight event loop is not running")

        owner_future = asyncio.run_coroutine_threadsafe(operation(), owner_loop)
        try:
            return await asyncio.wrap_future(owner_future)
        except asyncio.CancelledError:
            owner_future.cancel()
            raise

    def _schedule_on_flight_event_loop(
        self,
        operation,
        *,
        failure_message: str,
        fail_closed,
    ) -> None:
        """Schedule one coroutine factory only on the stable flight owner loop."""
        owner_loop = self._get_flight_event_loop()
        if owner_loop is None or owner_loop.is_closed() or not owner_loop.is_running():
            logging.error(failure_message)
            fail_closed(None)
            return

        try:
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is owner_loop:
                owner_loop.create_task(operation())
            else:
                asyncio.run_coroutine_threadsafe(operation(), owner_loop)
        except Exception as exc:
            logging.error("%s: %s", failure_message, exc)
            fail_closed(exc)

    def _schedule_offboard_mode_exit(self, old_mode, new_mode) -> None:
        """
        Schedule Offboard-exit cleanup from any thread.

        MavlinkDataManager polls in a worker thread, so this cannot rely on
        `asyncio.create_task()` being available in the caller's thread.
        """
        def fail_closed(_exc) -> None:
            self.following_active = False

        self._schedule_on_flight_event_loop(
            lambda: self._handle_offboard_mode_exit(
                old_mode,
                new_mode,
            ),
            failure_message=(
                "Offboard exit detected but the flight event loop is unavailable; "
                "clearing follow mode state synchronously"
            ),
            fail_closed=fail_closed,
        )

    async def handle_key_input_async(self, key: int, frame: np.ndarray):
        """
        Asynchronous key input handler.
        'y' toggles segmentation.
        't' toggles classic tracking.
        's' toggles smart mode.
        Other keys perform PX4 or re-detection actions.
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            if self.following_active:
                await self.cancel_activities_async()
            else:
                self.toggle_tracking(frame)
        # Within the key input handler (handle_key_input_async)
        elif key == ord('s'):
            if self.following_active:
                await self.cancel_activities_async()
            self.toggle_smart_mode()
        elif key == ord('d'):
            self.initiate_redetection(frame=frame)
        elif key == ord('f'):
            await self.connect_px4()
        elif key == ord('x'):
            await self.disconnect_px4()
        elif key == ord('c'):
            await self.cancel_activities_async()
        elif key == ord('o'):
            new_preset = self.osd_mode_manager.cycle_preset()
            self.logger.info(f"OSD preset cycled to: {new_preset}")
        elif key == ord('n'):
            new_mode = self.osd_mode_manager.cycle_color_mode()
            self.logger.info(f"OSD color mode cycled to: {new_mode}")
        elif key == ord('r'):
            if hasattr(self, 'recording_manager') and self.recording_manager:
                if self.recording_manager.is_active:
                    result = self.recording_manager.stop()
                    self.logger.info(f"Recording stopped via keyboard: {result.get('message', '')}")
                else:
                    source_fps = self.video_handler.fps if hasattr(self.video_handler, 'fps') else 30
                    cap = self.video_handler.cap if hasattr(self.video_handler, 'cap') else None
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap else 640
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap else 480
                    result = self.recording_manager.start(source_fps or 30, w, h)
                    self.logger.info(f"Recording via keyboard: {result.get('message', '')}")

    def handle_key_input(self, key: int, frame: np.ndarray):
        """
        Synchronous key input handler that schedules the asynchronous handler.
        """
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x: int, y: int) -> Dict[str, Any]:
        """
        Handles user click events for segmentation-based object selection.
        """
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {"success": False, "reason": "follower_state_barrier_unavailable"}
        if follower_lock.locked():
            return {"success": False, "reason": "follower_lifecycle_busy"}
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            return {
                "success": False,
                "reason": "tracker_model_state_barrier_unavailable",
            }
        with state_lock:
            return self._handle_user_click_locked(x, y)

    def _handle_user_click_locked(self, x: int, y: int) -> Dict[str, Any]:
        """Select and initialize one segmented target under the state barrier."""
        if not self.segmentation_active:
            return {"success": False, "reason": "segmentation_inactive"}
        if self.following_active:
            logging.warning(
                "Segmentation target selection refused while following is active"
            )
            return {"success": False, "reason": "following_active"}

        selection_frame, detections = self.get_segmentation_selection_snapshot()
        if selection_frame is None:
            return {"success": False, "reason": "segmentation_frame_unavailable"}
        selected_bbox = self.identify_clicked_object(detections, x, y)
        if selected_bbox is None:
            return {"success": False, "reason": "no_detection_at_click"}

        frame_height, frame_width = selection_frame.shape[:2]
        try:
            bbox_pixels = tracking_xyxy_to_pixels(
                selected_bbox,
                frame_width=frame_width,
                frame_height=frame_height,
            )
        except TrackingROIError as exc:
            logging.warning("Rejected invalid segmentation selection: %s", exc)
            return {"success": False, "reason": "invalid_detection_bbox"}

        bbox_tuple = (
            bbox_pixels["x"],
            bbox_pixels["y"],
            bbox_pixels["width"],
            bbox_pixels["height"],
        )
        if self.tracker is None:
            return {"success": False, "reason": "tracker_state_unavailable"}

        try:
            self.tracker.reinitialize_tracker(selection_frame, bbox_tuple)
            self.tracking_started = True
            self._advance_tracking_session_generation()
            self._reset_tracking_failure_state()
        except Exception as exc:
            self.tracking_started = False
            stop_tracking = getattr(self.tracker, "stop_tracking", None)
            if callable(stop_tracking):
                stop_tracking()
            self._reset_tracking_failure_state()
            logging.warning(
                "Segmentation tracker initialization failed: %s",
                exc,
            )
            return {"success": False, "reason": "tracker_initialization_failed"}

        logging.info("Object selected for tracking: %s", bbox_tuple)
        return {
            "success": True,
            "reason": "tracker_initialized",
            "bounding_box": bbox_tuple,
        }

    def identify_clicked_object(self, detections: list, x: int, y: int) -> Optional[Tuple[int, int, int, int]]:
        """
        Identifies the clicked object based on segmentation detections.
        """
        for det in detections:
            x1, y1, x2, y2 = det
            if x1 <= x <= x2 and y1 <= y <= y2:
                return det
        return None

    def initiate_redetection(
        self,
        frame: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Attempts to re-detect the target using the detector (classic mode only).
        """
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {
                "success": False,
                "message": "Follower state barrier is unavailable.",
            }
        if follower_lock.locked():
            return {
                "success": False,
                "message": "Follower lifecycle transition is in progress.",
            }
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            return {
                "success": False,
                "message": "Tracker/model state barrier is unavailable.",
            }
        with state_lock:
            return self._initiate_redetection_locked(frame=frame)

    def _initiate_redetection_locked(
        self,
        frame: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Detect and reinitialize one target while tracker identity is stable."""
        if Parameters.USE_DETECTOR:
            recovery_frame = frame
            if recovery_frame is None:
                recovery_frame = self.get_tracking_input_frame_snapshot()
            if recovery_frame is None:
                return {
                    "success": False,
                    "message": "Re-detection requires a current tracking frame.",
                }
            frame_height, frame_width = recovery_frame.shape[:2]
            estimate = self.tracker.get_estimated_position()
            if estimate:
                estimated_x, estimated_y = estimate[:2]
                search_radius = Parameters.REDETECTION_SEARCH_RADIUS
                x_min = max(0, int(estimated_x - search_radius))
                x_max = min(frame_width, int(estimated_x + search_radius))
                y_min = max(0, int(estimated_y - search_radius))
                y_max = min(frame_height, int(estimated_y + search_radius))
                search_region = (x_min, y_min, x_max - x_min, y_max - y_min)
                redetect_result = self.detector.smart_redetection(
                    recovery_frame, self.tracker, roi=search_region
                )
            else:
                redetect_result = self.detector.smart_redetection(
                    recovery_frame,
                    self.tracker,
                )

            if redetect_result:
                detected_bbox = self.detector.get_latest_bbox()
                try:
                    bbox_pixels = tracking_roi_to_pixels(
                        x=detected_bbox[0],
                        y=detected_bbox[1],
                        width=detected_bbox[2],
                        height=detected_bbox[3],
                        coordinate_space="pixels",
                        frame_width=frame_width,
                        frame_height=frame_height,
                    )
                except (IndexError, TypeError, TrackingROIError) as exc:
                    logging.warning("Rejected invalid re-detection ROI: %s", exc)
                    return {
                        "success": False,
                        "message": "Re-detection returned an invalid bounding box.",
                    }
                bbox_tuple = (
                    bbox_pixels["x"],
                    bbox_pixels["y"],
                    bbox_pixels["width"],
                    bbox_pixels["height"],
                )
                try:
                    self.tracker.reinitialize_tracker(recovery_frame, bbox_tuple)
                    self.tracking_started = True
                except Exception as exc:
                    stop_tracking = getattr(self.tracker, "stop_tracking", None)
                    if callable(stop_tracking):
                        stop_tracking()
                    logging.warning(
                        "Re-detection tracker initialization failed: %s",
                        exc,
                    )
                    return {
                        "success": False,
                        "message": "Re-detection could not initialize the tracker.",
                    }
                logging.info("Re-detection successful and tracker re-initialized.")
                return {
                    "success": True,
                    "message": "Re-detection successful and tracker re-initialized.",
                    "bounding_box": bbox_tuple,
                }
            else:
                logging.info("Re-detection failed or no new object found.")
                return {
                    "success": False,
                    "message": "Re-detection failed or no new object found."
                }
        else:
            return {
                "success": False,
                "message": "Detector is not enabled."
            }

    def show_current_frame(self, frame_title: str = Parameters.FRAME_TITLE) -> np.ndarray:
        """
        Displays the current frame in a window if enabled.
        """
        if self.local_video_window_available:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def _apply_pending_follower_config(self) -> Dict[str, Any]:
        """Apply only immediate/follower-tier paths before a new follow session."""
        from classes.config_service import ConfigService

        return await asyncio.to_thread(
            ConfigService.get_instance().apply_runtime_config_tiers,
            {"immediate", "follower_restart"},
            source="follow_session_start",
        )

    def _assert_setpoint_handler_ownership(self, *, require_commander: bool) -> None:
        """Require one handler across follower and active publication paths."""
        follower_manager = self.follower
        concrete_follower = getattr(follower_manager, "follower", None)
        follower_handler = getattr(concrete_follower, "setpoint_handler", None)
        active_controller = getattr(self, "_active_following_controller", None)
        controller_handler = getattr(active_controller, "setpoint_handler", None)
        if follower_handler is None or controller_handler is not follower_handler:
            raise RuntimeError(
                "Follower/command-controller setpoint handler ownership invariant failed"
            )
        if require_commander:
            commander_handler = getattr(
                self.offboard_commander,
                "setpoint_handler",
                None,
            )
            if commander_handler is not follower_handler:
                raise RuntimeError(
                    "Follower/command-controller/commander setpoint handler ownership invariant failed"
                )

    def _configured_follower_execution_mode(self) -> str:
        """Return the normalized configured mode, failing closed on bad input."""
        return get_configured_follower_execution_mode()

    def _is_command_preview_configured(self) -> bool:
        return (
            self._configured_follower_execution_mode()
            == COMMAND_PREVIEW_EXECUTION_MODE
        )

    def _is_command_preview_session(self) -> bool:
        return (
            getattr(self, "following_execution_mode", PX4_EXECUTION_MODE)
            == COMMAND_PREVIEW_EXECUTION_MODE
        )

    def _reset_following_execution_state(self) -> None:
        """Reset mode claims without assuming a fully constructed controller."""
        self.following_execution_mode = PX4_EXECUTION_MODE
        self._active_following_controller = getattr(self, "px4_interface", None)

    def _get_command_preview_readiness(
        self,
        runtime_status: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return the explicit no-PX4 command-preview readiness contract."""
        return evaluate_command_preview_start_readiness(
            self,
            runtime_status=runtime_status,
        )

    async def connect_px4(self) -> Dict[str, any]:
        """Start one follow session on the stable flight owner loop."""
        return await self._run_on_flight_event_loop(
            self._connect_px4_once_on_flight_loop
        )

    def _get_follow_start_readiness(self) -> Dict[str, Any]:
        """Return the same live readiness contract used by the API preflight."""
        return evaluate_following_start_readiness(self)

    def _require_follow_start_readiness(
        self,
        result: Dict[str, Any],
        *,
        stage: str,
    ) -> None:
        """Fail closed if target/video readiness changed during startup."""
        readiness = self._get_follow_start_readiness()
        result[f"tracker_readiness_{stage}"] = readiness
        if readiness.get("usable_for_following") is True:
            return

        frame_status = readiness.get("video_frame_status") or {}
        if frame_status.get("replay_source") is True:
            code = "video_replay_not_authorized"
        elif readiness.get("tracker_requires_video"):
            code = "video_or_tracker_not_fresh"
        else:
            code = "tracker_not_usable"
        reason = str(
            readiness.get("reason")
            or "Tracker output is not usable for autonomous following"
        )
        result["precondition"] = {
            "code": code,
            "stage": stage,
            "reason": reason,
        }
        raise RuntimeError(f"Following readiness changed during startup: {reason}")

    async def _connect_px4_once_on_flight_loop(self) -> Dict[str, Any]:
        """Coalesce concurrent starts and retain an abortable startup task."""
        existing = getattr(self, "_follow_start_task", None)
        if existing is not None and not existing.done():
            return await asyncio.shield(existing)

        start_task = asyncio.create_task(
            self._connect_px4_on_flight_loop(),
            name="pixeagle-follow-start",
        )
        self._follow_start_task = start_task
        try:
            return await start_task
        finally:
            if getattr(self, "_follow_start_task", None) is start_task:
                self._follow_start_task = None

    async def _connect_command_preview_on_flight_loop(self) -> Dict[str, Any]:
        """Start a tracker-driven follower session with a local intent sink."""
        result: Dict[str, Any] = {
            "steps": [],
            "errors": [],
            "auto_stopped": False,
            "execution_mode": COMMAND_PREVIEW_EXECUTION_MODE,
            "commands_sent_to_px4": False,
            "px4_connection_attempted": False,
        }

        async with self._follower_state_lock:
            readiness = self._get_command_preview_readiness()
            result["command_preview_readiness"] = readiness
            if not readiness.get("ready", False):
                result["errors"].append(
                    str(
                        readiness.get("reason")
                        or "Command preview preflight failed"
                    )
                )
                result["precondition"] = {
                    "code": "command_preview_not_ready",
                    "reason": readiness.get("reason"),
                }
                logging.warning(
                    "Command preview start refused: %s",
                    readiness.get("reason"),
                )
                return result

            has_runtime_components = any(
                getattr(self, name, None) is not None
                for name in ("offboard_commander", "setpoint_sender", "follower")
            )
            if self.following_active or has_runtime_components:
                result["steps"].append(
                    "Auto-stopping active follower before command preview restart"
                )
                result["auto_stopped"] = True
                stop_result = await self._disconnect_px4_internal()
                result["steps"].extend(
                    f"[Auto-stop] {step}" for step in stop_result["steps"]
                )
                if stop_result["errors"]:
                    result["errors"].extend(
                        f"[Auto-stop] {error}" for error in stop_result["errors"]
                    )
                    raise RuntimeError(
                        "Existing follow session did not stop cleanly; "
                        "command preview restart refused"
                    )

            try:
                publication = await self._apply_pending_follower_config()
                if publication["applied_count"]:
                    result["steps"].append(
                        "Applied pending follower configuration "
                        f"({publication['applied_count']} paths)"
                    )

                if Parameters.TARGET_POSITION_MODE == "initial":
                    normalized_center = getattr(self.tracker, "normalized_center", None)
                    initial_target_coords = (
                        tuple(normalized_center)
                        if isinstance(normalized_center, (tuple, list))
                        and len(normalized_center) == 2
                        else tuple(Parameters.DESIRE_AIM)
                    )
                else:
                    initial_target_coords = tuple(Parameters.DESIRE_AIM)

                preview_controller = CommandPreviewController()
                preview_controller.active_mode = True
                self._active_following_controller = preview_controller
                self.follower = Follower(
                    preview_controller,
                    initial_target_coords,
                )
                self._assert_setpoint_handler_ownership(require_commander=False)
                if getattr(self, "telemetry_handler", None) is not None:
                    self.telemetry_handler.follower = self.follower

                if not self.follower.validate_current_mode():
                    raise RuntimeError(
                        "Follower mode validation failed; command preview refused"
                    )
                result["steps"].append(
                    f"Follower created: {self.follower.get_display_name()}"
                )

                self.following_execution_mode = COMMAND_PREVIEW_EXECUTION_MODE
                result["command_preview_readiness_after_follower"] = (
                    self._get_command_preview_readiness()
                )
                if not result["command_preview_readiness_after_follower"].get(
                    "ready", False
                ):
                    raise RuntimeError(
                        "Command preview readiness changed during startup: "
                        + str(
                            result["command_preview_readiness_after_follower"].get(
                                "reason"
                            )
                        )
                    )

                self.offboard_commander = CommandPreviewCommander(
                    self.follower.follower.setpoint_handler
                )
                self._assert_setpoint_handler_ownership(require_commander=True)
                if not await self.offboard_commander.start():
                    raise RuntimeError(
                        self.offboard_commander.last_error
                        or "Command preview capture failed to start"
                    )

                self.following_active = True
                self.last_offboard_commander_failure = None
                result["steps"].append(
                    "Command preview started; follower intents are recorded locally"
                )
                logging.info(
                    "Command preview activated for %s; no PX4/MAVSDK command path",
                    self.follower.get_display_name(),
                )
            except asyncio.CancelledError:
                await self._cleanup_failed_follow_start(
                    result,
                    offboard_cleanup_required=False,
                )
                raise
            except Exception as exc:
                error = f"Failed to start command preview: {exc}"
                logging.error(error)
                result["errors"].append(error)
                await self._cleanup_failed_follow_start(
                    result,
                    offboard_cleanup_required=False,
                )

        return result

    async def _connect_px4_on_flight_loop(self) -> Dict[str, Any]:
        """
        Enhanced PX4 connection with unified command protocol support.
        Automatically stops existing follower if active before starting a new one.

        Returns:
            Dict with status information including steps taken and any errors
        """
        if self._is_command_preview_configured():
            return await self._connect_command_preview_on_flight_loop()

        result = {"steps": [], "errors": [], "auto_stopped": False}
        offboard_cleanup_required = False

        # Use lock to prevent race conditions during state changes
        async with self._follower_state_lock:
            circuit_state = FollowerCircuitBreaker.get_activation_state()
            if circuit_state["active"]:
                message = (
                    "Circuit breaker is active; PX4 command dispatch is inhibited"
                    if circuit_state["available"]
                    else "Circuit-breaker state is unavailable; PX4 command dispatch "
                    "remains inhibited"
                )
                result["precondition"] = {
                    "code": (
                        "circuit_breaker_command_inhibit_active"
                        if circuit_state["available"]
                        else "circuit_breaker_state_unavailable"
                    ),
                    "circuit_breaker": circuit_state,
                }
                result["errors"].append(message)
                logging.warning(
                    "Follow start refused before PX4 connection: %s",
                    message,
                )
                return result

            # Auto-stop if follower is already active (user-friendly feature)
            has_runtime_components = any(
                getattr(self, name, None) is not None
                for name in ("offboard_commander", "setpoint_sender", "follower")
            )
            if self.following_active or has_runtime_components:
                logging.info("Follower already active - automatically stopping before restart...")
                result["steps"].append("Auto-stopping active follower for restart")
                result["auto_stopped"] = True

                # Call internal stop without acquiring lock again
                stop_result = await self._disconnect_px4_internal()
                result["steps"].extend([f"[Auto-stop] {step}" for step in stop_result["steps"]])

                if stop_result["errors"]:
                    result["errors"].extend([f"[Auto-stop] {err}" for err in stop_result["errors"]])
                    raise RuntimeError(
                        "Existing follow session did not stop cleanly; restart refused"
                    )

            # Now proceed with starting follower
            try:
                logging.info("Activating Follow Mode to PX4!")

                publication = await self._apply_pending_follower_config()
                if publication["applied_count"]:
                    result["steps"].append(
                        "Applied pending follower configuration "
                        f"({publication['applied_count']} paths)"
                    )

                # Connect to PX4
                connection_status = await self.px4_interface.connect()
                if (
                    not isinstance(connection_status, dict)
                    or connection_status.get("connected") is not True
                ):
                    raise RuntimeError(
                        "MAVSDK returned without confirming a PX4 vehicle connection"
                    )
                result["px4_connection"] = dict(connection_status)
                result["steps"].append("MAVSDK vehicle connection confirmed")
                logging.info("MAVSDK vehicle connection confirmed")

                telemetry_readiness = await self.px4_interface.wait_for_telemetry_ready()
                result["px4_telemetry"] = dict(telemetry_readiness)
                if telemetry_readiness.get("ready") is not True:
                    raise RuntimeError(
                        "PX4 link connected but follower telemetry is not ready: "
                        f"state={telemetry_readiness.get('state', 'unknown')}; "
                        f"error={telemetry_readiness.get('last_error') or 'none'}"
                    )
                result["steps"].append(
                    "Complete follower telemetry confirmed "
                    f"({telemetry_readiness.get('source', 'unknown')})"
                )

                # Determine initial target coordinates
                initial_target_coords = (
                    tuple(self.tracker.normalized_center)
                    if Parameters.TARGET_POSITION_MODE == 'initial'
                    else tuple(Parameters.DESIRE_AIM)
                )

                # Create follower using enhanced factory
                try:
                    self.following_execution_mode = PX4_EXECUTION_MODE
                    self._active_following_controller = self.px4_interface
                    self.follower = Follower(self.px4_interface, initial_target_coords)
                    self._assert_setpoint_handler_ownership(require_commander=False)

                    # Update telemetry handler
                    self.telemetry_handler.follower = self.follower

                    # Log follower information
                    logging.info(f"Follower initialized: {self.follower.get_display_name()}")
                    logging.info(f"Control type: {self.follower.get_control_type()}")
                    logging.info(f"Available fields: {self.follower.get_available_fields()}")

                    # Validate follower configuration
                    if not self.follower.validate_current_mode():
                        raise RuntimeError(
                            "Follower mode validation failed; Offboard start refused"
                        )

                    result["steps"].append(f"Follower created: {self.follower.get_display_name()}")

                except Exception as e:
                    error_msg = f"Failed to create follower: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                self._require_follow_start_readiness(
                    result,
                    stage="before_offboard",
                )

                # PX4InterfaceManager owns the required default-setpoint priming
                # and mode transition as one fail-closed protocol operation.
                try:
                    offboard_result = await self.px4_interface.start_offboard_mode()
                    if not isinstance(offboard_result, dict):
                        raise RuntimeError("PX4 Offboard start returned no action outcome")
                    result["offboard_action"] = dict(offboard_result)
                    offboard_cleanup_required = bool(
                        offboard_result.get("executed") is True
                        and not offboard_result.get("degraded")
                    )
                    if offboard_result.get("steps"):
                        result["steps"].extend(offboard_result["steps"])
                    if offboard_result.get("errors"):
                        raise RuntimeError("; ".join(offboard_result["errors"]))
                    if offboard_result.get("executed") is True:
                        result["steps"].append(
                            "MAVSDK Offboard start command acknowledged"
                        )
                    elif offboard_result.get("simulated") is True:
                        result["steps"].append(
                            "Offboard start simulated; circuit breaker sent no PX4 action"
                        )
                        raise RuntimeError(
                            "Circuit-breaker simulation cannot activate a Follow session"
                        )
                    else:
                        raise RuntimeError(
                            "PX4 Offboard start did not execute: "
                            f"{offboard_result.get('reason', 'unknown')}"
                        )
                    if not self.px4_interface.get_connection_status().get("connected"):
                        raise RuntimeError(
                            "PX4 connection was lost during Offboard startup"
                        )
                    self._require_follow_start_readiness(
                        result,
                        stage="after_offboard",
                    )
                except Exception as e:
                    error_msg = f"Failed to start offboard mode: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                # Create the application-level MAVSDK setter owner. MAVSDK itself
                # independently retransmits the latest setpoint for PX4's wire
                # proof-of-life; follower updates submit CommandIntent snapshots.
                try:
                    self.offboard_commander = OffboardCommander(
                        self.px4_interface,
                        self.follower.follower.setpoint_handler,
                        on_failure_threshold=self._schedule_offboard_commander_failure,
                        on_publish_result=self._record_offboard_publish_result,
                    )
                    self._assert_setpoint_handler_ownership(require_commander=True)

                    commander_started = await self.offboard_commander.start()
                    if commander_started:
                        result["steps"].append("Offboard commander started")
                        logging.info(
                            "OffboardCommander started for %s",
                            self.follower.get_display_name(),
                        )
                    else:
                        error_msg = "OffboardCommander configuration validation failed"
                        logging.error(error_msg)
                        result["errors"].append(error_msg)
                        raise RuntimeError(error_msg)

                    if not self.px4_interface.get_connection_status().get("connected"):
                        raise RuntimeError(
                            "PX4 connection was lost before Follow activation"
                        )

                except Exception as e:
                    error_msg = f"Failed to start Offboard commander: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                # Mark as active
                self.following_active = True
                self.last_offboard_commander_failure = None

                # Log final status
                logging.info("Follow mode activation completed successfully!")
                if hasattr(self.follower, 'get_status_report'):
                    logging.debug(self.follower.get_status_report())

            except asyncio.CancelledError:
                logging.warning("Follow mode activation canceled; cleaning partial state")
                await self._cleanup_failed_follow_start(
                    result,
                    offboard_cleanup_required=offboard_cleanup_required,
                )
                raise
            except Exception as e:
                error_msg = f"Failed to connect/start offboard mode: {e}"
                logging.error(error_msg)
                result["errors"].append(error_msg)
                await self._cleanup_failed_follow_start(
                    result,
                    offboard_cleanup_required=offboard_cleanup_required,
                )

        return result

    async def _cleanup_failed_follow_start(
        self,
        result: Dict[str, Any],
        *,
        offboard_cleanup_required: bool,
    ) -> None:
        """Independently unwind every partial follow-start component."""
        commander = getattr(self, "offboard_commander", None)
        if commander is not None:
            try:
                stopped = await commander.stop(publish_final=False)
                if not stopped:
                    raise RuntimeError(
                        "publication owner remained active after cancellation deadline"
                    )
                result["steps"].append("Partial Offboard commander stopped")
                if self.offboard_commander is commander:
                    self.offboard_commander = None
            except Exception as exc:
                error = f"Partial Offboard commander cleanup failed: {exc}"
                logging.error(error)
                result["errors"].append(error)

        sender = getattr(self, "setpoint_sender", None)
        if sender is not None:
            try:
                sender.stop()
                result["steps"].append("Partial legacy setpoint sender stopped")
            except Exception as exc:
                error = f"Partial setpoint sender cleanup failed: {exc}"
                logging.error(error)
                result["errors"].append(error)
            finally:
                self.setpoint_sender = None

        if offboard_cleanup_required:
            try:
                stop_outcome = await self.px4_interface.stop_offboard_mode()
                if isinstance(stop_outcome, dict) and stop_outcome.get("errors"):
                    raise RuntimeError("; ".join(stop_outcome["errors"]))
                result["steps"].append("Partial Offboard start cleaned up")
            except Exception as exc:
                error = f"Partial Offboard cleanup failed: {exc}"
                logging.error(error)
                result["errors"].append(error)

        self.follower = None
        telemetry_handler = getattr(self, "telemetry_handler", None)
        if telemetry_handler is not None:
            telemetry_handler.follower = None
        self.following_active = False
        self._reset_following_execution_state()

    async def _disconnect_px4_internal(
        self,
        *,
        commander_publish_final: bool = True,
        attempt_offboard_stop: bool = True,
    ) -> Dict[str, any]:
        """
        Internal method for PX4 disconnection without acquiring lock.
        Used by connect_px4 for auto-stop functionality to avoid deadlock.

        Returns:
            Dict with status information
        """
        result = {"steps": [], "errors": []}

        has_runtime_components = any(
            getattr(self, name, None) is not None
            for name in ("offboard_commander", "setpoint_sender", "follower")
        )
        if not self.following_active and not has_runtime_components:
            result["steps"].append("Follow mode is not active.")
            self._reset_following_execution_state()
            return result

        try:
            logging.info("Deactivating Follow Mode...")
            preview_session = self._is_command_preview_session()

            # Stop Offboard commander first while Offboard is still active so
            # it can publish a best-effort final default setpoint.
            if hasattr(self, 'offboard_commander') and self.offboard_commander:
                try:
                    commander_status = self.offboard_commander.get_status()
                    logging.debug(f"OffboardCommander status before stop: {commander_status}")

                    commander = self.offboard_commander
                    stopped = await commander.stop(
                        publish_final=commander_publish_final
                    )
                    if not stopped:
                        raise RuntimeError(
                            "publication owner remained active after cancellation deadline"
                        )
                    result["steps"].append("Offboard commander stopped")
                    logging.info("OffboardCommander stopped successfully")
                    if self.offboard_commander is commander:
                        self.offboard_commander = None
                except Exception as e:
                    error_msg = f"Error stopping Offboard commander: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)

            # Stop legacy setpoint sender monitor if present.
            if hasattr(self, 'setpoint_sender') and self.setpoint_sender:
                try:
                    # Get status before stopping
                    sender_status = self.setpoint_sender.get_status()
                    logging.debug(f"SetpointSender status before stop: {sender_status}")

                    self.setpoint_sender.stop()
                    result["steps"].append("Enhanced setpoint sender stopped")
                    logging.info("SetpointSender stopped successfully")
                except Exception as e:
                    error_msg = f"Error stopping setpoint sender: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                finally:
                    self.setpoint_sender = None

            # Do not attempt a final command when MAVSDK has already confirmed
            # the link is gone. PX4 owns the configured Offboard-loss failsafe.
            if preview_session:
                result["steps"].append(
                    "Command preview stopped locally; no PX4 Offboard stop sent"
                )
            elif attempt_offboard_stop:
                try:
                    offboard_stop = await self.px4_interface.stop_offboard_mode()
                    if isinstance(offboard_stop, dict):
                        result["offboard_stop_action"] = dict(offboard_stop)
                        if offboard_stop.get("errors"):
                            raise RuntimeError("; ".join(offboard_stop["errors"]))
                        if offboard_stop.get("executed") is True:
                            result["steps"].append("Offboard mode stopped on PX4")
                        elif offboard_stop.get("simulated") is True:
                            result["steps"].append(
                                "Offboard stop simulated; circuit breaker sent no PX4 action"
                            )
                        else:
                            raise RuntimeError(
                                "PX4 Offboard stop did not execute: "
                                f"{offboard_stop.get('reason', 'unknown')}"
                            )
                    else:
                        result["steps"].append("Offboard mode stop completed")
                except Exception as e:
                    error_msg = f"Failed to stop offboard mode: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
            else:
                result["steps"].append(
                    "Offboard stop intentionally not sent; local follow cleanup only"
                )
                quiesce_sender = getattr(
                    self.px4_interface,
                    "quiesce_offboard_sender",
                    None,
                )
                if callable(quiesce_sender):
                    try:
                        quiesce = await quiesce_sender(
                            reason="local_follow_cleanup",
                        )
                        result["sender_quiesce"] = dict(quiesce)
                        result["steps"].append(
                            "MAVSDK local sender state: "
                            f"{quiesce.get('state_after', 'unknown')}"
                        )
                        if quiesce.get("attempted") and not quiesce.get(
                            "local_sender_quiesced"
                        ):
                            result["errors"].append(
                                quiesce.get("error")
                                or "MAVSDK local sender quiesce was not confirmed"
                            )
                    except Exception as exc:
                        error_msg = f"MAVSDK local sender quiesce failed: {exc}"
                        logging.error(error_msg)
                        result["errors"].append(error_msg)

            # Reset follower
            if hasattr(self, 'follower') and self.follower:
                try:
                    # Log final follower status
                    if hasattr(self.follower, 'get_status_report'):
                        logging.debug("Final follower status:")
                        logging.debug(self.follower.get_status_report())

                    self.follower = None
                    self.telemetry_handler.follower = None
                    result["steps"].append("Follower instance cleaned up")
                except Exception as e:
                    logging.warning(f"Error during follower cleanup: {e}")

            # Mark as inactive
            self.following_active = False
            self._reset_following_execution_state()

            logging.info("Follow mode deactivated successfully!")

        except Exception as e:
            error_msg = f"Error during PX4 disconnection: {e}"
            logging.error(error_msg)
            result["errors"].append(error_msg)

        # Keep the next start fail-closed even if one cleanup step raised.
        self._reset_following_execution_state()

        return result

    async def disconnect_px4(self) -> Dict[str, any]:
        """
        Enhanced PX4 disconnection with proper cleanup of unified protocol components.
        Thread-safe wrapper that acquires lock before calling internal disconnect.

        Returns:
            Dict with status information
        """
        return await self._run_on_flight_event_loop(
            self._disconnect_px4_on_flight_loop
        )

    async def _disconnect_px4_on_flight_loop(
        self,
        *,
        commander_publish_final: bool = True,
        attempt_offboard_stop: bool = True,
        cancel_pending_start: bool = True,
    ) -> Dict[str, Any]:
        """Abort pending startup, then stop one follow session on its owner loop."""
        start_task = getattr(self, "_follow_start_task", None)
        current_task = asyncio.current_task()
        if (
            cancel_pending_start
            and start_task is not None
            and not start_task.done()
            and start_task is not current_task
        ):
            logging.warning("Canceling pending Follow activation before disconnect")
            start_task.cancel()
            done, _ = await asyncio.wait(
                {start_task},
                timeout=self.FOLLOW_START_CANCEL_TIMEOUT_S,
            )
            if start_task not in done:
                error = (
                    "Pending Follow activation ignored cancellation for "
                    f"{self.FOLLOW_START_CANCEL_TIMEOUT_S:.1f} s"
                )
                logging.error(error)
                return {
                    "steps": [],
                    "errors": [error],
                    "cleanup_failed": True,
                }
            try:
                start_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logging.warning("Pending Follow activation stopped with error: %s", exc)

        # Use one owner-loop lock to prevent lifecycle state races. A damaged or
        # test-constructed controller still gets a local fail-closed barrier.
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            follower_lock = asyncio.Lock()
            self._follower_state_lock = follower_lock
        async with follower_lock:
            return await self._disconnect_px4_internal(
                commander_publish_final=commander_publish_final,
                attempt_offboard_stop=attempt_offboard_stop,
            )

    async def _handle_offboard_commander_failure(self, status: Dict[str, Any]):
        """Route sustained publication failure cleanup to the flight owner loop."""
        return await self._run_on_flight_event_loop(
            lambda: self._handle_offboard_commander_failure_on_flight_loop(status)
        )

    async def _handle_offboard_commander_failure_on_flight_loop(
        self,
        status: Dict[str, Any],
    ):
        """
        Stop local following when OffboardCommander reports sustained send failures.

        This is a local fail-closed policy. It does not claim PX4 accepted an
        abort command; PX4-in-loop evidence remains tracked under PXE-0018.
        """
        self.last_offboard_commander_failure = dict(status or {})
        if not self.following_active:
            return

        logging.error(
            "OffboardCommander failure threshold reached; stopping follow mode: %s",
            self.last_offboard_commander_failure.get("failure_policy_reason"),
        )

        try:
            async with self._follower_state_lock:
                if not self.following_active:
                    return
                disconnect_result = await self._disconnect_px4_internal(
                    commander_publish_final=False
                )
                self.last_offboard_commander_failure["disconnect_result"] = disconnect_result
        except Exception as exc:
            logging.error(
                "Error handling OffboardCommander failure policy: %s",
                exc,
            )
            self.last_offboard_commander_failure["handler_error"] = str(exc)
            self.following_active = False

    def _schedule_offboard_commander_failure(self, status: Dict[str, Any]) -> None:
        """Schedule commander failure cleanup from the commander task or any thread."""
        def fail_closed(exc) -> None:
            self.last_offboard_commander_failure = dict(status or {})
            if exc is not None:
                self.last_offboard_commander_failure["schedule_error"] = str(exc)
            self.following_active = False

        self._schedule_on_flight_event_loop(
            lambda: self._handle_offboard_commander_failure(status),
            failure_message=(
                "OffboardCommander failure detected but the flight event loop is "
                "unavailable; clearing follow mode state synchronously"
            ),
            fail_closed=fail_closed,
        )

    async def switch_tracker_type(self, new_tracker_type: str) -> Dict[str, Any]:
        """
        Switch to a different classic tracker type dynamically.

        This method provides a clean, user-friendly way to change trackers from the UI
        without editing configuration files. It handles all necessary cleanup and
        initialization to ensure a smooth transition.

        Args:
            new_tracker_type (str): The tracker type name (e.g., "CSRTTracker", "DlibTracker")

        Returns:
            Dict[str, Any]: Result dictionary with keys:
                - success (bool): Whether the switch was successful
                - old_tracker (str): Previous tracker type
                - new_tracker (str): New tracker type
                - was_tracking (bool): Whether tracking was active before switch
                - message (str): Human-readable status message
                - requires_restart (bool): Whether user needs to restart tracking manually
                - error (str, optional): Error message if switch failed

        Example:
            >>> result = await app_controller.switch_tracker_type("DlibTracker")
            >>> if result['success']:
            ...     print(f"Switched to {result['new_tracker']}")
        """
        return await self._run_on_flight_event_loop(
            lambda: self._switch_tracker_type_on_flight_loop(new_tracker_type)
        )

    async def _switch_tracker_type_on_flight_loop(
        self,
        new_tracker_type: str,
    ) -> Dict[str, Any]:
        """Replace a tracker while the lifecycle lock remains loop-owned."""
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None:
            return {
                "success": False,
                "error": "Follower state barrier is unavailable; tracker switch refused",
                "old_tracker": getattr(self, "current_tracker_type", "Unknown"),
                "new_tracker": new_tracker_type,
            }
        async with follower_lock:
            return self._switch_tracker_type_with_follower_barrier(new_tracker_type)

    def _switch_tracker_type_with_follower_barrier(
        self,
        new_tracker_type: str,
    ) -> Dict[str, Any]:
        """Replace a tracker while caller owns the follower lifecycle barrier."""
        follower_lock = getattr(self, "_follower_state_lock", None)
        if follower_lock is None or not follower_lock.locked():
            raise RuntimeError("Follower state barrier must be held for tracker replacement")
        state_lock = getattr(self, "_tracker_model_state_lock", None)
        if state_lock is None:
            return {
                "success": False,
                "error": "Tracker/model state barrier is unavailable; switch refused",
                "old_tracker": getattr(self, "current_tracker_type", "Unknown"),
                "new_tracker": new_tracker_type,
            }
        with state_lock:
            return self._switch_tracker_type_locked(new_tracker_type)

    def _switch_tracker_type_locked(self, new_tracker_type: str) -> Dict[str, Any]:
        """Perform tracker replacement while both lifecycle barriers are held."""
        from classes.schema_manager import get_schema_manager

        try:
            schema_manager = get_schema_manager()

            # 1. Resolve/validate the tracker identifier accepted by API/UI.
            requested_tracker_type = new_tracker_type
            (
                canonical_tracker_type,
                tracker_info,
                error_msg,
            ) = schema_manager.resolve_tracker_for_ui(new_tracker_type)
            if not canonical_tracker_type or not tracker_info:
                logging.warning(f"Invalid tracker selection: {new_tracker_type} - {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type
                }
            new_tracker_type = canonical_tracker_type

            # 2. Get factory key for creating new tracker
            factory_key = tracker_info.get('ui_metadata', {}).get('factory_key')

            if not factory_key:
                error_msg = f"Tracker {new_tracker_type} has no factory key"
                logging.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requested_tracker": requested_tracker_type,
                }

            # 3. A live PX4 session must keep one validated tracker implementation.
            # Local command preview may switch while its recorder is held at defaults.
            if self.following_active and not self._is_command_preview_session():
                error_msg = (
                    "Cannot replace the tracker implementation during live PX4 "
                    "following. Select a new target with the current tracker or stop "
                    "following first."
                )
                logging.warning(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requested_tracker": requested_tracker_type,
                    "requires_disconnect": True
                }

            transition = self._prepare_following_target_transition(
                "command_preview_tracker_switch"
            )
            if not transition["prepared"]:
                return {
                    "success": False,
                    "error": (
                        "Tracker switch refused because the active follower could "
                        "not enter a fail-closed hold."
                    ),
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requested_tracker": requested_tracker_type,
                    "target_transition": transition,
                }

            # 4. Record current state
            was_tracking = self.tracking_started
            old_tracker_type = self.current_tracker_type
            old_tracker_class = self.tracker.__class__.__name__ if self.tracker else "None"

            logging.info(f"TRACKER SWITCH: Changing from {old_tracker_type} → {new_tracker_type}")
            logging.info(f"  Previous tracker: {old_tracker_class}")
            logging.info(f"  Tracking was active: {was_tracking}")

            # 5. Stop tracking and cleanup current tracker
            if was_tracking:
                logging.info("  Stopping active tracking...")
                self.cancel_activities()

            # 6. Destroy old tracker instance
            if self.tracker:
                logging.info(f"  Cleaning up old tracker: {self.tracker.__class__.__name__}")
                try:
                    if hasattr(self.tracker, 'stop_tracking'):
                        self.tracker.stop_tracking()
                    if hasattr(self.tracker, 'reset'):
                        self.tracker.reset()
                except Exception as e:
                    logging.warning(f"  Error during tracker cleanup: {e}")
                finally:
                    self.tracker = None

            # 7. Create new tracker instance
            try:
                logging.info(f"  Creating new tracker: {factory_key}")
                self.tracker = create_tracker(
                    factory_key,
                    self.video_handler,
                    self.detector,
                    self
                )
                self._start_external_tracker_monitoring(
                    self.tracker,
                    context="tracker switch",
                )

                # 8. Update application state
                self.current_tracker_type = new_tracker_type
                Parameters.DEFAULT_TRACKING_ALGORITHM = factory_key

                logging.info(f"✅ TRACKER SWITCH SUCCESSFUL")
                logging.info(f"  New tracker: {self.tracker.__class__.__name__}")
                logging.info(f"  Factory key: {factory_key}")

                # 9. Determine user action message
                is_external_tracker = bool(
                    getattr(self.tracker, "is_external_tracker", False)
                )
                if is_external_tracker:
                    message = (
                        f"Switched to "
                        f"{tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type)}. "
                        "External provider monitoring is active."
                    )
                    requires_restart = False
                elif was_tracking:
                    message = f"Switched to {tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type)}. Please select a new ROI to resume tracking."
                    requires_restart = True
                else:
                    message = f"Switched to {tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type)}. Ready for tracking."
                    requires_restart = False

                result = {
                    "success": True,
                    "old_tracker": old_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requested_tracker": requested_tracker_type,
                    "new_tracker_display_name": tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type),
                    "factory_key": factory_key,
                    "was_tracking": was_tracking,
                    "requires_restart": requires_restart,
                    "message": message
                }
                if transition["command_hold_applied"]:
                    result["target_transition"] = transition
                return result

            except Exception as e:
                error_msg = f"Failed to create new tracker: {str(e)}"
                logging.error(f"❌ TRACKER SWITCH FAILED: {error_msg}")

                failed_tracker = self.tracker
                if failed_tracker is not None:
                    try:
                        stop_tracking = getattr(
                            failed_tracker,
                            "stop_tracking",
                            None,
                        )
                        if callable(stop_tracking):
                            stop_tracking()
                    except Exception as cleanup_error:
                        logging.warning(
                            "  Failed tracker cleanup was incomplete: %s",
                            cleanup_error,
                        )
                    finally:
                        self.tracker = None

                # Try to restore old tracker if possible
                logging.warning("  Attempting to restore previous tracker...")
                restored_tracker = None
                rollback_restored = False
                rollback_error = None
                try:
                    _old_canonical, old_tracker_info, _old_error = (
                        schema_manager.resolve_tracker_for_ui(old_tracker_type)
                    )
                    old_factory_key = (
                        old_tracker_info or {}
                    ).get('ui_metadata', {}).get('factory_key')
                    if old_factory_key:
                        restored_tracker = create_tracker(
                            old_factory_key,
                            self.video_handler,
                            self.detector,
                            self
                        )
                        self._start_external_tracker_monitoring(
                            restored_tracker,
                            context="tracker switch rollback",
                        )
                        self.tracker = restored_tracker
                        rollback_restored = True
                        logging.info("  ✓ Previous tracker restored")
                    else:
                        rollback_error = (
                            f"Previous tracker {old_tracker_type!r} has no factory key"
                        )
                except Exception as restore_error:
                    rollback_error = str(restore_error)
                    if restored_tracker is not None:
                        try:
                            stop_tracking = getattr(
                                restored_tracker,
                                "stop_tracking",
                                None,
                            )
                            if callable(stop_tracking):
                                stop_tracking()
                        except Exception as cleanup_error:
                            logging.warning(
                                "  Rollback tracker cleanup was incomplete: %s",
                                cleanup_error,
                            )
                    self.tracker = None
                    logging.error(f"  ✗ Failed to restore previous tracker: {restore_error}")

                result = {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": old_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requested_tracker": requested_tracker_type,
                    "was_tracking": was_tracking,
                    "rollback_restored": rollback_restored,
                    "active_tracker": (
                        self.tracker.__class__.__name__
                        if self.tracker is not None
                        else None
                    ),
                }
                if rollback_error is not None:
                    result["rollback_error"] = rollback_error
                return result

        except Exception as e:
            error_msg = f"Unexpected error during tracker switch: {str(e)}"
            logging.error(f"❌ TRACKER SWITCH EXCEPTION: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "old_tracker": getattr(self, 'current_tracker_type', 'Unknown'),
                "new_tracker": new_tracker_type
            }

    async def follow_target(self):
        """
        Enhanced target following with flexible tracker schema and proper async command dispatch.
        """
        self._capture_app_event_loop()
        # DEBUG: Log when follow_target is called
        logging.debug(f"Follow target called - tracking_started={self.tracking_started}, following_active={self.following_active}")

        # For always-reporting trackers, only check following_active (not tracking_started)
        is_always_reporting = self._is_always_reporting_tracker()
        if is_always_reporting:
            if not self.following_active:
                logging.debug(f"Follow target early exit (always-reporting): following_active={self.following_active}")
                return False
            else:
                logging.debug(f"Always-reporting tracker: Proceeding with follow_target (tracking_started not required)")
        else:
            # Classic trackers require both tracking_started AND following_active
            if not (self.tracking_started and self.following_active):
                logging.debug(f"Follow target early exit (classic): tracking_started={self.tracking_started}, following_active={self.following_active}")
                return False
            
        try:
            # Get structured tracker output
            tracker_output = self.get_tracker_output()
            if not tracker_output:
                logging.warning("No tracker output available for following.")
                return False

            return await self._follow_tracker_output(tracker_output)
            
        except Exception as e:
            logging.error(f"Error in follow_target: {e}")
            return False

    async def _follow_tracker_output(self, tracker_output: TrackerOutput) -> bool:
        """Apply command freshness to a known tracker output and dispatch it."""
        if not tracker_output:
            return False
        tracker_output = self._apply_command_freshness_contract(tracker_output)
        return await self._dispatch_tracker_output_to_follower(tracker_output)

    async def inject_tracker_output_for_validation(
        self,
        tracker_output: TrackerOutput,
        *,
        source: str = "sitl_validation",
    ) -> Dict[str, Any]:
        """
        Drive a SITL/test TrackerOutput through the normal follower path.

        This hook is intentionally narrow: it refuses to dispatch when follow
        mode is not already active, then uses the same command-freshness and
        follower/commander boundary as live tracker output.
        """
        self._capture_app_event_loop()

        if not isinstance(tracker_output, TrackerOutput):
            raise TypeError("tracker_output must be a TrackerOutput instance")

        if not getattr(self, "following_active", False):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "following_not_active",
                "following_active": False,
                "injection": {
                    "source": source,
                    "tracker_id": tracker_output.tracker_id,
                    "data_type": tracker_output.data_type.value,
                    "input_tracking_active": tracker_output.tracking_active,
                },
                "command_intent": None,
                "offboard_commander": None,
                "timestamp": time.time(),
            }

        processed_output = self._apply_command_freshness_contract(tracker_output)
        accepted = await self._dispatch_tracker_output_to_follower(processed_output)
        intent = self._get_current_command_intent()
        commander = getattr(self, "offboard_commander", None)
        commander_status = (
            commander.get_status()
            if commander and hasattr(commander, "get_status")
            else None
        )
        commander_summary = self._summarize_offboard_commander_for_validation(
            commander_status
        )

        raw_data = processed_output.raw_data or {}
        metadata = processed_output.metadata or {}
        return {
            "status": "accepted" if accepted else "rejected",
            "accepted": bool(accepted),
            "reason": None if accepted else "dispatch_rejected",
            "following_active": bool(getattr(self, "following_active", False)),
            "injection": {
                "source": source,
                "tracker_id": processed_output.tracker_id,
                "data_type": processed_output.data_type.value,
                "input_tracking_active": tracker_output.tracking_active,
                "processed_tracking_active": processed_output.tracking_active,
                "processed_usable_for_following": raw_data.get(
                    "usable_for_following",
                    metadata.get("usable_for_following"),
                ),
                "processed_data_is_stale": raw_data.get(
                    "data_is_stale",
                    metadata.get("data_is_stale"),
                ),
                "freshness_reason": raw_data.get(
                    "freshness_reason",
                    metadata.get("freshness_reason"),
                ),
                "has_output": raw_data.get(
                    "has_output",
                    metadata.get("has_output"),
                ),
            },
            "command_intent": dataclasses.asdict(intent) if intent else None,
            "offboard_commander": commander_summary,
            "timestamp": time.time(),
        }

    @staticmethod
    def _summarize_offboard_commander_for_validation(
        commander_status: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Return the stable OffboardCommander evidence fields for SITL APIs."""
        if not isinstance(commander_status, dict):
            return None

        return {
            "exists": bool(commander_status.get("exists", True)),
            "running": commander_status.get("running"),
            "health_state": commander_status.get("health_state"),
            "command_publication_source": commander_status.get(
                "command_publication_source"
            ),
            "command_failure_threshold": commander_status.get(
                "command_failure_threshold"
            ),
            "publish_count": commander_status.get("publish_count"),
            "last_intent_fresh": commander_status.get("last_intent_fresh"),
            "failsafe_defaults_active": commander_status.get(
                "failsafe_defaults_active"
            ),
            "successful_publishes": commander_status.get("successful_publishes"),
            "failed_publishes": commander_status.get("failed_publishes"),
            "consecutive_failures": commander_status.get("consecutive_failures"),
            "rejected_intents": commander_status.get("rejected_intents"),
            "last_publish_success": commander_status.get("last_publish_success"),
            "last_publish_reason": commander_status.get("last_publish_reason"),
            "last_error": commander_status.get("last_error"),
            "failure_policy_triggered": commander_status.get(
                "failure_policy_triggered"
            ),
            "failure_policy_reason": commander_status.get("failure_policy_reason"),
            "failure_policy_trigger_count": commander_status.get(
                "failure_policy_trigger_count"
            ),
            "failure_action": commander_status.get("failure_action"),
        }

    def configure_tracker_trace_artifacts(
        self,
        *,
        tracker_command_trace_path: str | Path,
        offboard_publish_trace_path: str | Path,
        source: str = "validation_runtime",
    ) -> Dict[str, Any]:
        """
        Enable append-only tracker/offboard trace capture for validation runs.

        This only writes local JSONL artifacts. It does not start PX4, change
        follow mode, publish commands, or alter routing.
        """
        self.tracker_trace_recorder = TrackerTraceRecorder(
            tracker_command_trace_path=Path(tracker_command_trace_path),
            offboard_publish_trace_path=Path(offboard_publish_trace_path),
            source=source,
        )
        self._tracker_trace_frame_index = 0
        self._offboard_trace_sequence = 0
        return {
            "enabled": True,
            "source": source,
            "tracker_command_trace_path": str(tracker_command_trace_path),
            "offboard_publish_trace_path": str(offboard_publish_trace_path),
            "claim_boundary": (
                "Tracker trace capture writes validation artifacts only; it does "
                "not prove PX4, SITL, HIL, field, or real-aircraft behavior."
            ),
        }

    def disable_tracker_trace_artifacts(self) -> Dict[str, Any]:
        """Disable validation trace capture."""
        self.tracker_trace_recorder = None
        return {"enabled": False}

    def _record_tracker_dispatch_trace(
        self,
        *,
        tracker_output: TrackerOutput,
        command_intent: Optional[CommandIntent],
        dispatch_accepted: bool,
    ) -> None:
        """Best-effort validation trace recording for tracker dispatch."""
        recorder = getattr(self, "tracker_trace_recorder", None)
        if recorder is None:
            return

        frame_index = int(getattr(self, "_tracker_trace_frame_index", 0))
        self._tracker_trace_frame_index = frame_index + 1
        commander = getattr(self, "offboard_commander", None)
        commander_status = (
            commander.get_status()
            if commander is not None and hasattr(commander, "get_status")
            else None
        )
        frame_status = self._get_video_frame_status_for_following()
        try:
            recorder.record_tracker_command(
                frame_index=frame_index,
                tracker_output=tracker_output,
                command_intent=command_intent,
                dispatch_accepted=dispatch_accepted,
                frame_status=frame_status,
                offboard_commander=commander_status,
            )
        except Exception as exc:
            logging.error("Failed to write tracker trace artifact: %s", exc)

    def _record_offboard_publish_result(self, event: Dict[str, Any]) -> None:
        """Record evidence after the commander completes a concrete send attempt."""
        recorder = getattr(self, "tracker_trace_recorder", None)
        if recorder is None:
            return
        sequence = int(getattr(self, "_offboard_trace_sequence", 0))
        self._offboard_trace_sequence = sequence + 1
        try:
            recorder.record_offboard_publish(
                sequence=sequence,
                command_intent=event.get("command_intent"),
                publish_status=event.get("publish_status"),
            )
        except Exception as exc:
            logging.error("Failed to write Offboard publication trace: %s", exc)

    async def inject_video_stall_for_validation(
        self,
        frame_status: Optional[Dict[str, Any]] = None,
        *,
        source: str = "sitl_validation",
    ) -> Dict[str, Any]:
        """
        Drive a validation-only video-stall stimulus through the normal path.

        This hook does not stop or start a video source. It injects the same
        frame-status contract that the main loop passes to
        handle_video_frame_unavailable() when frame capture stalls.
        """
        self._capture_app_event_loop()

        normalized_frame_status = dict(frame_status or {})
        normalized_frame_status.setdefault("source", "sitl_validation")
        normalized_frame_status.setdefault("status", "unavailable")
        normalized_frame_status.setdefault("usable_for_following", False)
        normalized_frame_status.setdefault("reason", "sitl_video_stall")
        normalized_frame_status.setdefault("timestamp", time.time())

        if not getattr(self, "following_active", False):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "following_not_active",
                "following_active": False,
                "injection": {
                    "source": source,
                    "tracker_requires_video": self._tracker_requires_video_for_following(),
                    "frame_status": normalized_frame_status,
                },
                "command_intent": None,
                "offboard_commander": None,
                "timestamp": time.time(),
            }

        accepted = await self.handle_video_frame_unavailable(normalized_frame_status)
        intent = self._get_current_command_intent()
        commander = getattr(self, "offboard_commander", None)
        commander_status = (
            commander.get_status()
            if commander and hasattr(commander, "get_status")
            else None
        )

        return {
            "status": "accepted" if accepted else "rejected",
            "accepted": bool(accepted),
            "reason": None if accepted else "dispatch_rejected",
            "following_active": bool(getattr(self, "following_active", False)),
            "injection": {
                "source": source,
                "tracker_requires_video": self._tracker_requires_video_for_following(),
                "frame_status": normalized_frame_status,
            },
            "command_intent": dataclasses.asdict(intent) if intent else None,
            "offboard_commander": self._summarize_offboard_commander_for_validation(
                commander_status
            ),
            "timestamp": time.time(),
        }

    async def inject_commander_publish_failure_for_validation(
        self,
        *,
        failure_count: Optional[int] = None,
        reason: str = "sitl_commander_publish_failure",
        source: str = "sitl_validation",
        failure_mode: str = "recorded_failure",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Drive the OffboardCommander publish-failure policy for validation.

        This hook records synthetic failed publishes inside the running
        OffboardCommander without sending a MAVSDK setpoint or changing any
        external service. If the configured threshold is crossed, it then runs
        the same AppController cleanup handler used by real commander publish
        failures, including the normal Offboard stop path.
        """
        self._capture_app_event_loop()

        commander = getattr(self, "offboard_commander", None)
        commander_status_before = (
            commander.get_status()
            if commander and hasattr(commander, "get_status")
            else None
        )

        if not getattr(self, "following_active", False):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "following_not_active",
                "following_active": False,
                "injection": {
                    "source": source,
                    "failure_mode": failure_mode,
                    "requested_failure_count": failure_count,
                    "applied_failure_count": 0,
                    "failure_reason": reason,
                    "metadata": dict(metadata or {}),
                },
                "offboard_commander": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_after": None,
                "offboard_commander_failure": getattr(
                    self,
                    "last_offboard_commander_failure",
                    None,
                ),
                "disconnect_result": None,
                "timestamp": time.time(),
            }

        if commander is None or not hasattr(
            commander,
            "inject_publish_failures_for_validation",
        ):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "offboard_commander_unavailable",
                "following_active": bool(getattr(self, "following_active", False)),
                "injection": {
                    "source": source,
                    "failure_mode": failure_mode,
                    "requested_failure_count": failure_count,
                    "applied_failure_count": 0,
                    "failure_reason": reason,
                    "metadata": dict(metadata or {}),
                },
                "offboard_commander": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_after": None,
                "offboard_commander_failure": getattr(
                    self,
                    "last_offboard_commander_failure",
                    None,
                ),
                "disconnect_result": None,
                "timestamp": time.time(),
            }

        if not bool((commander_status_before or {}).get("running")):
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "offboard_commander_not_running",
                "following_active": bool(getattr(self, "following_active", False)),
                "injection": {
                    "source": source,
                    "failure_mode": failure_mode,
                    "requested_failure_count": failure_count,
                    "applied_failure_count": 0,
                    "failure_reason": reason,
                    "metadata": dict(metadata or {}),
                },
                "offboard_commander": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_after": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_failure": getattr(
                    self,
                    "last_offboard_commander_failure",
                    None,
                ),
                "disconnect_result": None,
                "timestamp": time.time(),
            }

        threshold = int(
            (commander_status_before or {}).get("command_failure_threshold")
            or getattr(commander, "command_failure_threshold", 1)
            or 1
        )
        consecutive_failures = int(
            (commander_status_before or {}).get("consecutive_failures") or 0
        )
        applied_count = (
            int(failure_count)
            if failure_count is not None
            else max(1, threshold - consecutive_failures)
        )

        injection_result = await commander.inject_publish_failures_for_validation(
            failure_count=applied_count,
            reason=reason,
            invoke_failure_callback=False,
        )
        commander_status_after = dict(
            injection_result.get("offboard_commander") or commander.get_status()
        )

        disconnect_result = None
        offboard_commander_failure = None
        if commander_status_after.get("failure_policy_triggered"):
            await self._handle_offboard_commander_failure(commander_status_after)
            offboard_commander_failure = (
                getattr(self, "last_offboard_commander_failure", {}) or {}
            )
            disconnect_result = offboard_commander_failure.get("disconnect_result")

        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": bool(getattr(self, "following_active", False)),
            "injection": {
                "source": source,
                "failure_mode": failure_mode,
                "requested_failure_count": failure_count,
                "applied_failure_count": injection_result.get(
                    "applied_failure_count",
                    applied_count,
                ),
                "failure_reason": injection_result.get("failure_reason", reason),
                "metadata": dict(metadata or {}),
            },
            "offboard_commander": self._summarize_offboard_commander_for_validation(
                commander_status_after
            ),
            "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                commander_status_before
            ),
            "offboard_commander_after": self._summarize_offboard_commander_for_validation(
                commander_status_after
            ),
            "offboard_commander_failure": offboard_commander_failure,
            "disconnect_result": disconnect_result,
            "timestamp": time.time(),
        }

    @staticmethod
    def _summarize_px4_connection_for_validation(
        connection_status: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Return stable PX4/MAVSDK command-path fields for SITL APIs."""
        if not isinstance(connection_status, dict):
            return None

        return {
            "status": connection_status.get("status"),
            "connected": connection_status.get("connected"),
            "active_mode": connection_status.get("active_mode"),
            "validation_disconnect_active": connection_status.get(
                "validation_disconnect_active"
            ),
            "disconnect_reason": connection_status.get("disconnect_reason"),
            "disconnect_source": connection_status.get("disconnect_source"),
            "disconnect_age_s": connection_status.get("disconnect_age_s"),
            "disconnect_count": connection_status.get("disconnect_count"),
            "last_error": connection_status.get("last_error"),
            "system_address": connection_status.get("system_address"),
            "configured_vehicle_link": connection_status.get(
                "configured_vehicle_link"
            ),
            "vehicle_link_owner": connection_status.get("vehicle_link_owner"),
            "mavsdk_server": connection_status.get("mavsdk_server"),
            "uses_mavlink2rest": connection_status.get("uses_mavlink2rest"),
            "telemetry_source": connection_status.get("telemetry_source"),
            "telemetry_source_requested": connection_status.get(
                "telemetry_source_requested"
            ),
            "offboard_sender": connection_status.get("offboard_sender"),
        }

    async def inject_mavsdk_disconnect_for_validation(
        self,
        *,
        failure_count: Optional[int] = None,
        reason: str = "sitl_mavsdk_disconnect",
        source: str = "sitl_validation",
        failure_mode: str = "local_mavsdk_command_disconnect",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Drive PixEagle-local MAVSDK command-path disconnect validation.

        This hook does not stop PX4, Docker, MAVLink routing, MAVSDK server, or
        network interfaces. It marks PX4InterfaceManager's local command path
        validation-disconnected, then trips the existing OffboardCommander
        failure policy and awaits normal AppController cleanup.
        """
        self._capture_app_event_loop()

        px4 = getattr(self, "px4_interface", None)
        commander = getattr(self, "offboard_commander", None)
        px4_status_before = (
            px4.get_connection_status()
            if px4 and hasattr(px4, "get_connection_status")
            else None
        )
        commander_status_before = (
            commander.get_status()
            if commander and hasattr(commander, "get_status")
            else None
        )

        def rejected(reason_code: str) -> Dict[str, Any]:
            return {
                "status": "rejected",
                "accepted": False,
                "reason": reason_code,
                "following_active": bool(getattr(self, "following_active", False)),
                "injection": {
                    "source": source,
                    "failure_mode": failure_mode,
                    "requested_failure_count": failure_count,
                    "applied_failure_count": 0,
                    "failure_reason": reason,
                    "metadata": dict(metadata or {}),
                },
                "px4_connection_before": self._summarize_px4_connection_for_validation(
                    px4_status_before
                ),
                "px4_connection_after": self._summarize_px4_connection_for_validation(
                    px4_status_before
                ),
                "offboard_commander": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                    commander_status_before
                ),
                "offboard_commander_after": None,
                "offboard_commander_failure": getattr(
                    self,
                    "last_offboard_commander_failure",
                    None,
                ),
                "disconnect_result": None,
                "timestamp": time.time(),
            }

        if not getattr(self, "following_active", False):
            return rejected("following_not_active")

        if commander is None or not hasattr(
            commander,
            "inject_publish_failures_for_validation",
        ):
            return rejected("offboard_commander_unavailable")

        if not bool((commander_status_before or {}).get("running")):
            return rejected("offboard_commander_not_running")

        if px4 is None or not hasattr(px4, "inject_mavsdk_disconnect_for_validation"):
            return rejected("px4_interface_unavailable")

        threshold = int(
            (commander_status_before or {}).get("command_failure_threshold")
            or getattr(commander, "command_failure_threshold", 1)
            or 1
        )
        consecutive_failures = int(
            (commander_status_before or {}).get("consecutive_failures") or 0
        )
        required_failures = max(1, threshold - consecutive_failures)
        requested_failure_count = failure_count
        applied_failure_count = (
            int(failure_count)
            if failure_count is not None
            else required_failures
        )
        applied_failure_count = max(applied_failure_count, required_failures)

        injection_result = await commander.inject_publish_failures_for_validation(
            failure_count=applied_failure_count,
            reason=reason,
            invoke_failure_callback=False,
        )
        commander_status_after = dict(
            injection_result.get("offboard_commander") or commander.get_status()
        )
        if not commander_status_after.get("failure_policy_triggered"):
            return rejected("offboard_commander_failure_policy_not_triggered")

        px4_status_after_injection = await px4.inject_mavsdk_disconnect_for_validation(
            reason=reason,
            source=source,
        )

        await self._handle_offboard_commander_failure(commander_status_after)
        offboard_commander_failure = (
            getattr(self, "last_offboard_commander_failure", {}) or {}
        )
        disconnect_result = offboard_commander_failure.get("disconnect_result")

        px4_status_after = (
            px4.get_connection_status()
            if px4 and hasattr(px4, "get_connection_status")
            else px4_status_after_injection
        )
        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "following_active": bool(getattr(self, "following_active", False)),
            "injection": {
                "source": source,
                "failure_mode": failure_mode,
                "requested_failure_count": requested_failure_count,
                "applied_failure_count": injection_result.get(
                    "applied_failure_count",
                    applied_failure_count,
                ),
                "failure_reason": injection_result.get("failure_reason", reason),
                "metadata": dict(metadata or {}),
            },
            "px4_connection_before": self._summarize_px4_connection_for_validation(
                px4_status_before
            ),
            "px4_connection_after": self._summarize_px4_connection_for_validation(
                px4_status_after
            ),
            "offboard_commander": self._summarize_offboard_commander_for_validation(
                commander_status_after
            ),
            "offboard_commander_before": self._summarize_offboard_commander_for_validation(
                commander_status_before
            ),
            "offboard_commander_after": self._summarize_offboard_commander_for_validation(
                commander_status_after
            ),
            "offboard_commander_failure": offboard_commander_failure,
            "disconnect_result": disconnect_result,
            "timestamp": time.time(),
        }

    async def inject_mavlink2rest_timeout_for_validation(
        self,
        *,
        failure_count: int = 1,
        reason: str = "sitl_mavlink2rest_timeout",
        force_stale: bool = True,
        timeout_window_s: float = 2.0,
        source: str = "sitl_validation",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Drive local MAVLink2REST timeout freshness state for validation.

        This hook records a timeout on PixEagle's local MavlinkDataManager
        without stopping MAVLink2REST, PX4, Docker, MAVLink routing, or network
        interfaces.
        """
        self._capture_app_event_loop()

        manager = getattr(self, "mavlink_data_manager", None)
        if manager is None or not hasattr(manager, "inject_timeout_for_validation"):
            manager_status = (
                manager.get_connection_status()
                if manager and hasattr(manager, "get_connection_status")
                else None
            )
            return {
                "status": "rejected",
                "accepted": False,
                "reason": "mavlink_data_manager_unavailable",
                "injection": {
                    "source": source,
                    "requested_failure_count": failure_count,
                    "applied_failure_count": 0,
                    "failure_reason": reason,
                    "force_stale": bool(force_stale),
                    "timeout_window_s": timeout_window_s,
                    "metadata": dict(metadata or {}),
                },
                "mavlink_telemetry": manager_status,
                "timestamp": time.time(),
            }

        injection_result = manager.inject_timeout_for_validation(
            failure_count=failure_count,
            reason=reason,
            force_stale=force_stale,
            timeout_window_s=timeout_window_s,
        )

        return {
            "status": "accepted",
            "accepted": True,
            "reason": None,
            "injection": {
                "source": source,
                "requested_failure_count": failure_count,
                "applied_failure_count": injection_result.get(
                    "applied_failure_count",
                    failure_count,
                ),
                "failure_reason": injection_result.get("failure_reason", reason),
                "force_stale": injection_result.get("force_stale", force_stale),
                "timeout_window_s": injection_result.get(
                    "timeout_window_s",
                    timeout_window_s,
                ),
                "metadata": dict(metadata or {}),
            },
            "mavlink_telemetry": injection_result.get("mavlink_telemetry"),
            "timestamp": time.time(),
        }

    async def _dispatch_tracker_output_to_follower(self, tracker_output: TrackerOutput) -> bool:
        """Route follower mutation and intent submission to the flight owner loop."""
        return await self._run_on_flight_event_loop(
            lambda: self._dispatch_tracker_output_on_flight_loop(tracker_output)
        )

    async def _dispatch_tracker_output_on_flight_loop(
        self,
        tracker_output: TrackerOutput,
    ) -> bool:
        """
        Process a vetted TrackerOutput through follower math and PX4 dispatch.

        The input may be an inactive fail-closed output produced by target-loss,
        stale-frame, or prediction-only freshness checks.
        """
        if not tracker_output:
            return False

        # Inactive output is rejected by default no matter what a legacy or
        # custom compatibility validator returns. Followers must explicitly opt
        # in when inactive output is needed to publish stop/hover/orbit commands.
        if not tracker_output.tracking_active:
            if not self._should_route_inactive_output_to_follower(tracker_output):
                logging.warning(
                    "Inactive tracker output rejected because active follower "
                    "did not opt into fail-closed command handling"
                )
                self._record_tracker_dispatch_trace(
                    tracker_output=tracker_output,
                    command_intent=None,
                    dispatch_accepted=False,
                )
                self._activate_offboard_commander_failsafe_defaults(
                    "inactive_tracker_output_rejected"
                )
                return False
            logging.warning(
                "Routing inactive tracker output to follower for "
                "fail-closed command handling"
            )
        elif not self.validate_tracker_follower_compatibility(tracker_output):
            logging.warning("Current tracker incompatible with active follower")
            self._record_tracker_dispatch_trace(
                tracker_output=tracker_output,
                command_intent=None,
                dispatch_accepted=False,
            )
            self._activate_offboard_commander_failsafe_defaults(
                "tracker_follower_incompatible"
            )
            return False

        # SYNCHRONOUS: Calculate and set commands using structured data.
        try:
            logging.debug(
                "Calling follower.follow_target() with tracker_output: "
                "data_type=%s, tracking_active=%s",
                tracker_output.data_type,
                tracker_output.tracking_active,
            )
            follow_result = self.follower.follow_target(tracker_output)
            logging.debug(f"Follower result: follow_target returned {follow_result}")

            if hasattr(self.follower, 'setpoint_handler'):
                setpoints = self.follower.setpoint_handler.get_fields()
                logging.debug(f"Setpoints after follower: {setpoints}")

            if follow_result is False:
                logging.debug("Follower follow_target returned False")
                self._activate_offboard_commander_failsafe_defaults(
                    "follower_rejected_tracker_output"
                )
                self._record_tracker_dispatch_trace(
                    tracker_output=tracker_output,
                    command_intent=self._get_current_command_intent(),
                    dispatch_accepted=False,
                )
                return False
        except Exception as e:
            logging.error(f"Error in follower.follow_target: {e}")
            self._activate_offboard_commander_failsafe_defaults(
                "follower_exception"
            )
            self._record_tracker_dispatch_trace(
                tracker_output=tracker_output,
                command_intent=self._get_current_command_intent(),
                dispatch_accepted=False,
            )
            return False

        # ASYNCHRONOUS: Hand the accepted command intent to the commander.
        # The commander owns fixed-rate MAVSDK publication; this frame/tracker
        # path must not be the PX4 heartbeat.
        intent = self._get_current_command_intent()
        accepted = self._submit_current_command_intent_to_commander()
        self._record_tracker_dispatch_trace(
            tracker_output=tracker_output,
            command_intent=intent,
            dispatch_accepted=accepted,
        )
        return accepted

    def _get_current_command_intent(self) -> Optional[CommandIntent]:
        """Return the latest command intent from the active follower manager."""
        follower = getattr(self, 'follower', None)
        if follower is None:
            return None

        getter = getattr(follower, 'get_last_command_intent', None)
        if callable(getter):
            intent = getter()
            if intent is not None:
                return intent

        concrete_follower = getattr(follower, 'follower', None)
        getter = getattr(concrete_follower, 'get_last_command_intent', None)
        if callable(getter):
            return getter()

        return None

    def _submit_current_command_intent_to_commander(self) -> bool:
        """Submit the latest follower command intent to the Offboard commander."""
        commander = getattr(self, 'offboard_commander', None)
        if commander is None:
            logging.error(
                "OffboardCommander unavailable while following is active; "
                "refusing frame-loop PX4 dispatch"
            )
            return False

        intent = self._get_current_command_intent()
        if intent is None:
            logging.error(
                "Follower reported success but no CommandIntent was available "
                "for OffboardCommander publication"
            )
            self._activate_offboard_commander_failsafe_defaults(
                "follower_intent_missing"
            )
            return False

        try:
            accepted = commander.submit_intent(intent)
        except Exception as e:
            logging.error(f"OffboardCommander rejected command intent with exception: {e}")
            self._activate_offboard_commander_failsafe_defaults(
                "commander_intent_exception"
            )
            return False

        if not accepted:
            logging.error("OffboardCommander rejected command intent")
            self._activate_offboard_commander_failsafe_defaults(
                "commander_intent_rejected"
            )
            return False

        logging.debug(
            "Submitted command intent to OffboardCommander: control_type=%s reason=%s",
            intent.control_type,
            intent.reason,
        )
        return True

    def _activate_offboard_commander_failsafe_defaults(self, reason: str) -> None:
        """Invalidate any prior command immediately after a rejected update."""
        commander = getattr(self, 'offboard_commander', None)
        activate = getattr(commander, 'activate_failsafe_defaults', None)
        if not callable(activate):
            return
        try:
            activate(reason)
        except Exception as exc:
            logging.error(
                "Failed to activate Offboard commander defaults for %s: %s",
                reason,
                exc,
            )

    async def _dispatch_unusable_tracker_output(
        self,
        reason: str,
        frame_status: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Dispatch inactive fail-closed tracker output for failed update paths."""
        tracker_output = self._create_unusable_tracker_output(
            reason=reason,
            frame_status=frame_status,
        )
        return await self._dispatch_tracker_output_to_follower(tracker_output)

    async def handle_video_frame_unavailable(
        self,
        frame_status: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Handle a hard video stall while the main frame loop is still alive.

        Vision-based trackers cannot produce command-fresh target data without a
        fresh frame. External trackers that explicitly do not require video, such
        as gimbal providers, may still update from their own input contract.
        """
        self._capture_app_event_loop()

        if not self._tracker_requires_video_for_following():
            logging.warning(
                "Video frame unavailable, but active tracker does not require "
                "video; continuing through tracker freshness contract"
            )
            return await self.follow_target() if self.following_active else False

        classic_tracking_active = bool(
            getattr(self, "tracking_started", False)
            and not getattr(self, "smart_mode_active", False)
            and not getattr(self.tracker, "is_external_tracker", False)
        )
        if classic_tracking_active:
            await self._handle_classic_tracking_loss(
                None,
                failure_reason="video_frame_unavailable",
                frame_status=frame_status,
            )
            return True

        if not self.following_active:
            return False

        synthetic_output = self._create_unusable_tracker_output(
            reason="video_frame_unavailable",
            frame_status=frame_status,
        )
        logging.warning(
            "Video frame unavailable while following - dispatching fail-closed "
            "tracker output"
        )
        return await self._dispatch_tracker_output_to_follower(synthetic_output)

    async def shutdown(self) -> Dict[str, Any]:
        """Run the idempotent shutdown sequence on the flight owner loop."""
        return await self._run_on_flight_event_loop(self._shutdown_once_on_flight_loop)

    async def _shutdown_once_on_flight_loop(self) -> Dict[str, Any]:
        """Share one non-cancelable shutdown task across concurrent callers."""
        shutdown_task = getattr(self, "_shutdown_task", None)
        if shutdown_task is None:
            shutdown_task = asyncio.create_task(
                self._shutdown_impl(),
                name="pixeagle-app-shutdown",
            )
            self._shutdown_task = shutdown_task
        return await asyncio.shield(shutdown_task)

    async def _shutdown_impl(self) -> Dict[str, Any]:
        """Stop flight-affecting work first, then release supporting resources."""
        result = {"steps": [], "errors": []}
        self.shutdown_flag = True
        logging.info("Starting application shutdown...")

        try:
            disconnect_result = await self._disconnect_px4_on_flight_loop(
                commander_publish_final=True,
                attempt_offboard_stop=True,
                cancel_pending_start=True,
            )
            result["steps"].extend(disconnect_result.get("steps", []))
            result["errors"].extend(disconnect_result.get("errors", []))
        except Exception as exc:
            error = f"Error during PX4 disconnection: {exc}"
            logging.error(error)
            result["errors"].append(error)

        # Independently clear any component left by an interrupted disconnect.
        commander = getattr(self, "offboard_commander", None)
        if commander is not None:
            try:
                await commander.stop(publish_final=False)
                result["steps"].append("Residual Offboard commander stopped")
            except Exception as exc:
                error = f"OffboardCommander stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)
            finally:
                self.offboard_commander = None

        sender = getattr(self, "setpoint_sender", None)
        if sender is not None:
            try:
                sender.stop()
                join = getattr(sender, "join", None)
                if callable(join):
                    join(timeout=3.0)
                result["steps"].append("Residual setpoint sender stopped")
            except Exception as exc:
                error = f"SetpointSender stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)
            finally:
                self.setpoint_sender = None

        self.follower = None
        telemetry_handler = getattr(self, "telemetry_handler", None)
        if telemetry_handler is not None:
            telemetry_handler.follower = None
        self.following_active = False

        # Process shutdown must join MAVSDK monitor and telemetry tasks before
        # video, streaming, or API resources disappear.
        px4_interface = getattr(self, "px4_interface", None)
        if px4_interface is not None:
            try:
                await px4_interface.stop()
                result["steps"].append("PX4 interface tasks stopped")
            except Exception as exc:
                error = f"PX4 interface stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        if (
            Parameters.MAVLINK_ENABLED
            and getattr(self, "mavlink_data_manager", None) is not None
        ):
            try:
                self.mavlink_data_manager.stop_polling()
                result["steps"].append("MAVLink data manager stopped")
            except Exception as exc:
                error = f"MAVLink stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        video_handler = getattr(self, "video_handler", None)
        if video_handler is not None:
            try:
                video_handler.release()
                result["steps"].append("Video handler released")
            except Exception as exc:
                error = f"Video handler release error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        gstreamer_handler = getattr(self, "gstreamer_handler", None)
        if gstreamer_handler is not None:
            try:
                if gstreamer_handler.release():
                    result["steps"].append("GStreamer output released")
                else:
                    status = gstreamer_handler.encoder_status
                    error = (
                        "GStreamer output cleanup incomplete: "
                        f"{status.get('last_error') or 'unknown_error'}"
                    )
                    logging.error(error)
                    result["errors"].append(error)
            except Exception as exc:
                error = f"GStreamer output release error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        recording_manager = getattr(self, "recording_manager", None)
        if recording_manager is not None:
            try:
                recording_manager.release()
                result["steps"].append("Recording manager released")
            except Exception as exc:
                error = f"Recording stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        storage_manager = getattr(self, "storage_manager", None)
        if storage_manager is not None:
            try:
                storage_manager.stop_monitoring()
                result["steps"].append("Storage monitor stopped")
            except Exception as exc:
                error = f"Storage monitor stop error: {exc}"
                logging.error(error)
                result["errors"].append(error)

        summary_stop_event = getattr(self, "_summary_stop_event", None)
        summary_thread = getattr(self, "_summary_thread", None)
        if summary_stop_event is not None:
            summary_stop_event.set()
        if summary_thread is not None and summary_thread.is_alive():
            summary_thread.join(timeout=1.0)
            if summary_thread.is_alive():
                result["errors"].append(
                    "System summary worker did not stop within 1.0 seconds"
                )
            else:
                result["steps"].append("System summary worker stopped")

        result["steps"].append("Shutdown complete")
        logging.info("Application shutdown completed")
        return result

    # ==================== Enhanced Tracker Schema Methods ====================
    
    def get_tracker_output(self) -> Optional[TrackerOutput]:
        """
        Gets structured output from the current active tracker.
        
        Returns:
            Optional[TrackerOutput]: Structured tracker data or None if unavailable
        """
        try:
            # Determine which tracker is active
            if self.smart_mode_active and self.smart_tracker:
                # Smart tracker is active
                if hasattr(self.smart_tracker, 'get_output'):
                    tracker_output = self.smart_tracker.get_output()
                    # Log status periodically with minimal, informative output
                    if tracker_output and tracker_output.tracking_active and (time.time() % 10 < 0.1):
                        target_info = f"ID:{tracker_output.target_id}" if tracker_output.target_id else "None"
                        logging.info(f"SMART TRACKER: {tracker_output.data_type.value} | Target: {target_info}")
                    return tracker_output
                else:
                    logging.warning("Smart tracker doesn't have get_output method")
                    return None
                    
            elif self.tracker:
                # Check if this is an external tracker that doesn't need manual start
                is_external_tracker = getattr(self.tracker, 'is_external_tracker', False)
                tracker_class = self.tracker.__class__.__name__

                logging.debug(f"AppController.get_tracker_output() - tracker: {tracker_class}, is_external: {is_external_tracker}, tracking_started: {self.tracking_started}")

                # For external trackers, always try to get output regardless of tracking_started
                # For classic trackers, require tracking_started to be True
                if is_external_tracker or self.tracking_started:
                    if hasattr(self.tracker, 'get_output'):
                        tracker_output = self.tracker.get_output()
                        # Log status periodically with minimal, informative output
                        if tracker_output and tracker_output.tracking_active and (time.time() % 10 < 0.1):
                            tracker_name = self.tracker.__class__.__name__.replace("Tracker", "")
                            if is_external_tracker:
                                # Enhanced logging for external trackers
                                status_info = "MONITORING" if hasattr(self.tracker, 'monitoring_active') and self.tracker.monitoring_active else "STANDBY"
                                logging.info(f"EXTERNAL TRACKER ({tracker_name}): {tracker_output.data_type.value} | Status: {status_info}")
                            else:
                                # Classic tracker logging
                                conf_info = f"Conf:{tracker_output.confidence:.2f}" if tracker_output.confidence else "NoConf"
                                logging.info(f"CLASSIC TRACKER ({tracker_name}): {tracker_output.data_type.value} | {conf_info}")
                        return tracker_output
                    else:
                        # Fallback for legacy trackers
                        if not is_external_tracker:
                            logging.debug("Using legacy tracker compatibility mode")
                            return self._create_legacy_tracker_output()
                        return None
                else:
                    # Classic tracker not started - log this only occasionally
                    if time.time() % 30 < 0.1:  # Every 30 seconds
                        logging.info("CLASSIC TRACKER: Waiting for manual tracking to start")
                    return None
            else:
                # No tracker available - log this only occasionally
                if time.time() % 30 < 0.1:  # Every 30 seconds
                    logging.info("NO TRACKER AVAILABLE: Tracker not initialized")
                return None
                
        except Exception as e:
            logging.error(f"Error getting tracker output: {e}")
            return None
    
    def get_tracker_status_debug(self) -> str:
        """
        Returns a comprehensive debug string about the current tracker state.
        
        Returns:
            str: Debug information about tracker states
        """
        status_parts = []
        status_parts.append(f"tracking_started: {self.tracking_started}")
        status_parts.append(f"smart_mode_active: {self.smart_mode_active}")
        status_parts.append(f"tracker: {self.tracker.__class__.__name__ if self.tracker else None}")
        status_parts.append(f"smart_tracker: {'Active' if self.smart_tracker else 'None'}")
        
        if self.tracker and hasattr(self.tracker, 'tracking_started'):
            status_parts.append(f"tracker.tracking_started: {self.tracker.tracking_started}")
        
        if self.smart_tracker and hasattr(self.smart_tracker, 'selected_object_id'):
            status_parts.append(f"smart_tracker.selected_object_id: {self.smart_tracker.selected_object_id}")
            
        return " | ".join(status_parts)
    
    def _create_legacy_tracker_output(self) -> Optional[TrackerOutput]:
        """
        Creates TrackerOutput from legacy tracker for backwards compatibility.
        
        Returns:
            Optional[TrackerOutput]: Legacy-compatible tracker output
        """
        try:
            if not (hasattr(self.tracker, 'normalized_center') and 
                   hasattr(self.tracker, 'normalized_bbox')):
                logging.debug("Legacy tracker missing required attributes (normalized_center or normalized_bbox)")
                return None
            
            # Debug the values being used
            normalized_center = self.tracker.normalized_center
            normalized_bbox = self.tracker.normalized_bbox
            bbox = getattr(self.tracker, 'bbox', None)
            confidence = getattr(self.tracker, 'confidence', 1.0)
            
            logging.debug(f"Legacy tracker output: center={normalized_center}, bbox={bbox}, confidence={confidence}")
            
            if normalized_center is None:
                logging.warning("Legacy tracker has None normalized_center - follower will fail")
            
            return TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=self.tracking_started,
                tracker_id="legacy_tracker",
                position_2d=normalized_center,
                bbox=bbox,
                normalized_bbox=normalized_bbox,
                confidence=confidence,
                metadata={"legacy_mode": True}
            )
            
        except Exception as e:
            logging.error(f"Error creating legacy tracker output: {e}")
            return None
    
    def validate_tracker_follower_compatibility(self, tracker_output: TrackerOutput) -> bool:
        """
        Validates compatibility between current tracker and follower.
        
        Args:
            tracker_output (TrackerOutput): Tracker output to validate
            
        Returns:
            bool: True if compatible, False otherwise
        """
        try:
            if not self.follower:
                logging.warning("No active follower to validate against")
                return False
            
            # Use follower's validation method if available
            if hasattr(self.follower, 'validate_tracker_compatibility'):
                return self.follower.validate_tracker_compatibility(tracker_output)
            else:
                # Basic compatibility check for legacy followers
                return tracker_output.position_2d is not None
                
        except Exception as e:
            logging.error(f"Error validating tracker-follower compatibility: {e}")
            return False

    def _should_route_inactive_output_to_follower(self, tracker_output: TrackerOutput) -> bool:
        """
        Return True when a follower explicitly accepts inactive tracker output.

        This is used for fail-closed external input handling, where skipping the
        follower would also skip the zero command that needs to be dispatched to
        PX4. Followers opt in case-by-case; inactive output remains rejected by
        default.
        """
        if not tracker_output or tracker_output.tracking_active or not self.follower:
            return False

        handler = getattr(self.follower, 'should_process_inactive_tracker_output', None)
        if not callable(handler):
            return False

        try:
            return bool(handler(tracker_output))
        except Exception as e:
            logging.error(f"Error checking inactive tracker output handling: {e}")
            return False

    def _apply_command_freshness_contract(self, tracker_output: TrackerOutput) -> TrackerOutput:
        """
        Convert stale/prediction-only tracker data into inactive follower input.

        A tracker may still expose a position for overlays, recovery, and
        diagnostics, but PixEagle must not treat cached frames or estimator-only
        predictions as command-fresh target measurements.
        """
        if not tracker_output:
            return tracker_output

        reason = self._tracker_output_unusable_reason(tracker_output)
        frame_status = self._get_video_frame_status_for_following()

        # Recorded video is never command-fresh for PX4.  The only exception
        # is the explicit local COMMAND_PREVIEW session, whose commander is a
        # non-network intent recorder and can therefore exercise follower math.
        replay_preview_active = (
            self._is_command_preview_session()
            and frame_status.get("replay_source") is True
        )
        if (
            self._tracker_requires_video_for_following()
            and frame_status
            and not frame_status.get("usable_for_following", False)
            and not replay_preview_active
        ):
            reason = reason or f"video_frame_{frame_status.get('source', 'unusable')}"

        if reason:
            return self._with_unusable_tracker_metadata(
                tracker_output,
                reason=reason,
                frame_status=frame_status,
            )

        return tracker_output

    def _tracker_output_unusable_reason(self, tracker_output: TrackerOutput) -> Optional[str]:
        """Return the canonical reason when output cannot drive pursuit commands."""
        freshness = evaluate_tracker_command_freshness(tracker_output)
        if freshness["usable_for_following"]:
            return None
        return str(freshness["reason_code"] or "tracker_unusable_for_following")

    def _with_unusable_tracker_metadata(
        self,
        tracker_output: TrackerOutput,
        reason: str,
        frame_status: Optional[Dict[str, Any]] = None,
    ) -> TrackerOutput:
        """Return a copy of tracker output marked unusable for command generation."""
        raw_data = dict(tracker_output.raw_data or {})
        metadata = dict(tracker_output.metadata or {})
        has_output = bool(
            tracker_output.has_position_data()
            or tracker_output.bbox
            or tracker_output.targets
        )

        observed_at = time.time()
        freshness_fields = {
            "usable_for_following": False,
            "data_is_stale": True,
            "command_freshness_blocked": True,
            "freshness_reason": reason,
            "has_output": has_output,
            "observed_at": observed_at,
        }
        if frame_status is not None:
            freshness_fields["video_frame_status"] = dict(frame_status)

        raw_data.update(freshness_fields)
        metadata.update(freshness_fields)

        return dataclasses.replace(
            tracker_output,
            tracking_active=False,
            raw_data=raw_data,
            metadata=metadata,
        )

    def _create_unusable_tracker_output(
        self,
        reason: str,
        frame_status: Optional[Dict[str, Any]] = None,
    ) -> TrackerOutput:
        """Create or adapt inactive output when no frame reaches tracker.update()."""
        base_output = None
        try:
            if self.tracker and hasattr(self.tracker, "get_output"):
                base_output = self.tracker.get_output()
        except Exception as e:
            logging.debug("Could not read tracker output for stale-frame handling: %s", e)

        if isinstance(base_output, TrackerOutput):
            return self._with_unusable_tracker_metadata(
                base_output,
                reason=reason,
                frame_status=frame_status,
            )

        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False,
            tracker_id="video_freshness_guard",
            confidence=0.0,
            raw_data={
                "usable_for_following": False,
                "data_is_stale": True,
                "command_freshness_blocked": True,
                "freshness_reason": reason,
                "has_output": False,
                "video_frame_status": dict(frame_status or {}),
            },
            metadata={
                "tracker_class": self.tracker.__class__.__name__ if self.tracker else None,
                "video_frame_status": dict(frame_status or {}),
                "usable_for_following": False,
                "data_is_stale": True,
                "command_freshness_blocked": True,
                "freshness_reason": reason,
            },
        )

    def _get_video_frame_status_for_following(self) -> Dict[str, Any]:
        """Return latest video freshness metadata, fail-closed if unavailable."""
        video_handler = getattr(self, "video_handler", None)
        if video_handler and hasattr(video_handler, "get_frame_status"):
            try:
                return video_handler.get_frame_status()
            except Exception as e:
                logging.error("Error reading video frame freshness status: %s", e)

        return {
            "source": "unknown",
            "status": "unavailable",
            "usable_for_following": not self._tracker_requires_video_for_following(),
            "reason": "video_frame_status_unavailable",
            "timestamp": time.time(),
        }

    def _tracker_requires_video_for_following(self) -> bool:
        """Return False only for trackers with an explicit non-video contract."""
        tracker = getattr(self, "tracker", None)
        if tracker is None:
            return True

        if getattr(tracker, "is_external_tracker", False):
            capabilities_getter = getattr(tracker, "get_capabilities", None)
            if callable(capabilities_getter):
                try:
                    capabilities = capabilities_getter() or {}
                    return capabilities.get("requires_video", True) is not False
                except Exception as e:
                    logging.debug("Could not read tracker capabilities: %s", e)
            return True

        return True
    
    def get_tracker_capabilities(self) -> Optional[Dict[str, Any]]:
        """
        Gets capabilities of the current active tracker.
        
        Returns:
            Optional[Dict[str, Any]]: Tracker capabilities or None if unavailable
        """
        try:
            if not self.tracker:
                return None
            
            if hasattr(self.tracker, 'get_capabilities'):
                return self.tracker.get_capabilities()
            else:
                # Default capabilities for legacy trackers
                return {
                    'data_types': [TrackerDataType.POSITION_2D.value],
                    'supports_confidence': hasattr(self.tracker, 'confidence'),
                    'supports_velocity': False,
                    'supports_bbox': hasattr(self.tracker, 'bbox'),
                    'legacy_tracker': True
                }
                
        except Exception as e:
            logging.error(f"Error getting tracker capabilities: {e}")
            return None
    
    def get_system_compatibility_report(self) -> Dict[str, Any]:
        """
        Generates a comprehensive compatibility report between tracker and follower.
        
        Returns:
            Dict[str, Any]: Detailed compatibility analysis
        """
        try:
            report = {
                'timestamp': time.time(),
                'tracker_active': bool(self.tracker),
                'follower_active': bool(self.follower),
                'compatible': False,
                'issues': [],
                'recommendations': []
            }
            
            if not self.tracker:
                report['issues'].append("No active tracker")
                return report
            
            if not self.follower:
                report['issues'].append("No active follower")
                return report
            
            # Get current tracker output
            tracker_output = self.get_tracker_output()
            if not tracker_output:
                report['issues'].append("Unable to get tracker output")
                return report
            
            # Get capabilities
            tracker_caps = self.get_tracker_capabilities()
            
            report.update({
                'tracker_capabilities': tracker_caps,
                'current_tracker_data': {
                    'type': tracker_output.data_type.value,
                    'tracking_active': tracker_output.tracking_active,
                    'has_position_2d': tracker_output.position_2d is not None,
                    'has_confidence': tracker_output.confidence is not None,
                }
            })
            
            # Validate compatibility
            is_compatible = self.validate_tracker_follower_compatibility(tracker_output)
            report['compatible'] = is_compatible
            
            if not is_compatible:
                report['issues'].append("Tracker data incompatible with follower requirements")
            else:
                report['recommendations'].append("Current tracker-follower combination is compatible")
            
            return report
            
        except Exception as e:
            logging.error(f"Error generating compatibility report: {e}")
            return {
                'timestamp': time.time(),
                'error': str(e),
                'compatible': False
            }
    
    def _start_system_summary_thread(self):
        """Start a background thread for periodic system summary logging."""
        self._summary_stop_event = threading.Event()
        self._summary_thread = threading.Thread(target=self._system_summary_loop, daemon=True)
        self._summary_thread.start()
        
        # Log the system startup
        logging_manager.log_operation(logging.getLogger(__name__), "System Startup", "info", "PixEagle initialized")
    
    def _system_summary_loop(self):
        """Background loop that generates periodic system summaries."""
        logger = logging.getLogger(__name__)
        
        while not self._summary_stop_event.is_set():
            try:
                # Wait for the next summary interval
                if self._summary_stop_event.wait(60):  # 60-second summaries
                    break  # Stop event was set
                
                # Generate system summary
                logging_manager.log_system_summary(logger)
                
            except Exception as e:
                logger.error(f"Error in system summary loop: {e}")
                
        logger.debug("System summary thread stopped")

    def _is_always_reporting_tracker(self) -> bool:
        """
        Check if the current tracker is an always-reporting tracker based on schema properties.
        Uses direct attribute check to avoid circular dependency.

        Returns:
            bool: True if tracker always reports data regardless of manual start
        """
        if not self.tracker:
            return False

        try:
            # Primary check: direct is_external_tracker attribute (avoids circular call)
            if hasattr(self.tracker, 'is_external_tracker'):
                result = getattr(self.tracker, 'is_external_tracker', False)
                return result

            # Secondary check: tracker class name
            tracker_class_name = self.tracker.__class__.__name__
            # This is a fallback - prefer using is_external_tracker attribute
            external_tracker_classes = {'GimbalTracker', 'ExternalTracker'}
            always_reporting_trackers = external_tracker_classes
            return tracker_class_name in always_reporting_trackers

        except Exception as e:
            logging.warning(f"Error checking always_reporting status: {e}")
            return False
