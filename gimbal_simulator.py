#!/usr/bin/env python3
"""
PixEagle Gimbal Simulator - All-in-One
=====================================

Single file gimbal simulator with GUI for PixEagle testing.
No additional setup required - just run this file!

Usage:
    python gimbal_simulator.py

Features:
- Complete SIP protocol gimbal emulation
- Real-time GUI control with sliders
- Manual target positioning
- Auto tracking patterns (circular, random, figure-8)
- Drop-in replacement for real gimbal hardware

Author: Alireza Ghaderi
Project: PixEagle
"""

import socket
import time
import threading
import logging
import math
import random
import sys
from typing import Optional, Dict, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

# Auto-install required packages
def auto_install_dependencies():
    """Automatically install required packages if missing."""
    required_packages = []

    # Check tkinter
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("ERROR: tkinter not found. Install with:")
        print("  Ubuntu/Debian: sudo apt-get install python3-tk")
        print("  CentOS/RHEL: sudo yum install tkinter")
        sys.exit(1)

    # Install missing packages
    if required_packages:
        import subprocess
        for package in required_packages:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Auto-install on import
auto_install_dependencies()

# Now import everything we need
import tkinter as tk
from tkinter import ttk, messagebox

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CORE SIMULATOR CLASSES
# =============================================================================

class SimulatedTrackingState(Enum):
    """Tracking states matching real gimbal protocol"""
    DISABLED = 0
    TARGET_SELECTION = 1
    TRACKING_ACTIVE = 2
    TARGET_LOST = 3

class CoordinateSystem(Enum):
    """Coordinate system modes"""
    GIMBAL_BODY = "gimbal_body"
    SPATIAL_FIXED = "spatial_fixed"

@dataclass
class SimulatorConfig:
    """Simulator configuration"""
    listen_port: int = 9003
    broadcast_port: int = 9004
    broadcast_host: str = "127.0.0.1"
    broadcast_interval: float = 0.1
    yaw_min: float = -180.0
    yaw_max: float = 180.0
    pitch_min: float = -90.0
    pitch_max: float = 90.0
    roll_min: float = -45.0
    roll_max: float = 45.0
    tracking_noise: float = 0.2
    auto_track_radius: float = 20.0
    auto_track_speed: float = 10.0
    coordinate_system: CoordinateSystem = CoordinateSystem.SPATIAL_FIXED

class GimbalSimulator:
    """Complete gimbal simulator with SIP protocol support"""

    def __init__(self, config: Optional[SimulatorConfig] = None):
        self.config = config or SimulatorConfig()

        # Network
        self.listen_socket: Optional[socket.socket] = None
        self.broadcast_socket: Optional[socket.socket] = None

        # Threading
        self.running = False
        self.command_thread: Optional[threading.Thread] = None
        self.broadcast_thread: Optional[threading.Thread] = None
        self.auto_track_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # State
        self.current_yaw = 0.0
        self.current_pitch = 0.0
        self.current_roll = 0.0
        self.tracking_state = SimulatedTrackingState.DISABLED

        # Manual target control
        self.manual_target_mode = False
        self.manual_target_yaw = 0.0
        self.manual_target_pitch = 0.0
        self.target_yaw = 0.0
        self.target_pitch = 0.0

        # Auto tracking
        self.auto_pattern = "circular"  # circular, figure8, random
        self.tracking_start_time = 0.0
        self.last_update_time = time.time()

        # Statistics
        self.commands_received = 0
        self.responses_sent = 0
        self.broadcasts_sent = 0

        logger.info(f"Gimbal simulator initialized - ports {self.config.listen_port}/{self.config.broadcast_port}")

    def start(self) -> bool:
        """Start the simulator"""
        if self.running:
            return True

        try:
            # Initialize sockets
            self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listen_socket.bind(('0.0.0.0', self.config.listen_port))
            self.listen_socket.settimeout(0.1)

            self.broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # Start threads
            self.running = True

            self.command_thread = threading.Thread(target=self._command_loop, daemon=True)
            self.command_thread.start()

            self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
            self.broadcast_thread.start()

            self.auto_track_thread = threading.Thread(target=self._auto_track_loop, daemon=True)
            self.auto_track_thread.start()

            logger.info(f"Simulator started - listening on {self.config.listen_port}, broadcasting to {self.config.broadcast_host}:{self.config.broadcast_port}")
            return True

        except Exception as e:
            logger.error(f"Failed to start simulator: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop the simulator"""
        self.running = False

        if self.listen_socket:
            self.listen_socket.close()
        if self.broadcast_socket:
            self.broadcast_socket.close()

        logger.info("Simulator stopped")

    def set_gimbal_angles(self, yaw: float, pitch: float, roll: float):
        """Set gimbal angles"""
        with self.lock:
            self.current_yaw = max(self.config.yaw_min, min(self.config.yaw_max, yaw))
            self.current_pitch = max(self.config.pitch_min, min(self.config.pitch_max, pitch))
            self.current_roll = max(self.config.roll_min, min(self.config.roll_max, roll))

    def set_tracking_state(self, state: SimulatedTrackingState):
        """Set tracking state"""
        with self.lock:
            old_state = self.tracking_state
            self.tracking_state = state

            if state == SimulatedTrackingState.TRACKING_ACTIVE:
                self.tracking_start_time = time.time()
                if self.manual_target_mode:
                    self.target_yaw = self.manual_target_yaw
                    self.target_pitch = self.manual_target_pitch
                else:
                    self.target_yaw = self.current_yaw
                    self.target_pitch = self.current_pitch

            logger.info(f"Tracking state: {old_state.name} → {state.name}")

    def set_manual_target(self, yaw: float, pitch: float):
        """Set manual target position"""
        with self.lock:
            self.manual_target_yaw = max(self.config.yaw_min, min(self.config.yaw_max, yaw))
            self.manual_target_pitch = max(self.config.pitch_min, min(self.config.pitch_max, pitch))
            self.manual_target_mode = True

            if self.tracking_state == SimulatedTrackingState.TRACKING_ACTIVE:
                self.target_yaw = self.manual_target_yaw
                self.target_pitch = self.manual_target_pitch

    def set_auto_pattern(self, pattern: str):
        """Set auto tracking pattern"""
        with self.lock:
            self.auto_pattern = pattern
            # Only disable manual mode if we're explicitly switching to auto mode
            # This method is called both from mode changes and pattern changes

    def get_state(self) -> Dict[str, Any]:
        """Get current state"""
        with self.lock:
            return {
                'angles': {'yaw': self.current_yaw, 'pitch': self.current_pitch, 'roll': self.current_roll},
                'tracking_state': self.tracking_state.name,
                'manual_target_mode': self.manual_target_mode,
                'target': {'yaw': self.manual_target_yaw if self.manual_target_mode else self.target_yaw,
                          'pitch': self.manual_target_pitch if self.manual_target_mode else self.target_pitch},
                'auto_pattern': self.auto_pattern,
                'stats': {'commands': self.commands_received, 'responses': self.responses_sent, 'broadcasts': self.broadcasts_sent}
            }

    def _command_loop(self):
        """Handle incoming commands"""
        while self.running:
            try:
                data, addr = self.listen_socket.recvfrom(1024)
                command = data.decode('ascii', errors='replace').strip()

                with self.lock:
                    self.commands_received += 1

                response = self._process_command(command)
                if response:
                    self.listen_socket.sendto(response.encode('ascii'), addr)
                    with self.lock:
                        self.responses_sent += 1

            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"Command error: {e}")

    def _broadcast_loop(self):
        """Broadcast gimbal data following real gimbal protocol"""
        broadcast_counter = 0
        while self.running:
            try:
                # Build angle data
                with self.lock:
                    yaw_hex = self._angle_to_hex(self.current_yaw)
                    pitch_hex = self._angle_to_hex(self.current_pitch)
                    roll_hex = self._angle_to_hex(self.current_roll)

                # Always broadcast angle data (primary data stream)
                angle_broadcast = f"#tpDP9wOFT{yaw_hex}{pitch_hex}{roll_hex}"
                self.broadcast_socket.sendto(
                    angle_broadcast.encode('ascii'),
                    (self.config.broadcast_host, self.config.broadcast_port)
                )

                # Send tracking status every 10th broadcast (like real gimbal)
                broadcast_counter += 1
                if broadcast_counter % 10 == 0:
                    time.sleep(0.05)  # Small delay between packets
                    status_broadcast = self._build_tracking_response()
                    self.broadcast_socket.sendto(
                        status_broadcast.encode('ascii'),
                        (self.config.broadcast_host, self.config.broadcast_port)
                    )

                with self.lock:
                    self.broadcasts_sent += 1

                time.sleep(self.config.broadcast_interval)

            except Exception as e:
                logger.debug(f"Broadcast error: {e}")

    def _auto_track_loop(self):
        """Auto tracking patterns"""
        while self.running:
            try:
                if (self.tracking_state == SimulatedTrackingState.TRACKING_ACTIVE and
                    not self.manual_target_mode):

                    current_time = time.time()
                    dt = current_time - self.last_update_time
                    self.last_update_time = current_time

                    with self.lock:
                        if self.auto_pattern == "circular":
                            self._update_circular(dt)
                        elif self.auto_pattern == "figure8":
                            self._update_figure8(dt)
                        elif self.auto_pattern == "random":
                            self._update_random(dt)

                        # Add noise
                        noise_yaw = random.uniform(-self.config.tracking_noise, self.config.tracking_noise)
                        noise_pitch = random.uniform(-self.config.tracking_noise, self.config.tracking_noise)

                        self.current_yaw += noise_yaw
                        self.current_pitch += noise_pitch

                        # Apply limits
                        self.current_yaw = max(self.config.yaw_min, min(self.config.yaw_max, self.current_yaw))
                        self.current_pitch = max(self.config.pitch_min, min(self.config.pitch_max, self.current_pitch))

                elif (self.tracking_state == SimulatedTrackingState.TRACKING_ACTIVE and
                      self.manual_target_mode):
                    # Manual target tracking
                    dt = time.time() - self.last_update_time
                    self.last_update_time = time.time()

                    with self.lock:
                        # Smooth tracking toward manual target
                        self.current_yaw += (self.target_yaw - self.current_yaw) * dt * 2.0
                        self.current_pitch += (self.target_pitch - self.current_pitch) * dt * 2.0

                time.sleep(0.1)

            except Exception as e:
                logger.debug(f"Auto track error: {e}")

    def _update_circular(self, dt: float):
        """Circular tracking pattern"""
        elapsed = time.time() - self.tracking_start_time
        angle = elapsed * self.config.auto_track_speed * math.pi / 180.0

        self.target_yaw = self.config.auto_track_radius * math.cos(angle)
        self.target_pitch = self.config.auto_track_radius * math.sin(angle)

        self.current_yaw += (self.target_yaw - self.current_yaw) * dt * 2.0
        self.current_pitch += (self.target_pitch - self.current_pitch) * dt * 2.0

    def _update_figure8(self, dt: float):
        """Figure-8 tracking pattern"""
        elapsed = time.time() - self.tracking_start_time
        angle = elapsed * self.config.auto_track_speed * math.pi / 180.0

        self.target_yaw = self.config.auto_track_radius * math.sin(angle)
        self.target_pitch = self.config.auto_track_radius * math.sin(2 * angle) / 2

        self.current_yaw += (self.target_yaw - self.current_yaw) * dt * 2.0
        self.current_pitch += (self.target_pitch - self.current_pitch) * dt * 2.0

    def _update_random(self, dt: float):
        """Random tracking pattern"""
        max_change = self.config.auto_track_speed * dt

        self.target_yaw += random.uniform(-max_change, max_change)
        self.target_pitch += random.uniform(-max_change, max_change)

        self.target_yaw = max(-30, min(30, self.target_yaw))
        self.target_pitch = max(-20, min(20, self.target_pitch))

        self.current_yaw += (self.target_yaw - self.current_yaw) * dt * 1.5
        self.current_pitch += (self.target_pitch - self.current_pitch) * dt * 1.5

    def _process_command(self, command: str) -> Optional[str]:
        """Process SIP protocol commands"""
        try:
            if not command.startswith('#tp'):
                return None

            if 'GAC' in command:  # Gimbal body angles
                return self._build_angle_response('GAC')
            elif 'GIC' in command:  # Spatial fixed angles
                return self._build_angle_response('GIC')
            elif 'TRC' in command:  # Tracking status
                return self._build_tracking_response()

        except Exception as e:
            logger.debug(f"Command processing error: {e}")

        return None

    def _build_angle_response(self, command_type: str) -> str:
        """Build SIP angle response following exact real gimbal protocol"""
        with self.lock:
            yaw_hex = self._angle_to_hex(self.current_yaw)
            pitch_hex = self._angle_to_hex(self.current_pitch)
            roll_hex = self._angle_to_hex(self.current_roll)

        # Real gimbal protocol: #tpUG2r[GAC/GIC][YYYYPPPPRRRR][checksum]
        response_base = f"#tpUG2r{command_type}{yaw_hex}{pitch_hex}{roll_hex}"
        checksum = sum(response_base.encode('ascii')) & 0xFF
        return f"{response_base}{checksum:02X}"

    def _build_tracking_response(self) -> str:
        """Build SIP tracking response"""
        with self.lock:
            state_value = self.tracking_state.value

        response_base = f"#tpUD2rTRC0{state_value}"
        checksum = sum(response_base.encode('ascii')) & 0xFF
        return f"{response_base}{checksum:02X}"

    def _angle_to_hex(self, angle_deg: float) -> str:
        """Convert angle to hex format"""
        angle_units = int(round(angle_deg * 100))
        if angle_units < 0:
            angle_units = 65536 + angle_units
        angle_units = max(0, min(65535, angle_units))
        return f"{angle_units:04X}"

# =============================================================================
# GUI INTERFACE
# =============================================================================

class GimbalSimulatorGUI:
    """Simple GUI for gimbal simulator control"""

    def __init__(self):
        self.simulator = GimbalSimulator()
        self.root = tk.Tk()
        self.running = True

        self.setup_gui()
        self.start_simulator()

    def setup_gui(self):
        """Setup the GUI interface"""
        self.root.title("PixEagle Gimbal Simulator")
        self.root.geometry("700x650")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Variables
        self.yaw_var = tk.DoubleVar()
        self.pitch_var = tk.DoubleVar()
        self.roll_var = tk.DoubleVar()
        self.tracking_state_var = tk.StringVar(value="DISABLED")
        self.target_mode_var = tk.StringVar(value="auto")
        self.auto_pattern_var = tk.StringVar(value="circular")
        self.target_yaw_var = tk.DoubleVar()
        self.target_pitch_var = tk.DoubleVar()

        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Gimbal controls
        gimbal_frame = ttk.LabelFrame(main_frame, text="Gimbal Control", padding="10")
        gimbal_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Yaw
        ttk.Label(gimbal_frame, text="Yaw:").grid(row=0, column=0, sticky=tk.W)
        yaw_scale = ttk.Scale(gimbal_frame, from_=-180, to=180, variable=self.yaw_var,
                             orient=tk.HORIZONTAL, length=300, command=self.on_yaw_change)
        yaw_scale.grid(row=0, column=1, padx=5)
        self.yaw_label = ttk.Label(gimbal_frame, text="0.0°")
        self.yaw_label.grid(row=0, column=2)

        # Pitch
        ttk.Label(gimbal_frame, text="Pitch:").grid(row=1, column=0, sticky=tk.W)
        pitch_scale = ttk.Scale(gimbal_frame, from_=-90, to=90, variable=self.pitch_var,
                               orient=tk.HORIZONTAL, length=300, command=self.on_pitch_change)
        pitch_scale.grid(row=1, column=1, padx=5)
        self.pitch_label = ttk.Label(gimbal_frame, text="0.0°")
        self.pitch_label.grid(row=1, column=2)

        # Roll
        ttk.Label(gimbal_frame, text="Roll:").grid(row=2, column=0, sticky=tk.W)
        roll_scale = ttk.Scale(gimbal_frame, from_=-45, to=45, variable=self.roll_var,
                              orient=tk.HORIZONTAL, length=300, command=self.on_roll_change)
        roll_scale.grid(row=2, column=1, padx=5)
        self.roll_label = ttk.Label(gimbal_frame, text="0.0°")
        self.roll_label.grid(row=2, column=2)

        # Tracking state
        state_frame = ttk.LabelFrame(main_frame, text="Tracking State", padding="10")
        state_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        states = [("Disabled", "DISABLED"), ("Selection", "TARGET_SELECTION"),
                 ("Active", "TRACKING_ACTIVE"), ("Lost", "TARGET_LOST")]
        for i, (text, value) in enumerate(states):
            ttk.Radiobutton(state_frame, text=text, variable=self.tracking_state_var,
                           value=value, command=self.on_tracking_change).grid(row=0, column=i, padx=10)

        # Target control
        target_frame = ttk.LabelFrame(main_frame, text="Target Control", padding="10")
        target_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Mode selection
        mode_frame = ttk.Frame(target_frame)
        mode_frame.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=5)

        ttk.Radiobutton(mode_frame, text="Auto Patterns", variable=self.target_mode_var,
                       value="auto", command=self.on_target_mode_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Manual Target", variable=self.target_mode_var,
                       value="manual", command=self.on_target_mode_change).pack(side=tk.LEFT, padx=5)

        # Auto pattern
        ttk.Label(target_frame, text="Pattern:").grid(row=1, column=0, sticky=tk.W)
        pattern_combo = ttk.Combobox(target_frame, textvariable=self.auto_pattern_var,
                                   values=["circular", "figure8", "random"], state="readonly", width=10)
        pattern_combo.grid(row=1, column=1, padx=5)
        pattern_combo.bind('<<ComboboxSelected>>', self.on_pattern_change)

        # Manual target controls
        ttk.Label(target_frame, text="Target Yaw:").grid(row=2, column=0, sticky=tk.W)
        target_yaw_scale = ttk.Scale(target_frame, from_=-180, to=180, variable=self.target_yaw_var,
                                   orient=tk.HORIZONTAL, length=200, command=self.on_target_yaw_change)
        target_yaw_scale.grid(row=2, column=1, padx=5)
        self.target_yaw_label = ttk.Label(target_frame, text="0.0°")
        self.target_yaw_label.grid(row=2, column=2)

        ttk.Label(target_frame, text="Target Pitch:").grid(row=3, column=0, sticky=tk.W)
        target_pitch_scale = ttk.Scale(target_frame, from_=-90, to=90, variable=self.target_pitch_var,
                                     orient=tk.HORIZONTAL, length=200, command=self.on_target_pitch_change)
        target_pitch_scale.grid(row=3, column=1, padx=5)
        self.target_pitch_label = ttk.Label(target_frame, text="0.0°")
        self.target_pitch_label.grid(row=3, column=2)

        # Visual Display
        visual_frame = ttk.LabelFrame(main_frame, text="Gimbal Visualization", padding="10")
        visual_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # Canvas frames
        canvas_frame = ttk.Frame(visual_frame)
        canvas_frame.grid(row=0, column=0, columnspan=2, pady=5)

        # Top-down view (Yaw)
        topdown_frame = ttk.Frame(canvas_frame)
        topdown_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(topdown_frame, text="Top-Down View (Yaw)", font=("Arial", 10, "bold")).pack()
        self.topdown_canvas = tk.Canvas(topdown_frame, width=150, height=150, bg="white", relief="sunken", bd=2)
        self.topdown_canvas.pack()

        # Front view (Pitch/Roll)
        front_frame = ttk.Frame(canvas_frame)
        front_frame.pack(side=tk.LEFT, padx=10)
        ttk.Label(front_frame, text="Front View (Pitch/Roll)", font=("Arial", 10, "bold")).pack()
        self.front_canvas = tk.Canvas(front_frame, width=150, height=150, bg="white", relief="sunken", bd=2)
        self.front_canvas.pack()

        # Status
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.status_text = tk.StringVar()
        status_label = ttk.Label(status_frame, textvariable=self.status_text, font=("Courier", 9))
        status_label.grid(row=0, column=0, sticky=tk.W)

        # Update thread
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()

    def start_simulator(self):
        """Start the simulator"""
        if self.simulator.start():
            logger.info("Simulator started successfully!")
            messagebox.showinfo("Success",
                "Gimbal simulator started!\n\n"
                "PixEagle Configuration:\n"
                "GIMBAL_UDP_HOST: 127.0.0.1\n"
                "GIMBAL_LISTEN_PORT: 9004\n"
                "GIMBAL_CONTROL_PORT: 9003\n\n"
                "Set tracking to 'Active' and use controls to test!")
        else:
            messagebox.showerror("Error", "Failed to start simulator")

    def update_loop(self):
        """Update GUI with current state"""
        while self.running:
            try:
                state = self.simulator.get_state()

                # Update status
                angles = state['angles']
                target = state['target']
                stats = state['stats']

                status = (f"Gimbal: Y={angles['yaw']:+6.1f}° P={angles['pitch']:+6.1f}° R={angles['roll']:+6.1f}° | "
                         f"State: {state['tracking_state']} | ")

                if state['tracking_state'] == 'TRACKING_ACTIVE':
                    mode = "Manual" if state['manual_target_mode'] else f"Auto({state['auto_pattern']})"
                    status += f"Target({mode}): Y={target['yaw']:+6.1f}° P={target['pitch']:+6.1f}° | "

                status += f"Packets: {stats['broadcasts']}"

                self.status_text.set(status)

                # Update labels
                self.yaw_label.config(text=f"{angles['yaw']:+6.1f}°")
                self.pitch_label.config(text=f"{angles['pitch']:+6.1f}°")
                self.roll_label.config(text=f"{angles['roll']:+6.1f}°")
                self.target_yaw_label.config(text=f"{target['yaw']:+6.1f}°")
                self.target_pitch_label.config(text=f"{target['pitch']:+6.1f}°")

                # Update visual displays
                self.draw_topdown_view(angles['yaw'])
                self.draw_front_view(angles['pitch'], angles['roll'])

                time.sleep(0.1)

            except Exception as e:
                logger.debug(f"Update error: {e}")

    def on_yaw_change(self, value):
        """Handle yaw change"""
        self.simulator.set_gimbal_angles(float(value), self.pitch_var.get(), self.roll_var.get())

    def on_pitch_change(self, value):
        """Handle pitch change"""
        self.simulator.set_gimbal_angles(self.yaw_var.get(), float(value), self.roll_var.get())

    def on_roll_change(self, value):
        """Handle roll change"""
        self.simulator.set_gimbal_angles(self.yaw_var.get(), self.pitch_var.get(), float(value))

    def on_tracking_change(self):
        """Handle tracking state change"""
        state_name = self.tracking_state_var.get()
        state = SimulatedTrackingState[state_name]
        self.simulator.set_tracking_state(state)

    def on_target_mode_change(self):
        """Handle target mode change"""
        mode = self.target_mode_var.get()
        if mode == "manual":
            yaw = self.target_yaw_var.get()
            pitch = self.target_pitch_var.get()
            self.simulator.set_manual_target(yaw, pitch)
        else:
            # Switch to auto mode - disable manual and set auto pattern
            pattern = self.auto_pattern_var.get()
            with self.simulator.lock:
                self.simulator.manual_target_mode = False
                self.simulator.auto_pattern = pattern

    def on_pattern_change(self, event):
        """Handle pattern change"""
        pattern = self.auto_pattern_var.get()
        # Only update pattern, don't affect manual mode
        with self.simulator.lock:
            self.simulator.auto_pattern = pattern

    def on_target_yaw_change(self, value):
        """Handle target yaw change"""
        if self.target_mode_var.get() == "manual":
            self.simulator.set_manual_target(float(value), self.target_pitch_var.get())
            logger.debug(f"Manual yaw changed to: {value}")

    def on_target_pitch_change(self, value):
        """Handle target pitch change"""
        if self.target_mode_var.get() == "manual":
            self.simulator.set_manual_target(self.target_yaw_var.get(), float(value))
            logger.debug(f"Manual pitch changed to: {value}")

    def draw_topdown_view(self, yaw_deg):
        """Draw top-down view showing yaw rotation"""
        self.topdown_canvas.delete("all")

        # Canvas dimensions
        width = 150
        height = 150
        center_x = width // 2
        center_y = height // 2
        radius = 60

        # Draw base circle (gimbal housing)
        self.topdown_canvas.create_oval(center_x - radius, center_y - radius,
                                       center_x + radius, center_y + radius,
                                       outline="gray", width=2)

        # Draw center point
        self.topdown_canvas.create_oval(center_x - 3, center_y - 3,
                                       center_x + 3, center_y + 3,
                                       fill="black")

        # Draw north indicator (fixed reference)
        self.topdown_canvas.create_line(center_x, center_y - radius - 10,
                                       center_x, center_y - radius - 5,
                                       fill="blue", width=2)
        self.topdown_canvas.create_text(center_x, center_y - radius - 15, text="N", fill="blue", font=("Arial", 8, "bold"))

        # Draw gimbal direction (yaw)
        yaw_rad = math.radians(yaw_deg)
        end_x = center_x + radius * 0.8 * math.sin(yaw_rad)
        end_y = center_y - radius * 0.8 * math.cos(yaw_rad)

        # Gimbal direction line
        self.topdown_canvas.create_line(center_x, center_y, end_x, end_y,
                                       fill="red", width=3, arrow=tk.LAST, arrowshape=(8, 10, 3))

        # Draw angle arc
        if abs(yaw_deg) > 1:
            start_angle = 90  # Start from north
            extent = -yaw_deg  # Negative for clockwise
            self.topdown_canvas.create_arc(center_x - 20, center_y - 20,
                                          center_x + 20, center_y + 20,
                                          start=start_angle, extent=extent,
                                          outline="green", width=2, style="arc")

        # Angle text
        self.topdown_canvas.create_text(center_x, center_y + radius + 15,
                                       text=f"Yaw: {yaw_deg:+.1f}°",
                                       font=("Arial", 10, "bold"))

    def draw_front_view(self, pitch_deg, roll_deg):
        """Draw front view showing pitch and roll"""
        self.front_canvas.delete("all")

        # Canvas dimensions
        width = 150
        height = 150
        center_x = width // 2
        center_y = height // 2
        size = 50

        # Draw horizon line (fixed reference)
        self.front_canvas.create_line(10, center_y, width - 10, center_y,
                                     fill="lightblue", width=2, dash=(5, 5))
        self.front_canvas.create_text(10, center_y - 10, text="Horizon", fill="lightblue", font=("Arial", 8))

        # Draw gimbal frame (affected by roll)
        roll_rad = math.radians(roll_deg)

        # Calculate rotated frame corners
        cos_roll = math.cos(roll_rad)
        sin_roll = math.sin(roll_rad)

        # Frame corners relative to center
        frame_points = [
            (-size, -size), (size, -size), (size, size), (-size, size)
        ]

        # Rotate and translate frame
        rotated_points = []
        for x, y in frame_points:
            new_x = center_x + x * cos_roll - y * sin_roll
            new_y = center_y + x * sin_roll + y * cos_roll
            rotated_points.extend([new_x, new_y])

        # Draw gimbal frame
        self.front_canvas.create_polygon(rotated_points, outline="gray", width=2, fill="")

        # Draw pitch indicator (camera direction)
        pitch_rad = math.radians(pitch_deg)
        pitch_length = 40

        # Camera direction (affected by both pitch and roll)
        cam_x = center_x + pitch_length * math.sin(pitch_rad) * cos_roll
        cam_y = center_y - pitch_length * math.cos(pitch_rad) + pitch_length * math.sin(pitch_rad) * sin_roll

        # Camera direction line
        self.front_canvas.create_line(center_x, center_y, cam_x, cam_y,
                                     fill="red", width=3, arrow=tk.LAST, arrowshape=(8, 10, 3))

        # Center point
        self.front_canvas.create_oval(center_x - 3, center_y - 3,
                                     center_x + 3, center_y + 3,
                                     fill="black")

        # Roll angle arc
        if abs(roll_deg) > 1:
            start_angle = 0
            extent = -roll_deg
            self.front_canvas.create_arc(center_x - 15, center_y - 15,
                                        center_x + 15, center_y + 15,
                                        start=start_angle, extent=extent,
                                        outline="blue", width=2, style="arc")

        # Pitch angle indicator
        if abs(pitch_deg) > 1:
            # Draw pitch arc on the side
            pitch_arc_x = center_x + 60
            start_angle = 90 if pitch_deg > 0 else 90
            extent = -pitch_deg
            self.front_canvas.create_arc(pitch_arc_x - 10, center_y - 10,
                                        pitch_arc_x + 10, center_y + 10,
                                        start=start_angle, extent=extent,
                                        outline="green", width=2, style="arc")

        # Angle text
        self.front_canvas.create_text(center_x, center_y + size + 25,
                                     text=f"Pitch: {pitch_deg:+.1f}°",
                                     font=("Arial", 9, "bold"))
        self.front_canvas.create_text(center_x, center_y + size + 40,
                                     text=f"Roll: {roll_deg:+.1f}°",
                                     font=("Arial", 9, "bold"))

    def on_closing(self):
        """Handle window closing"""
        self.running = False
        self.simulator.stop()
        self.root.destroy()

    def run(self):
        """Run the GUI"""
        self.root.mainloop()

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entry point"""
    print("=" * 60)
    print("PixEagle Gimbal Simulator")
    print("=" * 60)
    print("Starting GUI interface...")
    print()
    print("PixEagle Configuration needed:")
    print("  GIMBAL_UDP_HOST: 127.0.0.1")
    print("  GIMBAL_LISTEN_PORT: 9004")
    print("  GIMBAL_CONTROL_PORT: 9003")
    print("=" * 60)

    try:
        gui = GimbalSimulatorGUI()
        gui.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        messagebox.showerror("Error", f"Failed to start simulator: {e}")

if __name__ == "__main__":
    main()