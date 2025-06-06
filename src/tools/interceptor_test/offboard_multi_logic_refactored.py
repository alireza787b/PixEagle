#!/usr/bin/env python3
"""
Robust Offboard Pursuit of a Moving Target
with Modular Guidance Modes (Local Velocity, Global Position, Global Velocity),
Full 3D PID in CAMERA frame, Yaw Slew Limiting,
Camera Mount Extrinsics (Yaw/Pitch/Roll), and Camera-Frame Target Definition.

Features:
  - Configuration at top (future YAML).
  - User-definable camera mount yaw, pitch, and roll angles.
  - Build rotation matrix R_CAM2BODY from mount angles.
  - Moving target defined in CAMERA frame: forward (X), right (Y), down (Z).
  - Pursuit control uses PID in camera axes, rotated to body velocities.
  - Desired yaw = bearing_to_target - camera_mount_yaw.
  - Yaw-rate slew limiting for smooth camera-pointing.
  - Optional real-time 3D Matplotlib visualization with dynamic zoom, path history,
    and arrows for body X and camera X directions with guide annotation.
  - Informative console logging.
  - Modular guidance modes:
      * "local_velocity": camera-frame PID → body-velocity offboard.
      * "global_position": compute target LLA → offboard PositionGlobalYaw (AMSL).
      * "global_velocity": compute target LLA → full NED‐PID → body-velocity offboard.
  - [NEW] Built‐in Kalman filter (via FilterPy) on target NED position/velocity to handle
    intermittent target loss and smooth estimates. Automatically applied regardless of guidance mode.
"""

import asyncio
import math
import time
from enum import Enum

import numpy as np
import matplotlib.pyplot as plt
import pymap3d as pm  # for geodetic ↔ ENU conversions

# 3rd‐party Kalman filter from FilterPy
from filterpy.kalman import KalmanFilter

from mavsdk import System
from mavsdk.offboard import (
    OffboardError,
    VelocityBodyYawspeed,
    PositionNedYaw,
    PositionGlobalYaw,
)

# =============================================================================
#                            USER‐CONFIGURABLE ZONE
# =============================================================================

# CAMERA FRAME TARGET DEFINITION:
# Simulates OAK-D camera detection output in SITL
# X_cam = forward, Y_cam = right, Z_cam = down (meters)
CAM_TARGET_INIT     = np.array([20.0,  0.0, -10.0])  # 10 m above the drone
CAM_TARGET_VEL      = np.array([0.0,   0.0,   0.0])  # static target

# Camera mount extrinsics: yaw, pitch, roll (degrees)
CAM_MOUNT_YAW_DEG   = 0.0   # + rotates camera left of vehicle X+ axis
CAM_MOUNT_PITCH_DEG = 0.0   # + tilts camera nose up
CAM_MOUNT_ROLL_DEG  = 0.0   # + rolls camera clockwise looking forward

# Takeoff settings
TAKEOFF_ALTITUDE    = 5.0    # meters above home
ASCENT_SPEED        = -2.0   # m/s down rate (negative = up)

# PID gains for CAMERA‐frame X (forward), Y (right), Z (down)
KP_CAM_X, KI_CAM_X, KD_CAM_X = 0.5,  0.05, 0.1
KP_CAM_Y, KI_CAM_Y, KD_CAM_Y = 0.5,  0.05, 0.1
KP_CAM_Z, KI_CAM_Z, KD_CAM_Z = 0.5,  0.02, 0.1
CAM_Z_DEADBAND      = 0.1    # m deadband in camera Z

# Yaw control parameters (applies to all modes)
YAW_DEADBAND        = 2.0    # deg
YAW_GAIN            = 2      # deg/s per deg error
YAW_RATE_MAX        = 90.0   # deg/s
YAW_SLEW_RATE       = 150.0  # deg/s^2

# Velocity limits (body frame)
# Note: if MAX_VZ_BODY is small (1 m/s), climbing 10 m will be slow
MAX_VX_BODY, MAX_VY_BODY, MAX_VZ_BODY = 5.0, 5.0, 1.0

# Mission logic
TARGET_THRESHOLD    = 1.0    # m finish radius
HOLD_TIME_AFTER     = 3.0    # s hold at target
SETPOINT_FREQ       = 20.0   # Hz control loop
MAX_MISSION_TIME    = 120.0  # s timeout

# Visualization
ENABLE_PLOT         = True
PLOT_RATE_HZ        = 5      # update plot this many times per second
ARROW_LEN           = 2.0    # m length of direction arrows

# Guidance mode configuration:
#   "local_velocity"   → camera‐frame PID → body‐velocity offboard
#   "global_position"  → compute target LLA → offboard PositionGlobalYaw (AMSL)
#   "global_velocity"  → compute target LLA → full NED‐PID → body‐velocity offboard
GUIDANCE_MODE = "global_position"

# Kalman filter configuration (applies to all guidance modes)
USE_KALMAN          = True
KF_POS_NOISE        = 1e-1   # Process noise (position) 
KF_VEL_NOISE        = 1e-2   # Process noise (velocity)
KF_MEAS_NOISE       = 0.5    # Measurement noise (position)
KF_MISS_TIMEOUT     = 5.0    # seconds to continue predicting without measurements
# =============================================================================
#                              END CONFIGURATION
# =============================================================================


def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp val to [lo, hi]."""
    return max(lo, min(val, hi))


def normalize(angle: float) -> float:
    """Wrap angle to [-180, +180] degrees."""
    return ((angle + 180) % 360) - 180


def rotation_x(deg: float) -> np.ndarray:
    """Rotation matrix about X axis by deg degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[1, 0,  0],
                     [0, c, -s],
                     [0, s,  c]])


def rotation_y(deg: float) -> np.ndarray:
    """Rotation matrix about Y axis by deg degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[ c, 0, s],
                     [ 0, 1, 0],
                     [-s, 0, c]])


def rotation_z(deg: float) -> np.ndarray:
    """Rotation matrix about Z axis by deg degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[ c, -s, 0],
                     [ s,  c, 0],
                     [ 0,  0, 1]])


# Build camera‐to‐body extrinsics: R_CAM2BODY = R_z(yaw) @ R_y(pitch) @ R_x(roll)
R_CAM2BODY = (
    rotation_z(CAM_MOUNT_YAW_DEG)
    @ rotation_y(CAM_MOUNT_PITCH_DEG)
    @ rotation_x(CAM_MOUNT_ROLL_DEG)
)


class PIDController:
    """
    A generic PID controller.
    Stores integrator, previous error, gains, and clamps output.
    """

    def __init__(self, kp: float, ki: float, kd: float, clamp_low: float, clamp_high: float, deadband: float = 0.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.clamp_low = clamp_low
        self.clamp_high = clamp_high
        self.deadband = deadband

        self.integrator = 0.0
        self.prev_error = 0.0

    def reset(self):
        """Reset integrator and previous error."""
        self.integrator = 0.0
        self.prev_error = 0.0

    def update(self, error: float, dt: float) -> float:
        """
        Compute PID output for given error and timestep dt.
        Returns the clamped output. Applies deadband on the error if configured.
        """
        # Deadband check
        if abs(error) <= self.deadband:
            self.prev_error = error
            return 0.0

        # Integrator update
        self.integrator += error * dt

        # Derivative term
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0

        # PID formula
        output = self.kp * error + self.ki * self.integrator + self.kd * derivative

        # Clamp output
        clamped = clamp(output, self.clamp_low, self.clamp_high)

        # Anti-windup: if output was clamped, remove the last integration step
        if output != clamped:
            self.integrator -= error * dt

        # Update previous error
        self.prev_error = error

        return clamped


class FilterPyKalmanNED:
    """
    6D Kalman Filter in NED coordinates using FilterPy.
    State: [n, e, d, vn, ve, vd].
    Process model: constant‐velocity discrete.
    """

    def __init__(self, dt: float, process_noise_pos: float, process_noise_vel: float,
                 meas_noise: float, miss_timeout: float):
        # Create FilterPy KalmanFilter instance with 6‐state, 3‐measurement
        self.kf = KalmanFilter(dim_x=6, dim_z=3)

        # Time step
        self.dt = dt

        # State transition matrix F
        # [1 0 0 dt  0  0]
        # [0 1 0  0 dt  0]
        # [0 0 1  0  0 dt]
        # [0 0 0  1  0  0]
        # [0 0 0  0  1  0]
        # [0 0 0  0  0  1]
        self.kf.F = np.array([
            [1, 0, 0, dt,  0,  0],
            [0, 1, 0,  0, dt,  0],
            [0, 0, 1,  0,  0, dt],
            [0, 0, 0,  1,  0,  0],
            [0, 0, 0,  0,  1,  0],
            [0, 0, 0,  0,  0,  1],
        ])

        # Measurement function H: we measure position only
        self.kf.H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0],
        ])

        # Initial state covariance
        self.kf.P = np.eye(6) * 1.0

        # Process noise covariance Q
        q_pos = process_noise_pos
        q_vel = process_noise_vel
        dt2, dt3, dt4 = dt**2, dt**3, dt**4

        Q_pos = q_pos * np.array([
            [dt4/4, dt3/2,    0],
            [dt3/2, dt2,      0],
            [0,     0,     dt2],
        ])
        Q_vel = q_vel * np.eye(3) * dt2

        self.kf.Q = np.block([
            [Q_pos,        np.zeros((3, 3))],
            [np.zeros((3, 3)), Q_vel      ]
        ])

        # Measurement noise covariance R
        self.kf.R = np.eye(3) * meas_noise**2

        # Last update time, for missing‐data logic
        self.last_update_time = time.time()
        self.miss_timeout = miss_timeout

    def predict(self, dt: float):
        """
        Predict step with possibly updated dt.
        If dt changes significantly, recompute F and Q accordingly.
        """
        if abs(dt - self.dt) > 1e-6:
            self.dt = dt
            # Rebuild F, Q with new dt
            dt2, dt3, dt4 = dt**2, dt**3, dt**4
            self.kf.F = np.array([
                [1, 0, 0, dt,  0,  0],
                [0, 1, 0,  0, dt,  0],
                [0, 0, 1,  0,  0, dt],
                [0, 0, 0,  1,  0,  0],
                [0, 0, 0,  0,  1,  0],
                [0, 0, 0,  0,  0,  1],
            ])
            Q_pos = KF_POS_NOISE * np.array([
                [dt4/4, dt3/2,    0],
                [dt3/2, dt2,      0],
                [0,     0,     dt2],
            ])
            Q_vel = KF_VEL_NOISE * np.eye(3) * dt2
            self.kf.Q = np.block([
                [Q_pos,        np.zeros((3, 3))],
                [np.zeros((3, 3)), Q_vel      ]
            ])

        # Standard predict
        self.kf.predict()

    def update(self, measurement: np.ndarray or None):
        """
        Update step if measurement is provided; else skip if timed out.
        measurement: 3‐vector [n, e, d] or None.
        """
        now = time.time()
        if measurement is not None:
            z = measurement.reshape((3, 1))
            self.kf.update(z)
            self.last_update_time = now
        else:
            # If no measurement and too long since last update, skip update
            if now - self.last_update_time > self.miss_timeout:
                # Do nothing (pure prediction)
                pass

    def step(self, measurement: np.ndarray or None, dt: float):
        """
        Single iteration: predict then update (if measurement present).
        Returns (pos_est, vel_est), each 3‐vector.
        """
        self.predict(dt)
        self.update(measurement)
        x = self.kf.x.flatten()
        pos_est = x[0:3]  # [n, e, d]
        vel_est = x[3:6]  # [vn, ve, vd]
        return pos_est, vel_est


class PlotUpdater:
    """
    Encapsulates all plotting logic:
      - Initializes 3D plot
      - Updates path lines, scatter points, arrows, zoom
    """

    def __init__(self):
        # Initialize interactive plotting
        plt.ion()
        self.fig = plt.figure()
        self.ax = self.fig.add_subplot(projection='3d')

        # Drone/target path lines
        self.drone_line, = self.ax.plot([], [], [], c='blue', label='Drone Path')
        self.tgt_line,   = self.ax.plot([], [], [], c='red',  label='Target Path')

        # Drone/target scatter markers
        self.drone_scatter = self.ax.scatter([], [], [], c='blue', s=50)
        self.tgt_scatter   = self.ax.scatter([], [], [], c='red',  s=50)

        # Engagement text box
        self.engagement_text = self.ax.text2D(0.02, 0.95, "", transform=self.ax.transAxes)

        # Axis labels & legend
        self.ax.set_xlabel('North (m)')
        self.ax.set_ylabel('East (m)')
        self.ax.set_zlabel('Down (m)')
        self.ax.legend()

        # Invert Z-axis so that negative-down (higher altitude) appears upward
        self.ax.invert_zaxis()

        # Placeholder arrows for drone body-X (blue) and camera-X (cyan)
        self.drone_arrow = self.ax.quiver(0, 0, 0, 0, 0, 0)
        self.cam_arrow   = self.ax.quiver(0, 0, 0, 0, 0, 0, color='cyan')

        # Store path history
        self.path_drone = []
        self.path_tgt = []
        self.zoom_margin = 2.0
        self.last_plot_time = 0.0

    def initialize(self, n0, e0, d0, target_n, target_e, target_d, yaw_rad):
        """
        Initial draw of drone & target positions and arrows.
        Must be called once before main loop.
        """
        # Initialize path lists
        self.path_drone = [(n0, e0, d0)]
        self.path_tgt = [(target_n, target_e, target_d)]

        # Draw initial path lines
        self.drone_line.set_data([n0], [e0])
        self.drone_line.set_3d_properties([d0])
        self.tgt_line.set_data([target_n], [target_e])
        self.tgt_line.set_3d_properties([target_d])

        # Draw initial scatter points
        self.drone_scatter._offsets3d = ([n0], [e0], [d0])
        self.tgt_scatter._offsets3d   = ([target_n], [target_e], [target_d])

        # Draw initial arrows
        self.drone_arrow.remove()
        self.cam_arrow.remove()
        self.drone_arrow = self.ax.quiver(
            n0, e0, d0,
            math.cos(yaw_rad), math.sin(yaw_rad), 0,
            length=ARROW_LEN, normalize=True
        )
        yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
        self.cam_arrow = self.ax.quiver(
            n0, e0, d0,
            math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0,
            length=ARROW_LEN, normalize=True, color='cyan'
        )

        plt.draw()
        plt.pause(0.001)
        self.last_plot_time = time.time()

    def update(self, cn, ce, cd, target_n, target_e, target_d, yaw_rad, dist, speed, eta, chi):
        """
        Update the plot with new drone/target positions, arrows, and dynamic zoom.
        Only updates if enough time has passed since last update (PLOT_RATE_HZ).
        """
        now = time.time()
        if now - self.last_plot_time < 1.0 / PLOT_RATE_HZ:
            return

        # Append current positions
        self.path_drone.append((cn, ce, cd))
        self.path_tgt.append((target_n, target_e, target_d))

        # Unpack path lists
        dn, de, dd = zip(*self.path_drone)
        tn, te, td = zip(*self.path_tgt)

        # Update path lines
        self.drone_line.set_data(dn, de)
        self.drone_line.set_3d_properties(dd)
        self.tgt_line.set_data(tn, te)
        self.tgt_line.set_3d_properties(td)

        # Update scatter points
        self.drone_scatter._offsets3d = ([cn], [ce], [cd])
        self.tgt_scatter._offsets3d   = ([target_n], [target_e], [target_d])

        # Update engagement text
        self.engagement_text.set_text(f"Dist={dist:.2f}m, Speed={speed:.2f}m/s, ETA={eta:.1f}s")

        # Redraw arrows
        self.drone_arrow.remove()
        self.cam_arrow.remove()
        self.drone_arrow = self.ax.quiver(
            cn, ce, cd,
            math.cos(yaw_rad), math.sin(yaw_rad), 0,
            length=ARROW_LEN, normalize=True
        )
        yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
        self.cam_arrow = self.ax.quiver(
            cn, ce, cd,
            math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0,
            length=ARROW_LEN, normalize=True, color='cyan'
        )

        # Dynamic zoom (Z-axis inverted)
        all_n = np.array(dn + tn)
        all_e = np.array(de + te)
        all_d = np.array(dd + td)
        self.ax.set_xlim(all_n.min() - self.zoom_margin, all_n.max() + self.zoom_margin)
        self.ax.set_ylim(all_e.min() - self.zoom_margin, all_e.max() + self.zoom_margin)
        # Because z-axis is inverted, reverse the limits
        self.ax.set_zlim(all_d.max() + self.zoom_margin, all_d.min() - self.zoom_margin)

        plt.draw()
        plt.pause(0.001)
        self.last_plot_time = now


class GuidanceMode(Enum):
    LOCAL_VELOCITY = "local_velocity"
    GLOBAL_POSITION = "global_position"
    GLOBAL_VELOCITY = "global_velocity"


class GuidanceDispatcher:
    """
    Dispatches to the appropriate guidance function based on GUIDANCE_MODE.
    """

    def __init__(self):
        # PID controllers for camera‐frame errors
        self.pid_cam_x = PIDController(KP_CAM_X, KI_CAM_X, KD_CAM_X,
                                       -MAX_VX_BODY, MAX_VX_BODY, deadband=0.0)
        self.pid_cam_y = PIDController(KP_CAM_Y, KI_CAM_Y, KD_CAM_Y,
                                       -MAX_VY_BODY, MAX_VY_BODY, deadband=0.0)
        self.pid_cam_z = PIDController(KP_CAM_Z, KI_CAM_Z, KD_CAM_Z,
                                       -MAX_VZ_BODY, MAX_VZ_BODY, deadband=CAM_Z_DEADBAND)

        # PID controllers for NED‐frame errors (used only in global_velocity)
        self.pid_n = PIDController(KP_CAM_X, KI_CAM_X, KD_CAM_X,
                                   -MAX_VX_BODY, MAX_VX_BODY, deadband=0.0)
        self.pid_e = PIDController(KP_CAM_Y, KI_CAM_Y, KD_CAM_Y,
                                   -MAX_VY_BODY, MAX_VY_BODY, deadband=0.0)
        self.pid_d = PIDController(KP_CAM_Z, KI_CAM_Z, KD_CAM_Z,
                                   -MAX_VZ_BODY, MAX_VZ_BODY, deadband=CAM_Z_DEADBAND)

    def reset_all(self):
        """Reset all PID controllers."""
        self.pid_cam_x.reset()
        self.pid_cam_y.reset()
        self.pid_cam_z.reset()
        self.pid_n.reset()
        self.pid_e.reset()
        self.pid_d.reset()

    async def local_velocity(self, drone: System, err_body: np.ndarray,
                             dt: float, yaw_rate: float):
        """
        Local Velocity Mode:
          - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
          - dt: timestep
          - yaw_rate: commanded yaw‐rate (deg/s)
        Action: Run camera‐frame PID → BODY velocities → send set_velocity_body.
        """
        # Rotate error into camera frame
        err_cam = R_CAM2BODY.T.dot(err_body)
        err_x, err_y, err_z = err_cam

        # Compute PID output in camera axes
        u_cam_x = self.pid_cam_x.update(err_x, dt)
        u_cam_y = self.pid_cam_y.update(err_y, dt)
        u_cam_z = self.pid_cam_z.update(err_z, dt)

        # Rotate camera‐PID output → BODY frame velocities
        vel_body = R_CAM2BODY.dot(np.array([u_cam_x, u_cam_y, u_cam_z]))

        # Send BODY‐velocity + yaw_rate
        try:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(
                    vel_body[0],
                    vel_body[1],
                    vel_body[2],
                    yaw_rate
                )
            )
        except OffboardError as e:
            print(f"[ERROR] Local Velocity command failed: {e}")

    async def global_position(self, drone: System, err_body: np.ndarray,
                              yaw_rad: float, desired_yaw_body: float):
        """
        Global Position Mode (AMSL):
          - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
          - yaw_rad: current yaw in radians.
          - desired_yaw_body: desired vehicle yaw (deg) to point camera at target.
        Action: compute target LLA (ENU→geodetic, AMSL) and send PositionGlobalYaw.
        """
        # 1) Fetch current LLA + NED (using AMSL)
        lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)

        # 2) BODY → WORLD NED offset
        offset_n, offset_e, offset_d = cam_to_world(err_body, yaw_rad)

        # 3) NED → ENU conversion (pymap3d expects ENU)
        enu_e = offset_e
        enu_n = offset_n
        enu_u = -offset_d  # down positive → up negative

        # 4) ENU → geodetic (target LLA, AMSL)
        tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
            enu_e, enu_n, enu_u,
            lat_cur, lon_cur, alt_cur,
            deg=True
        )

        # 5) Send global‐position setpoint + yaw (AMSL mode)
        gp = PositionGlobalYaw(
            tgt_lat,
            tgt_lon,
            tgt_alt,
            desired_yaw_body,
            PositionGlobalYaw.AltitudeType.AMSL  # explicitly use AMSL
        )
        try:
            await drone.offboard.set_position_global(gp)
        except OffboardError as e:
            print(f"[ERROR] Global Position command failed: {e}")

    async def global_velocity(self, drone: System, err_body: np.ndarray,
                              dt: float, yaw_rad: float, yaw_rate: float):
        """
        Global Velocity Mode:
          - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
          - dt: timestep
          - yaw_rad: current yaw in radians.
          - yaw_rate: commanded yaw‐rate (deg/s).
        Action:
          1) Compute target LLA (ENU→geodetic, AMSL).
          2) Convert that LLA → NED offset (geodetic2enu).
          3) FULL NED‐PID on (offset_n2, offset_e2, offset_d2) using camera gains.
          4) Rotate NED‐PID result → BODY velocities, send set_velocity_body.
          5) Yaw slew‐limit so camera X always points at target.
        """
        # 1) Fetch current LLA + NED
        lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)

        # 2) BODY → WORLD NED offset
        offset_n, offset_e, offset_d = cam_to_world(err_body, yaw_rad)

        # 3) NED → ENU
        enu_e = offset_e
        enu_n = offset_n
        enu_u = -offset_d  # down positive → up negative

        # 4) ENU → geodetic (target LLA, AMSL)
        tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
            enu_e, enu_n, enu_u,
            lat_cur, lon_cur, alt_cur,
            deg=True
        )

        # 5) geodetic → ENU (back conversion) to get truly consistent NED offset
        enu_e_back, enu_n_back, enu_u_back = pm.geodetic2enu(
            tgt_lat, tgt_lon, tgt_alt,
            lat_cur, lon_cur, alt_cur,
            deg=True
        )
        offset_n2 = enu_n_back
        offset_e2 = enu_e_back
        offset_d2 = -enu_u_back

        # 6) FULL PID on NED offset (north, east, down) using camera gains
        u_n_cl = self.pid_n.update(offset_n2, dt)
        u_e_cl = self.pid_e.update(offset_e2, dt)
        u_d_cl = self.pid_d.update(offset_d2, dt)

        # 7) Rotate NED‐velocity → BODY‐velocity
        u_x_body = u_n_cl * math.cos(yaw_rad) + u_e_cl * math.sin(yaw_rad)
        u_y_body = -u_n_cl * math.sin(yaw_rad) + u_e_cl * math.cos(yaw_rad)
        u_z_body = u_d_cl

        # 8) Send BODY‐velocity + yaw_rate to PX4
        try:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(
                    u_x_body,
                    u_y_body,
                    u_z_body,
                    yaw_rate
                )
            )
        except OffboardError as e:
            print(f"[ERROR] Global Velocity command failed: {e}")

    async def dispatch(self, drone: System, err_body: np.ndarray, dt: float,
                       yaw_rad: float, yaw_rate: float, desired_yaw_body: float):
        """
        Call the appropriate guidance function based on GUIDANCE_MODE.
        """
        mode = GUIDANCE_MODE
        if mode == GuidanceMode.LOCAL_VELOCITY.value:
            await self.local_velocity(drone, err_body, dt, yaw_rate)
        elif mode == GuidanceMode.GLOBAL_POSITION.value:
            await self.global_position(drone, err_body, yaw_rad, desired_yaw_body)
        elif mode == GuidanceMode.GLOBAL_VELOCITY.value:
            await self.global_velocity(drone, err_body, dt, yaw_rad, yaw_rate)
        else:
            print(f"[ERROR] Invalid GUIDANCE_MODE “{mode}”. Defaulting to local_velocity.")
            await self.local_velocity(drone, err_body, dt, yaw_rate)


# =============================================================================
#                                   UTILITIES
# =============================================================================

async def get_lla_ned(drone: System):
    """
    Get latest LLA (latitude, longitude, altitude) and NED position.
    Uses absolute AMSL altitude for "alt_m".
    Returns:
      lat_deg, lon_deg, alt_m (AMSL), north_m, east_m, down_m
    """
    # 1) Fetch geodetic position (absolute_altitude_m = AMSL)
    async for pos in drone.telemetry.position():
        lat_deg = pos.latitude_deg
        lon_deg = pos.longitude_deg
        alt_m   = pos.absolute_altitude_m  # altitude above mean sea level (m)
        break

    # 2) Fetch NED position (down is positive)
    async for pv in drone.telemetry.position_velocity_ned():
        n = pv.position.north_m
        e = pv.position.east_m
        d = pv.position.down_m
        return lat_deg, lon_deg, alt_m, n, e, d


async def get_yaw(drone: System):
    """Get latest yaw: returns (yaw_deg, yaw_rad)."""
    async for att in drone.telemetry.attitude_euler():
        return att.yaw_deg, math.radians(att.yaw_deg)


async def get_position_velocity(drone: System):
    """Get latest position+velocity telemetry (for ground speed)."""
    async for pv in drone.telemetry.position_velocity_ned():
        return pv


def init_plot():
    """
    Initialize 3D plot with:
      - drone path (blue line), target path (red line)
      - current drone/target positions (scatter)
      - engagement text box (Distance, Speed, ETA)
      - placeholder arrows for drone body-X (blue) and camera-X (cyan).
      - **Invert Z-axis** so that higher altitude (more negative down) plots upward.
    Returns all handles for updating.
    """
    plotter = PlotUpdater()
    return plotter


def cam_to_world(vec: np.ndarray, yaw_rad: float):
    """
    Convert a vector in BODY frame to WORLD NED frame.
    vec: (bx, by, bz) in BODY (forward, right, down).
    yaw_rad: current vehicle yaw in radians (zero means nose→north).
    Returns: (dn, de, dd) in WORLD NED.
    """
    bx, by, bz = vec
    dn = bx * math.cos(yaw_rad) - by * math.sin(yaw_rad)
    de = bx * math.sin(yaw_rad) + by * math.cos(yaw_rad)
    dd = bz  # down in body = down in NED
    return dn, de, dd


# =============================================================================
#                                   MAIN
# =============================================================================

async def main():
    # Instantiate dispatcher and optionally plot updater
    dispatcher = GuidanceDispatcher()
    plotter = None
    if ENABLE_PLOT:
        plotter = init_plot()

    # Initialize Kalman filter if enabled
    kf = None
    if USE_KALMAN:
        kf = FilterPyKalmanNED(
            dt=1.0/SETPOINT_FREQ,
            process_noise_pos=KF_POS_NOISE,
            process_noise_vel=KF_VEL_NOISE,
            meas_noise=KF_MEAS_NOISE,
            miss_timeout=KF_MISS_TIMEOUT,
        )

    # --- connect & arm ---
    drone = System()
    await drone.connect(system_address="udp://:14540")
    print("[INFO] Connecting to PX4 SITL...")

    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("[INFO] Vehicle ready for Offboard.")
            break

    print("[ACTION] Arming and holding...")
    await drone.action.hold()
    await drone.action.arm()

    try:
        # Start offboard in velocity mode
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
        await drone.offboard.start()
        print("[OFFBOARD] Engaged.")
    except OffboardError as e:
        print(f"[ERROR] Offboard start failed: {e._result.result}")
        return

    # --- takeoff ---
    print(f"[TAKEOFF] Ascending to {TAKEOFF_ALTITUDE:.1f} m...", end='\r', flush=True)
    last_log = time.time()
    while True:
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, ASCENT_SPEED, 0))
        # Check altitude via NED
        _, _, _, _, _, down = await get_lla_ned(drone)
        alt = -down  # negative‐down = altitude above home
        now = time.time()
        if now - last_log >= 1.0:
            print(f"[TAKEOFF] Altitude: {alt:.2f} m", end='\r', flush=True)
            last_log = now
        if alt >= TAKEOFF_ALTITUDE:
            print(f"\n[INFO] Reached altitude {alt:.2f} m")
            break
        await asyncio.sleep(1 / SETPOINT_FREQ)

    # Hover briefly
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))

    # --- record home state ---
    lat0, lon0, alt0, n0, e0, d0 = await get_lla_ned(drone)
    yaw_deg, yaw_rad = await get_yaw(drone)
    print(
        f"[DATA] Home LLA=({lat0:.6f},{lon0:.6f},{alt0:.2f} m AMSL), "
        f"NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°"
    )

    # --- Force yaw to 0 (face true North) for initial camera‐to‐world mapping ---
    print(f"[ACTION] Yaw to 0.0° (true North) for initial camera→world mapping...", end='\r', flush=True)
    await drone.offboard.set_position_ned(PositionNedYaw(n0, e0, d0, 0.0))
    await asyncio.sleep(2.0)
    print(f"\n[INFO] Yaw aligned to 0.0°")

    # After yaw is zero, fetch yaw again (should be ~0)
    yaw_deg, yaw_rad = await get_yaw(drone)

    # --- prepare initial world‐frame target ---
    # (Now yaw_rad = 0, so forward = +North)
    body_init = R_CAM2BODY.dot(CAM_TARGET_INIT)
    body_vel  = R_CAM2BODY.dot(CAM_TARGET_VEL)

    dn0, de0, dd0 = cam_to_world(body_init, yaw_rad)
    target_n, target_e, target_d = n0 + dn0, e0 + de0, d0 + dd0
    vel_n, vel_e, vel_d         = cam_to_world(body_vel, yaw_rad)

    print(f"[COMPUTE] Initial world target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})")

    # Initialize Kalman filter state if enabled
    if kf:
        meas = np.array([target_n, target_e, target_d])
        kf.kf.x[0:3] = meas.reshape((3, 1))  # set initial position
        kf.kf.x[3:6] = np.zeros((3, 1))      # assume zero initial velocity
        kf.kf.P = np.eye(6) * 1.0
        kf.last_update_time = time.time()

    # --- initial yaw align for camera‐facing (again) ---
    raw_bearing = math.degrees(math.atan2(target_e - e0, target_n - n0))
    desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
    print(f"[ACTION] Yaw to {desired_yaw_body:.1f}° for camera‐facing...", end='\r', flush=True)
    await drone.offboard.set_position_ned(PositionNedYaw(n0, e0, d0, desired_yaw_body))
    await asyncio.sleep(2.0)
    print(f"\n[INFO] Yaw aligned to {desired_yaw_body:.1f}°")

    # --- setup plot ---
    if plotter:
        plotter.initialize(n0, e0, d0, target_n, target_e, target_d, yaw_rad)

    # --- initialize PID state variables ---
    dispatcher.reset_all()

    prev_time = start_time = time.time()
    prev_yaw_rate = 0.0

    # Print header once (above dynamic updates)
    print("Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg) | tgt lat | tgt lon | tgt alt (m AMSL)")

    # --- pursuit loop ---
    while True:
        now = time.time()
        dt = now - prev_time
        prev_time = now

        # 1) Propagate simulated target in world NED (for SITL simulation)
        target_n += vel_n * dt
        target_e += vel_e * dt
        target_d += vel_d * dt

        # 2) Telemetry: yaw + ground speed
        yaw_deg, yaw_rad = await get_yaw(drone)
        pv = await get_position_velocity(drone)
        vn, ve = pv.velocity.north_m_s, pv.velocity.east_m_s

        # 3) Depending on GUIDANCE_MODE, fetch LLA+NED or only NED
        if GUIDANCE_MODE in (GuidanceMode.GLOBAL_POSITION.value,
                             GuidanceMode.GLOBAL_VELOCITY.value):
            lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)
        else:
            # local_velocity mode: ignore LLA fields
            _, _, _, cn, ce, cd = await get_lla_ned(drone)
            lat_cur = lon_cur = alt_cur = None

        # 4) Compute relative vector in NED & distance/ETA
        rel_n = target_n - cn
        rel_e = target_e - ce
        rel_d = target_d - cd
        dist = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
        speed = math.hypot(vn, ve)
        eta = dist / speed if speed > 0.1 else float('inf')

        # 5) Compute error in BODY frame: rotate NED error by yaw
        err_body = np.array([
            rel_n * math.cos(yaw_rad) + rel_e * math.sin(yaw_rad),
            -rel_n * math.sin(yaw_rad) + rel_e * math.cos(yaw_rad),
            rel_d
        ])

        # 6) Always apply Kalman filter to smooth target NED (if enabled)
        if USE_KALMAN and kf:
            measurement = np.array([target_n, target_e, target_d])
            est_pos, est_vel = kf.step(measurement, dt)
            # Overwrite target NED with filtered estimate
            target_n, target_e, target_d = est_pos
            # Recompute relative vector using filtered position
            rel_n = target_n - cn
            rel_e = target_e - ce
            rel_d = target_d - cd
            err_body = np.array([
                rel_n * math.cos(yaw_rad) + rel_e * math.sin(yaw_rad),
                -rel_n * math.sin(yaw_rad) + rel_e * math.cos(yaw_rad),
                rel_d
            ])
        else:
            # If no measurement (should not happen in SITL), simply predict
            if USE_KALMAN and kf:
                kf.predict(dt)

        # 7) Compute desired yaw so camera X always points at target
        raw_bearing = math.degrees(math.atan2(rel_e, rel_n))
        desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
        chi = normalize(desired_yaw_body - yaw_deg)
        raw_rate = clamp(chi * YAW_GAIN, -YAW_RATE_MAX, YAW_RATE_MAX) \
            if abs(chi) > YAW_DEADBAND else 0.0
        max_d = YAW_SLEW_RATE * dt
        yaw_rate = prev_yaw_rate + clamp(raw_rate - prev_yaw_rate, -max_d, max_d)
        prev_yaw_rate = yaw_rate

        # 8) Prepare variables for in‐line printing of target LLA (AMSL)
        tgt_lat = tgt_lon = tgt_alt = None
        if GUIDANCE_MODE in (GuidanceMode.GLOBAL_POSITION.value,
                             GuidanceMode.GLOBAL_VELOCITY.value):
            offset_n, offset_e, offset_d = cam_to_world(err_body, yaw_rad)
            enu_e = offset_e
            enu_n = offset_n
            enu_u = -offset_d
            tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
                enu_e, enu_n, enu_u,
                lat_cur, lon_cur, alt_cur,
                deg=True
            )

        # 9) Dispatch to chosen guidance mode
        await dispatcher.dispatch(drone, err_body, dt, yaw_rad, yaw_rate, desired_yaw_body)

        # 10) Dynamic single‐line console log including "TARGET LLA" in‐line
        if GUIDANCE_MODE in (GuidanceMode.GLOBAL_POSITION.value,
                             GuidanceMode.GLOBAL_VELOCITY.value):
            print(
                f"{now - start_time:7.1f} | {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi:6.1f} | "
                f"{tgt_lat:.6f} | {tgt_lon:.6f} | {tgt_alt:.2f} m AMSL",
                end='\r', flush=True
            )
        else:
            print(
                f"{now - start_time:7.1f} | {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi:6.1f}",
                end='\r', flush=True
            )

        # 11) Mission end checks
        if now - start_time > MAX_MISSION_TIME:
            print("\n[ERROR] Mission timeout.")
            break
        if dist <= TARGET_THRESHOLD:
            print(f"\n[INFO] Reached target (dist={dist:.2f} m)")
            break

        # 12) Update plot if enabled
        if plotter:
            plotter.update(cn, ce, cd, target_n, target_e, target_d,
                           yaw_rad, dist, speed, eta, chi)

        await asyncio.sleep(1 / SETPOINT_FREQ)

    # --- finish: hold & RTL ---
    print(f"[ACTION] Holding for {HOLD_TIME_AFTER:.1f} s")
    await asyncio.sleep(HOLD_TIME_AFTER)
    print("[OFFBOARD] Stopping & RTL")
    await drone.offboard.stop()
    await drone.action.return_to_launch()
    print("[COMPLETE] RTL initiated.")


if __name__ == "__main__":
    asyncio.run(main())
