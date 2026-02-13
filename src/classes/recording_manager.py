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
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
    frames_written: int = 0      # total frames written to file (includes duplicates)
    frames_received: int = 0     # unique frames received from pipeline
    frames_duplicated: int = 0   # extra writes from frame pacing duplication
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

        # H.264 post-processing for browser playback
        self._transcode_h264 = bool(getattr(
            Parameters, 'RECORDING_TRANSCODE_H264', True
        ))
        self._transcoding_files: Set[str] = set()

        # Frame pacing: monotonic-clock frame duplication for real-time playback
        self._recording_start_mono: float = 0.0
        self._total_paused_mono: float = 0.0
        self._pause_start_mono: Optional[float] = None
        self._target_fps: float = 30.0
        self._max_duplication: int = int(getattr(
            Parameters, 'RECORDING_MAX_FRAME_DUPLICATION', 5
        ))

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

            # Create cv2.VideoWriter with robust codec validation.
            #
            # IMPORTANT: On Windows with pip-installed OpenCV, H.264 codecs
            # (avc1, H264) may pass isOpened() but produce corrupt/empty files.
            # We validate each codec by writing+releasing a test frame and
            # checking the output file size before committing to it.
            codec_to_use = self._codec
            fallback_codecs = [codec_to_use]
            if codec_to_use != 'mp4v':
                fallback_codecs.append('mp4v')  # Always fall back to mp4v

            writer = None
            validated_codec = None
            for codec in fallback_codecs:
                if self._validate_codec(codec, fps, width, height):
                    try:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        w = cv2.VideoWriter(filepath, fourcc, fps, (width, height))
                        if w.isOpened():
                            writer = w
                            validated_codec = codec
                            if codec != self._codec:
                                logger.warning(
                                    f"Codec '{self._codec}' failed validation, "
                                    f"using '{codec}' instead"
                                )
                            break
                        else:
                            w.release()
                    except Exception:
                        pass

            if validated_codec:
                codec_to_use = validated_codec

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

            # Initialize frame pacing (monotonic-clock frame duplication)
            self._target_fps = fps
            self._recording_start_mono = time.monotonic()
            self._total_paused_mono = 0.0
            self._pause_start_mono = None

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
            self._pause_start_mono = time.monotonic()
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
        if self._pause_start_mono is not None:
            self._total_paused_mono += time.monotonic() - self._pause_start_mono
            self._pause_start_mono = None
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

        duration = metadata.get('duration_seconds', 1) or 1
        received = self._stats.frames_received
        written = self._stats.frames_written
        duplicated = self._stats.frames_duplicated
        avg_dup = written / max(received, 1)
        eff_fps = written / max(duration, 0.1)
        logger.info(
            f"Recording stopped: {metadata.get('filename', 'unknown')} "
            f"({duration:.1f}s, {received} unique frames, "
            f"{written} total written [{duplicated} duplicated], "
            f"avg dup: {avg_dup:.2f}x, effective FPS: {eff_fps:.1f}, "
            f"target FPS: {self._target_fps:.1f}, "
            f"{metadata.get('file_size_mb', 0):.1f}MB)"
        )

        # Background H.264 transcode for browser playback
        filepath = metadata.get('filepath', '')
        if self._transcode_h264 and filepath and Path(filepath).exists():
            t = threading.Thread(
                target=self._transcode_to_h264,
                args=(filepath,),
                name="recording-transcode",
                daemon=True,
            )
            t.start()

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

            # Non-blocking queue with capture timestamp for frame pacing
            item = (frame, time.monotonic())
            try:
                self._frame_queue.put_nowait(item)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()  # Drop oldest
                except queue.Empty:
                    pass
                self._frame_queue.put_nowait(item)
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
                if f.name in self._transcoding_files:
                    status = "transcoding"
                else:
                    status = "completed"

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
            'frames_received': self._stats.frames_received,
            'frames_duplicated': self._stats.frames_duplicated,
            'frames_dropped': self._stats.queue_drops,
            'file_size_bytes': self._stats.file_size_bytes,
            'file_size_mb': round(self._stats.file_size_bytes / (1024 * 1024), 2),
            'codec': (self._current_metadata.codec if self._current_metadata else self._codec),
            'container': self._container,
            'include_osd': self._include_osd,
            'output_dir': self._output_dir,
            'target_fps': self._target_fps if self.is_active else None,
        }

    # =========================================================================
    # Private methods
    # =========================================================================

    def _writer_loop(self):
        """
        Background thread: pull frames from queue, write to VideoWriter.

        Frame pacing: for each dequeued frame, compute how many frames
        SHOULD have been written by its capture timestamp (based on target
        FPS and recording elapsed time). If behind, duplicate the frame to
        fill the deficit. This ensures the video plays at real-time speed
        regardless of actual pipeline throughput — even when FPS changes
        mid-recording (e.g., tracker enable/disable).
        """
        while not self._writer_stop.is_set():
            try:
                item = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if self._writer and self._writer.isOpened():
                    frame, frame_mono = item

                    # Calculate recording-elapsed time at capture, excluding pauses
                    paused = self._total_paused_mono
                    if self._pause_start_mono is not None:
                        paused += frame_mono - self._pause_start_mono
                    elapsed = max(0.0, frame_mono - self._recording_start_mono - paused)

                    # How many frames should exist at this elapsed time?
                    target_count = int(elapsed * self._target_fps) + 1
                    deficit = target_count - self._stats.frames_written

                    # Always write at least 1; cap to prevent bloat from stalls
                    writes = max(1, min(deficit, self._max_duplication))

                    for _ in range(writes):
                        self._writer.write(frame)

                    self._stats.frames_received += 1
                    self._stats.frames_written += writes
                    if writes > 1:
                        self._stats.frames_duplicated += writes - 1

                    # Update file size periodically (every 30 received frames)
                    if self._stats.frames_received % 30 == 0:
                        self._update_file_size()
            except Exception as e:
                logger.error(f"Error writing frame to recording: {e}")
                self._stats.frames_dropped += 1

        # Drain remaining frames (write once each, no duplication during flush)
        while not self._frame_queue.empty():
            try:
                item = self._frame_queue.get_nowait()
                if self._writer and self._writer.isOpened():
                    frame, _ = item
                    self._writer.write(frame)
                    self._stats.frames_received += 1
                    self._stats.frames_written += 1
            except (queue.Empty, Exception):
                break

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
            'filepath': meta.filepath,
            'duration_seconds': meta.duration_seconds,
            'frame_count': meta.frame_count,
            'frames_received': self._stats.frames_received,
            'frames_duplicated': self._stats.frames_duplicated,
            'file_size_bytes': meta.file_size_bytes,
            'file_size_mb': round(meta.file_size_bytes / (1024 * 1024), 2),
            'message': f'Recording saved: {meta.filename}',
        }

        self._current_metadata = None
        return result

    def _transcode_to_h264(self, filepath: str):
        """
        Background transcode from mp4v to browser-playable H.264.

        Uses FFmpeg to re-encode with libx264. The original mp4v file is
        replaced with the H.264 version via atomic rename. If FFmpeg is
        not installed, logs a warning and leaves the mp4v file as-is
        (still playable in VLC/WMP, just not in browsers).

        Args:
            filepath: Absolute path to the finalized .mp4 file.
        """
        if not shutil.which('ffmpeg'):
            logger.info(
                "FFmpeg not found — skipping H.264 transcode. "
                "Recording plays in VLC/WMP but not in browsers. "
                "Install FFmpeg for browser playback support."
            )
            return

        filename = Path(filepath).name
        self._transcoding_files.add(filename)
        temp_h264 = filepath + '.h264.tmp'

        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', filepath,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                '-an',  # no audio track
                temp_h264,
            ]
            logger.info(f"Transcoding to H.264: {filename}")
            result = subprocess.run(
                cmd, capture_output=True, timeout=600,
            )

            if result.returncode == 0 and Path(temp_h264).exists():
                original_size = Path(filepath).stat().st_size
                h264_size = Path(temp_h264).stat().st_size
                Path(temp_h264).replace(filepath)
                logger.info(
                    f"H.264 transcode complete: {filename} "
                    f"({original_size / 1048576:.1f}MB → "
                    f"{h264_size / 1048576:.1f}MB)"
                )
            else:
                stderr = result.stderr.decode(errors='replace')[-200:]
                logger.error(
                    f"FFmpeg transcode failed for {filename}: {stderr}"
                )
                try:
                    Path(temp_h264).unlink(missing_ok=True)
                except OSError:
                    pass
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg transcode timed out for {filename}")
            try:
                Path(temp_h264).unlink(missing_ok=True)
            except OSError:
                pass
        except Exception as e:
            logger.error(f"H.264 transcode error for {filename}: {e}")
            try:
                Path(temp_h264).unlink(missing_ok=True)
            except OSError:
                pass
        finally:
            self._transcoding_files.discard(filename)

    def _validate_codec(self, codec: str, fps: float, width: int,
                        height: int) -> bool:
        """
        Validate a codec by writing a test frame and checking output.

        Some codecs (notably avc1/H264 on Windows with pip OpenCV) pass
        isOpened() but produce corrupt/empty files. This method writes a
        single black frame, releases the writer, and checks whether the
        output file has meaningful size (> 100 bytes).

        Args:
            codec: FOURCC codec string (e.g., 'mp4v', 'avc1')
            fps: Recording FPS
            width: Frame width
            height: Frame height

        Returns:
            True if the codec produces valid output.
        """
        # mp4v is known-good — skip the test to save time
        if codec == 'mp4v':
            return True

        test_path = Path(self._output_dir) / f".codec_test_{codec}.mp4"
        try:
            fourcc = cv2.VideoWriter_fourcc(*codec)
            test_writer = cv2.VideoWriter(
                str(test_path), fourcc, fps, (width, height)
            )
            if not test_writer.isOpened():
                return False

            # Write a test frame (black)
            test_frame = np.zeros((height, width, 3), dtype=np.uint8)
            test_writer.write(test_frame)
            test_writer.release()

            # Check output size — a valid codec produces > 100 bytes
            # for even a single black frame (mp4 header alone is ~40 bytes)
            if test_path.exists():
                size = test_path.stat().st_size
                if size > 100:
                    logger.debug(
                        f"Codec '{codec}' validated OK "
                        f"(test file: {size} bytes)"
                    )
                    return True
                else:
                    logger.warning(
                        f"Codec '{codec}' produces corrupt output "
                        f"(test file: {size} bytes) — skipping"
                    )
                    return False
            else:
                logger.warning(f"Codec '{codec}' failed to create output file")
                return False
        except Exception as e:
            logger.warning(f"Codec '{codec}' validation error: {e}")
            return False
        finally:
            try:
                test_path.unlink(missing_ok=True)
            except OSError:
                pass

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
