"""
Recording Manager — Non-blocking video recording engine for PixEagle.

Architecture mirrors GStreamerHandler (gstreamer_handler.py):
- write_frame() is non-blocking (queues frame for background thread)
- Bounded queue with oldest-frame dropping on overflow
- Background writer thread pulls from queue and writes to cv2.VideoWriter
- Thread-safe state machine for start/pause/resume/stop

Crash Recovery:
- Files are written with .tmp suffix during recording
- On clean stop, .tmp is renamed to final filename
- On startup, _recover_incomplete_recordings() finds leftover .tmp files
  and renames them (the video content is intact since cv2.VideoWriter
  flushes incrementally)

Integration point: app_controller.py update_loop(), right after GStreamer output.

Author: PixEagle Recording System
"""

import cv2
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from classes.parameters import Parameters

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Recording state machine states."""
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class RecordingMetadata:
    """Metadata for a single recording session."""
    filename: str
    filepath: str
    started_at: float            # time.time() UTC
    started_at_iso: str          # ISO 8601 UTC string
    width: int = 0
    height: int = 0
    fps: float = 0.0
    codec: str = ""
    short_uuid: str = ""
    stopped_at: Optional[float] = None
    duration_seconds: float = 0.0
    frame_count: int = 0
    file_size_bytes: int = 0
    status: str = "recording"    # recording | completed | recovered | error


@dataclass
class RecordingStats:
    """Runtime statistics for the current recording session."""
    frames_written: int = 0
    frames_dropped: int = 0
    queue_drops: int = 0
    file_size_bytes: int = 0


class RecordingManager:
    """
    Non-blocking video recording engine.

    Follows the identical architecture as GStreamerHandler:
    - write_frame() queues frames via bounded queue (never blocks main loop)
    - Background daemon thread writes frames to cv2.VideoWriter
    - Queue overflow drops oldest frame (same pattern as gstreamer_handler.py:269-277)

    Usage:
        manager = RecordingManager()
        manager.start(source_fps=30, source_width=640, source_height=480)
        # In main loop:
        manager.write_frame(frame)
        # When done:
        manager.stop()
    """

    TEMP_SUFFIX = ".tmp"

    def __init__(self):
        # Configuration from Parameters (loaded from Recording: YAML section)
        self._output_dir = str(getattr(Parameters, 'RECORDING_OUTPUT_DIR', 'recordings'))
        self._codec = str(getattr(Parameters, 'RECORDING_CODEC', 'mp4v'))
        self._container = str(getattr(Parameters, 'RECORDING_CONTAINER', 'mp4'))
        self._fps = float(getattr(Parameters, 'RECORDING_FPS', 0))
        self._width = int(getattr(Parameters, 'RECORDING_WIDTH', 0))
        self._height = int(getattr(Parameters, 'RECORDING_HEIGHT', 0))
        self._max_queue_size = int(getattr(Parameters, 'RECORDING_QUEUE_SIZE', 5))
        self._include_osd = bool(getattr(Parameters, 'RECORDING_INCLUDE_OSD', True))
        self._auto_recovery = bool(getattr(Parameters, 'RECORDING_AUTO_RECOVERY', True))

        # State machine
        self._state = RecordingState.IDLE
        self._state_lock = threading.Lock()

        # VideoWriter
        self._writer: Optional[cv2.VideoWriter] = None
        self._current_metadata: Optional[RecordingMetadata] = None
        self._stats = RecordingStats()

        # Non-blocking writer thread (mirrors GStreamerHandler pattern)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=self._max_queue_size)
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_stop = threading.Event()

        # Pause tracking
        self._pause_start: Optional[float] = None
        self._total_paused: float = 0.0

        # Ensure output directory exists
        Path(self._output_dir).mkdir(parents=True, exist_ok=True)

        # Run crash recovery on initialization
        recovered = []
        if self._auto_recovery:
            recovered = self._recover_incomplete_recordings()

        logger.info(
            f"RecordingManager initialized: dir={self._output_dir}, "
            f"codec={self._codec}, container={self._container}, "
            f"queue_size={self._max_queue_size}"
            + (f", recovered {len(recovered)} file(s)" if recovered else "")
        )

    # =========================================================================
    # Public API
    # =========================================================================

    def start(self, source_fps: float = 30.0, source_width: int = 640,
              source_height: int = 480) -> Dict[str, Any]:
        """
        Start a new recording.

        Args:
            source_fps: Source video FPS (used if RECORDING_FPS=0)
            source_width: Source frame width (used if RECORDING_WIDTH=0)
            source_height: Source frame height (used if RECORDING_HEIGHT=0)

        Returns:
            Dict with status, filename, message
        """
        with self._state_lock:
            if self._state == RecordingState.RECORDING:
                return {'status': 'error', 'message': 'Already recording'}
            if self._state == RecordingState.PAUSED:
                return self._resume_internal()

            # Determine actual recording parameters
            fps = self._fps if self._fps > 0 else source_fps
            width = self._width if self._width > 0 else source_width
            height = self._height if self._height > 0 else source_height

            # Ensure valid dimensions
            width = max(1, int(width))
            height = max(1, int(height))
            fps = max(1.0, float(fps))

            # Generate filename: PixEagle_<date>_<time>_<uuid>.<ext>
            # Human-readable format with UUID suffix for uniqueness
            now = time.time()
            date_str = time.strftime('%Y-%m-%d', time.gmtime(now))
            time_str = time.strftime('%H-%M-%S', time.gmtime(now))
            short_id = uuid.uuid4().hex[:8]
            filename = f"PixEagle_{date_str}_{time_str}_{short_id}.{self._container}"
            temp_filename = filename + self.TEMP_SUFFIX
            filepath = str(Path(self._output_dir) / temp_filename)

            # Create cv2.VideoWriter — try H.264 variants then fall back to mp4v
            # avc1: macOS/QuickTime, H264: Windows MSMF/ffmpeg, mp4v: universal fallback
            codec_to_use = self._codec
            fallback_codecs = []
            if codec_to_use in ('avc1', 'H264'):
                fallback_codecs = ['avc1', 'H264', 'mp4v']
            elif codec_to_use != 'mp4v':
                fallback_codecs = [codec_to_use, 'mp4v']
            else:
                fallback_codecs = ['mp4v']

            writer = None
            for codec in fallback_codecs:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*codec)
                    w = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
                    if w.isOpened():
                        writer = w
                        codec_to_use = codec
                        if codec != self._codec:
                            logger.warning(f"Codec '{self._codec}' unavailable, using '{codec}'")
                        break
                    else:
                        w.release()
                except Exception:
                    pass

            if writer is None or not writer.isOpened():
                logger.error(f"Failed to open VideoWriter: {filepath} "
                           f"(tried codecs: {fallback_codecs}, {width}x{height}@{fps}fps)")
                self._state = RecordingState.ERROR
                return {'status': 'error', 'message': 'Failed to initialize video writer'}

            self._writer = writer
            self._current_metadata = RecordingMetadata(
                filename=filename,
                filepath=filepath,
                started_at=now,
                started_at_iso=f"{date_str}T{time_str}Z",
                width=width,
                height=height,
                fps=fps,
                codec=codec_to_use,
                short_uuid=short_id,
            )
            self._stats = RecordingStats()
            self._total_paused = 0.0
            self._pause_start = None

            # Clear any stale frames from queue
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break

            # Start background writer thread
            self._writer_stop.clear()
            self._writer_thread = threading.Thread(
                target=self._writer_loop, name="recording-writer", daemon=True
            )
            self._writer_thread.start()
            self._state = RecordingState.RECORDING

            logger.info(
                f"Recording started: {filename} "
                f"({width}x{height} @ {fps:.1f}fps, codec={self._codec})"
            )

            return {
                'status': 'success',
                'filename': filename,
                'message': f'Recording started: {filename}',
            }

    def pause(self) -> Dict[str, Any]:
        """Pause recording. Frames are silently dropped while paused."""
        with self._state_lock:
            if self._state != RecordingState.RECORDING:
                return {'status': 'error', 'message': 'Not currently recording'}
            self._state = RecordingState.PAUSED
            self._pause_start = time.time()
            logger.info("Recording paused")
            return {'status': 'success', 'message': 'Recording paused'}

    def resume(self) -> Dict[str, Any]:
        """Resume a paused recording."""
        with self._state_lock:
            return self._resume_internal()

    def _resume_internal(self) -> Dict[str, Any]:
        """Resume implementation (must be called with _state_lock held)."""
        if self._state != RecordingState.PAUSED:
            return {'status': 'error', 'message': 'Not paused'}
        if self._pause_start is not None:
            self._total_paused += time.time() - self._pause_start
            self._pause_start = None
        self._state = RecordingState.RECORDING
        logger.info("Recording resumed")
        return {'status': 'success', 'message': 'Recording resumed'}

    def stop(self) -> Dict[str, Any]:
        """Stop recording, finalize file, update metadata."""
        with self._state_lock:
            if self._state not in (RecordingState.RECORDING, RecordingState.PAUSED):
                return {'status': 'error', 'message': 'Not recording'}
            self._state = RecordingState.STOPPING

        # Signal writer thread to stop
        self._writer_stop.set()
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
            self._writer_thread = None

        # Release VideoWriter
        if self._writer:
            try:
                self._writer.release()
            except Exception as e:
                logger.error(f"Error releasing VideoWriter: {e}")
            self._writer = None

        # Finalize: rename .tmp to final filename
        metadata = self._finalize_recording()

        with self._state_lock:
            self._state = RecordingState.IDLE

        logger.info(
            f"Recording stopped: {metadata.get('filename', 'unknown')} "
            f"({metadata.get('duration_seconds', 0):.1f}s, "
            f"{metadata.get('frame_count', 0)} frames, "
            f"{metadata.get('file_size_mb', 0):.1f}MB)"
        )
        return {'status': 'success', **metadata}

    def write_frame(self, frame: np.ndarray):
        """
        Queue a frame for recording (non-blocking).

        Mirrors GStreamerHandler.stream_frame() pattern exactly:
        - If not recording, returns immediately
        - If queue is full, drops oldest frame and inserts new one
        - Never blocks the main processing loop

        Args:
            frame: BGR uint8 frame from OpenCV
        """
        if self._state != RecordingState.RECORDING:
            return

        try:
            # Validate frame
            if frame is None or frame.size == 0:
                return

            # Resize if dimensions don't match the recording resolution
            meta = self._current_metadata
            if meta and (frame.shape[1] != meta.width or frame.shape[0] != meta.height):
                frame = cv2.resize(frame, (meta.width, meta.height))

            # Non-blocking queue (identical to GStreamerHandler pattern)
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()  # Drop oldest
                except queue.Empty:
                    pass
                self._frame_queue.put_nowait(frame)
                self._stats.queue_drops += 1

        except Exception as e:
            logger.error(f"Error queuing frame for recording: {e}")

    def set_include_osd(self, value: bool):
        """Toggle whether OSD overlays are included in the recording."""
        self._include_osd = bool(value)
        logger.info(f"Recording OSD overlay {'enabled' if self._include_osd else 'disabled'}")

    def release(self):
        """Clean shutdown. Called during application shutdown."""
        if self.is_active:
            self.stop()

    # =========================================================================
    # Recording management
    # =========================================================================

    def list_recordings(self) -> List[Dict[str, Any]]:
        """
        List all recordings in the output directory with metadata.

        Returns:
            List of dicts sorted by creation time (newest first).
        """
        recordings = []
        output_dir = Path(self._output_dir)
        if not output_dir.exists():
            return recordings

        valid_extensions = {'.mp4', '.avi', '.mkv'}

        for f in output_dir.iterdir():
            if not f.is_file() or f.suffix.lower() not in valid_extensions:
                continue
            # Skip .tmp files (incomplete recordings)
            if f.name.endswith(self.TEMP_SUFFIX):
                continue

            try:
                stat = f.stat()
                # Parse timestamp from filename: PixEagle_YYYY-MM-DD_HH-MM-SS_uuid.ext
                name_parts = f.stem.split('_')
                # Reconstruct date+time as ISO-like string
                if len(name_parts) >= 3:
                    iso_str = f"{name_parts[1]}T{name_parts[2]}Z"
                elif len(name_parts) >= 2:
                    iso_str = name_parts[1]
                else:
                    iso_str = ""

                # Determine status
                status = "completed"
                # Check for recovered files (those without expected PixEagle prefix
                # or with other anomalies could be flagged, but for now all are "completed")

                recordings.append({
                    'filename': f.name,
                    'size_bytes': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'created_at': stat.st_ctime,
                    'created_at_iso': iso_str,
                    'modified_at': stat.st_mtime,
                    'status': status,
                })
            except OSError:
                continue

        # Sort by creation time, newest first
        recordings.sort(key=lambda r: r['created_at'], reverse=True)
        return recordings

    def delete_recording(self, filename: str) -> Dict[str, Any]:
        """
        Delete a recording file by name.

        Args:
            filename: Name of the file to delete (just the filename, not path)

        Returns:
            Dict with status and message
        """
        # Sanitize: prevent path traversal
        safe_name = Path(filename).name

        # Don't delete the currently recording file
        if self._current_metadata and self._current_metadata.filename == safe_name:
            return {'status': 'error', 'message': 'Cannot delete active recording'}

        filepath = Path(self._output_dir) / safe_name

        if not filepath.exists():
            return {'status': 'error', 'message': f'File not found: {safe_name}'}
        if not filepath.is_file():
            return {'status': 'error', 'message': f'Not a file: {safe_name}'}

        try:
            filepath.unlink()
            logger.info(f"Deleted recording: {safe_name}")
            return {'status': 'success', 'message': f'Deleted: {safe_name}'}
        except OSError as e:
            logger.error(f"Failed to delete recording {safe_name}: {e}")
            return {'status': 'error', 'message': f'Delete failed: {e}'}

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def state(self) -> str:
        """Current recording state as string."""
        return self._state.value

    @property
    def is_recording(self) -> bool:
        """True if actively recording (not paused)."""
        return self._state == RecordingState.RECORDING

    @property
    def is_active(self) -> bool:
        """True if recording or paused (session in progress)."""
        return self._state in (RecordingState.RECORDING, RecordingState.PAUSED)

    @property
    def status(self) -> Dict[str, Any]:
        """Complete status dict for API responses."""
        elapsed = 0.0
        if self._current_metadata:
            raw_elapsed = time.time() - self._current_metadata.started_at
            elapsed = raw_elapsed - self._total_paused
            if self._pause_start is not None:
                elapsed -= (time.time() - self._pause_start)

        return {
            'state': self._state.value,
            'is_recording': self.is_recording,
            'is_active': self.is_active,
            'filename': self._current_metadata.filename if self._current_metadata else None,
            'elapsed_seconds': round(max(0, elapsed), 1),
            'frames_written': self._stats.frames_written,
            'frames_dropped': self._stats.queue_drops,
            'file_size_bytes': self._stats.file_size_bytes,
            'file_size_mb': round(self._stats.file_size_bytes / (1024 * 1024), 2),
            'codec': self._codec,
            'container': self._container,
            'include_osd': self._include_osd,
            'output_dir': self._output_dir,
        }

    # =========================================================================
    # Private methods
    # =========================================================================

    def _writer_loop(self):
        """
        Background thread: pull frames from queue, write to VideoWriter.
        Mirrors GStreamerHandler._writer_loop().
        """
        while not self._writer_stop.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if self._writer and self._writer.isOpened():
                    self._writer.write(frame)
                    self._stats.frames_written += 1
                    # Update file size periodically (every 30 frames to minimize I/O)
                    if self._stats.frames_written % 30 == 0:
                        self._update_file_size()
            except Exception as e:
                logger.error(f"Error writing frame to recording: {e}")
                self._stats.frames_dropped += 1

        # Drain remaining frames from queue before exiting
        while not self._frame_queue.empty():
            try:
                frame = self._frame_queue.get_nowait()
                if self._writer and self._writer.isOpened():
                    self._writer.write(frame)
                    self._stats.frames_written += 1
            except (queue.Empty, Exception):
                break

        # Final file size update
        self._update_file_size()

    def _update_file_size(self):
        """Update file size stat from disk."""
        if self._current_metadata:
            try:
                self._stats.file_size_bytes = Path(
                    self._current_metadata.filepath
                ).stat().st_size
            except OSError:
                pass

    def _finalize_recording(self) -> Dict[str, Any]:
        """Rename .tmp file to final name, compute metadata."""
        if not self._current_metadata:
            return {}

        meta = self._current_metadata
        tmp_path = Path(meta.filepath)
        final_path = Path(str(meta.filepath).replace(self.TEMP_SUFFIX, ""))

        try:
            if tmp_path.exists():
                # Path.replace() is atomic on both Windows and Linux
                tmp_path.replace(final_path)
                meta.filepath = str(final_path)
                logger.debug(f"Finalized recording: {meta.filename}")
        except OSError as e:
            logger.error(f"Failed to finalize recording file: {e}")
            # File stays as .tmp but is still valid video

        meta.stopped_at = time.time()
        meta.frame_count = self._stats.frames_written
        meta.status = "completed"

        raw_elapsed = meta.stopped_at - meta.started_at
        meta.duration_seconds = round(raw_elapsed - self._total_paused, 1)

        try:
            meta.file_size_bytes = Path(meta.filepath).stat().st_size
        except OSError:
            meta.file_size_bytes = self._stats.file_size_bytes

        result = {
            'filename': meta.filename,
            'duration_seconds': meta.duration_seconds,
            'frame_count': meta.frame_count,
            'file_size_bytes': meta.file_size_bytes,
            'file_size_mb': round(meta.file_size_bytes / (1024 * 1024), 2),
            'message': f'Recording saved: {meta.filename}',
        }

        self._current_metadata = None
        return result

    def _recover_incomplete_recordings(self) -> List[str]:
        """
        On startup, find .tmp files (crashed recordings) and finalize them.

        Returns:
            List of recovered filenames.
        """
        recovered = []
        try:
            output_dir = Path(self._output_dir)
            if not output_dir.exists():
                return recovered

            for tmp_file in output_dir.glob(f"*{self.TEMP_SUFFIX}"):
                final_name = tmp_file.name.replace(self.TEMP_SUFFIX, "")
                final_path = tmp_file.parent / final_name
                try:
                    # Don't overwrite existing final files
                    if final_path.exists():
                        logger.warning(
                            f"Cannot recover {tmp_file.name}: "
                            f"{final_name} already exists"
                        )
                        continue
                    tmp_file.replace(final_path)
                    recovered.append(final_name)
                    logger.warning(f"Recovered incomplete recording: {final_name}")
                except OSError as e:
                    logger.error(f"Failed to recover {tmp_file.name}: {e}")

        except Exception as e:
            logger.error(f"Error during recording recovery scan: {e}")

        return recovered
