#!/usr/bin/env python3
"""
Robust Offboard Pursuit of a Moving Target
with Modular Guidance Modes,
Built-in Kalman Filtering & 3D Visualization,
and NED-Frame Velocity Commands + Desired Yaw.

Usage:
  - Configure params in the "USER-CONFIGURABLE ZONE"
  - Select GUIDANCE_MODE (local_velocity, global_position, global_velocity, pn)
  - Toggle USE_KALMAN to enable/disable target filtering

Features:
  • Synthetic target defined in CAMERA frame (X forward, Y right, Z down)
  • Camera mount extrinsics (yaw/pitch/roll) applied to transform to body
  • Guidance strategies dispatchable via uniform interface
  • PID controllers for camera- & NED-frame errors
  • Optional FilterPy Kalman filter for target smoothing and dropout handling
  • Direct NED velocity commands (VelocityNedYaw) with explicit yaw angle
  • 3D Matplotlib visualization with dynamic zoom, path history, and arrows
  • Informative logging and console metrics

Requirements:
  • Python 3.7+
  • mavsdk
  • filterpy
  • numpy
  • pymap3d
  • matplotlib

"""

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Type

import matplotlib.pyplot as plt
import numpy as np
import pymap3d as pm
from filterpy.kalman import KalmanFilter
from mavsdk import System
from mavsdk.offboard import (
    OffboardError,
    PositionGlobalYaw,
    PositionNedYaw,
    VelocityNedYaw,
)

# =============================================================================
#                          USER-CONFIGURABLE ZONE
# =============================================================================
# Offboard timing & mission parameters
TAKEOFF_ALTITUDE = 5.0    # meters above home position
ASCENT_SPEED     = -2.0   # m/s (negative = ascend)
SETPOINT_FREQ    = 20.0   # control loop frequency (Hz)
MAX_MISSION_TIME = 120.0  # mission timeout (s)
TARGET_THRESHOLD = 3.0    # target acceptance radius (m)
HOLD_TIME_AFTER  = 3.0    # hold time at target (s)

# Simulated target in CAMERA frame: X forward, Y right, Z down (m)
CAM_TARGET_INIT = np.array([20.0, 0.0, -10.0])  
CAM_TARGET_VEL  = np.array([1.0,  0.0,   0.0])  

# Camera mount extrinsics (degrees)
CAM_MOUNT_YAW_DEG   = 90.0  # camera yaw offset relative to vehicle X+
CAM_MOUNT_PITCH_DEG = 0.0
CAM_MOUNT_ROLL_DEG  = 0.0

# PID gains for camera-frame axes: X (forward), Y (right), Z (down)
KP_CAM_X, KI_CAM_X, KD_CAM_X = 0.5, 0.05, 0.1
KP_CAM_Y, KI_CAM_Y, KD_CAM_Y = 0.5, 0.05, 0.1
KP_CAM_Z, KI_CAM_Z, KD_CAM_Z = 0.5, 0.02, 0.1
CAM_Z_DEADBAND = 0.1         # deadband for Z-axis (m)

# Maximum allowed velocities in body frame (m/s)
MAX_VX_BODY, MAX_VY_BODY, MAX_VZ_BODY = 5.0, 5.0, 1.0

# Visualization parameters
ENABLE_PLOT  = True
PLOT_RATE_HZ = 5
ARROW_LEN    = 2.0  # arrow length for orientation indicators (m)

# Guidance mode selection:
#   "local_velocity"  → camera-frame PID → NED velocity offboard
#   "global_position" → compute geo setpoint → PositionGlobalYaw
#   "global_velocity" → full NED-PID → NED velocity offboard
#   "pn"              → stub for Proportional Navigation
GUIDANCE_MODE = "global_velocity"

# Kalman filter settings (applies to all guidance modes)
USE_KALMAN      = True   # enable synthetic target smoothing
KF_POS_NOISE    = 1e-1   # process noise density for position
KF_VEL_NOISE    = 1e-2   # process noise density for velocity
KF_MEAS_NOISE   = 0.5    # measurement noise (position)
KF_MISS_TIMEOUT = 5.0    # seconds to continue predicting without updates
# =============================================================================
#                                LOGGER SETUP
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# =============================================================================
#                              UTILITIES & MATH
# =============================================================================
def clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value to the interval [lo, hi]."""
    return max(lo, min(hi, val))

def normalize(angle: float) -> float:
    """Wrap an angle in degrees to [-180, +180]."""
    return ((angle + 180) % 360) - 180

def rotation_x(deg: float) -> np.ndarray:
    """Build a rotation matrix about the X-axis by `deg` degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[1, 0,  0],
                     [0, c, -s],
                     [0, s,  c]])

def rotation_y(deg: float) -> np.ndarray:
    """Build a rotation matrix about the Y-axis by `deg` degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[ c, 0, s],
                     [ 0, 1, 0],
                     [-s, 0, c]])

def rotation_z(deg: float) -> np.ndarray:
    """Build a rotation matrix about the Z-axis by `deg` degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[ c, -s, 0],
                     [ s,  c, 0],
                     [ 0,  0, 1]])

# Pre-computed camera→body extrinsic rotation
R_CAM2BODY = (
    rotation_z(CAM_MOUNT_YAW_DEG)
    @ rotation_y(CAM_MOUNT_PITCH_DEG)
    @ rotation_x(CAM_MOUNT_ROLL_DEG)
)

def cam_to_world(vec: np.ndarray, yaw_rad: float) -> Tuple[float, float, float]:
    """
    Transform a vector in BODY frame to WORLD NED frame:
      vec = [forward, right, down]
      yaw_rad = vehicle heading (rad) relative to North

    Returns (north_offset, east_offset, down_offset)
    """
    bx, by, bz = vec
    dn = bx * math.cos(yaw_rad) - by * math.sin(yaw_rad)
    de = bx * math.sin(yaw_rad) + by * math.cos(yaw_rad)
    dd = bz
    return dn, de, dd

# =============================================================================
#                                PID CONTROLLER
# =============================================================================

class PIDController:
    """
    Generic PID with deadband and anti-windup.

    kp, ki, kd  → gains
    lo, hi      → output clamping
    deadband    → error range to ignore
    """
    def __init__(self, kp, ki, kd, lo, hi, deadband=0.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.lo, self.hi, self.deadband = lo, hi, deadband
        self.integral = 0.0
        self.prev_error = 0.0

    def reset(self) -> None:
        """Zero integrator & previous error."""
        self.integral = 0.0
        self.prev_error = 0.0

    def update(self, error: float, dt: float) -> float:
        """
        Compute PID output for given error & dt.
        Applies deadband, clamps, and anti-windup.
        Returns clamped control.
        """
        if abs(error) <= self.deadband:
            self.prev_error = error
            return 0.0

        self.integral += error * dt
        derivative = (error - self.prev_error) / dt if dt > 0 else 0.0
        raw = self.kp*error + self.ki*self.integral + self.kd*derivative
        out = clamp(raw, self.lo, self.hi)
        if out != raw:
            # anti-windup
            self.integral -= error * dt
        self.prev_error = error
        return out

# =============================================================================
#                             KALMAN FILTER (FilterPy)
# =============================================================================

class FilterPyKalmanNED:
    """
    6D constant-velocity Kalman filter in NED coordinates.

    State vector: [n, e, d, vn, ve, vd]
    Measures position only (n,e,d).
    Missed-measurement logic: pure predict until MISS_TIMEOUT
    """
    def __init__(self,
                 dt: float,
                 q_pos: float,
                 q_vel: float,
                 r_meas: float,
                 miss_timeout: float):
        self.dt = dt
        self.kf = KalmanFilter(dim_x=6, dim_z=3)
        F = np.eye(6)
        F[0,3] = F[1,4] = F[2,5] = dt
        self.kf.F = F
        self.kf.H = np.block([np.eye(3), np.zeros((3,3))])
        self.kf.P = np.eye(6)

        # Process noise Q
        dt2, dt3, dt4 = dt**2, dt**3, dt**4
        Qp = q_pos * np.array([[dt4/4, dt3/2,    0],
                                [dt3/2, dt2,      0],
                                [0,     0,     dt2]])
        Qv = q_vel * np.eye(3) * dt2
        self.kf.Q = np.block([[Qp,        np.zeros((3,3))],
                              [np.zeros((3,3)), Qv       ]])

        # Measurement noise R
        self.kf.R = np.eye(3) * (r_meas**2)

        self.miss_timeout = miss_timeout
        self.last_update = time.time()

    def predict(self, dt: float) -> None:
        """Perform Kalman predict; no dynamic F/Q rebuild for brevity."""
        self.kf.predict()

    def update(self, meas: Optional[np.ndarray]) -> None:
        """
        Perform update if `meas` is provided and not timed out.
        `meas` should be shape=(3,) array [n,e,d].
        """
        now = time.time()
        if meas is not None:
            self.kf.update(meas.reshape((3,1)))
            self.last_update = now
        elif now - self.last_update > self.miss_timeout:
            # pure prediction until next measurement
            pass

    def step(self, meas: Optional[np.ndarray], dt: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Combined predict+update for one cycle.
        Returns (pos_est[3], vel_est[3])
        """
        self.predict(dt)
        self.update(meas)
        x = self.kf.x.flatten()
        return x[0:3], x[3:6]

# =============================================================================
#                          GUIDANCE STRATEGY INTERFACE
# =============================================================================

class GuidanceStrategy(ABC):
    """
    Abstract base class for pursuit guidance strategies.
    """
    @abstractmethod
    async def run(self,
                  drone: System,
                  err_body: np.ndarray,
                  *,
                  dt: float,
                  yaw_rad: float,
                  desired_yaw: float) -> None:
        """
        Compute & send offboard command based on camera-body error.

        :param drone: MAVSDK System instance
        :param err_body: [x_body_error,y_body_error,z_body_error]
        :param dt: time since last update (s)
        :param yaw_rad: vehicle yaw in radians
        :param desired_yaw: final heading command (deg)
        """
        pass

# =============================================================================
#                     BUILT-IN GUIDANCE STRATEGIES
# =============================================================================

class LocalVelocityStrategy(GuidanceStrategy):
    """
    Applies camera-frame PID → BODY velocities → NED velocities → offboard.
    Always points camera X axis at target via desired_yaw.
    """
    def __init__(self):
        self.pid_x = PIDController(KP_CAM_X, KI_CAM_X, KD_CAM_X,
                                   -MAX_VX_BODY, MAX_VX_BODY)
        self.pid_y = PIDController(KP_CAM_Y, KI_CAM_Y, KD_CAM_Y,
                                   -MAX_VY_BODY, MAX_VY_BODY)
        self.pid_z = PIDController(KP_CAM_Z, KI_CAM_Z, KD_CAM_Z,
                                   -MAX_VZ_BODY, MAX_VZ_BODY,
                                   CAM_Z_DEADBAND)

    async def run(self, drone, err_body, *, dt, yaw_rad, desired_yaw):
        # 1) Rotate error into CAMERA frame
        err_cam = R_CAM2BODY.T.dot(err_body)
        # 2) PID in X,Y,Z camera axes
        ux = self.pid_x.update(err_cam[0], dt)
        uy = self.pid_y.update(err_cam[1], dt)
        uz = self.pid_z.update(err_cam[2], dt)
        # 3) Rotate camera-output back to BODY
        vel_body = R_CAM2BODY.dot(np.array([ux, uy, uz]))
        # 4) Rotate BODY velocities to WORLD NED
        dn, de, dd = cam_to_world(vel_body, yaw_rad)
        # 5) Send NED velocity + yaw angle
        try:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(dn, de, dd, desired_yaw)
            )
        except OffboardError as e:
            logger.error("LocalVelocity failed: %s", e)


class GlobalPositionStrategy(GuidanceStrategy):
    """
    Computes geodetic setpoint from camera-body error and sends PositionGlobalYaw.
    Uses absolute AMSL altitude from telemetry.
    """
    async def run(self, drone, err_body, *, dt, yaw_rad, desired_yaw):
        # fetch current geodetic + NED
        lat, lon, alt, cn, ce, cd = await get_lla_ned(drone)
        # compute NED offset in world
        dn, de, dd = cam_to_world(err_body, yaw_rad)
        enu_e, enu_n, enu_u = de, dn, -dd
        # convert ENU→geodetic
        tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
            enu_e, enu_n, enu_u,
            lat, lon, alt,
            deg=True
        )
        # send setpoint
        try:
            await drone.offboard.set_position_global(
                PositionGlobalYaw(
                    tgt_lat,
                    tgt_lon,
                    tgt_alt,
                    desired_yaw,
                    PositionGlobalYaw.AltitudeType.AMSL
                )
            )
        except OffboardError as e:
            logger.error("GlobalPosition failed: %s", e)


class GlobalVelocityStrategy(GuidanceStrategy):
    """
    Full NED-frame PID on geodetic-derived offset → send NED velocities.
    """
    def __init__(self):
        self.pid_n = PIDController(KP_CAM_X, KI_CAM_X, KD_CAM_X,
                                   -MAX_VX_BODY, MAX_VX_BODY)
        self.pid_e = PIDController(KP_CAM_Y, KI_CAM_Y, KD_CAM_Y,
                                   -MAX_VY_BODY, MAX_VY_BODY)
        self.pid_d = PIDController(KP_CAM_Z, KI_CAM_Z, KD_CAM_Z,
                                   -MAX_VZ_BODY, MAX_VZ_BODY,
                                   CAM_Z_DEADBAND)

    async def run(self, drone, err_body, *, dt, yaw_rad, desired_yaw):
        # fetch current geodetic + NED
        lat, lon, alt, cn, ce, cd = await get_lla_ned(drone)
        # compute world NED offset
        dn, de, dd = cam_to_world(err_body, yaw_rad)
        enu_e, enu_n, enu_u = de, dn, -dd
        # geodetic target
        tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
            enu_e, enu_n, enu_u, lat, lon, alt, deg=True
        )
        # back to ENU→consistent NED offset
        be, bn, bu = pm.geodetic2enu(
            tgt_lat, tgt_lon, tgt_alt, lat, lon, alt, deg=True
        )
        off_n, off_e, off_d = bn, be, -bu
        # PID in NED
        un = self.pid_n.update(off_n, dt)
        ue = self.pid_e.update(off_e, dt)
        ud = self.pid_d.update(off_d, dt)
        # send NED velocity + yaw
        try:
            await drone.offboard.set_velocity_ned(
                VelocityNedYaw(un, ue, ud, desired_yaw)
            )
        except OffboardError as e:
            logger.error("GlobalVelocity failed: %s", e)


class PNStrategy(GuidanceStrategy):
    """
    Stub for Proportional Navigation guidance.
    Replace `run` with PN implementation.
    """
    async def run(self, drone, err_body, *, dt, yaw_rad, desired_yaw):
        logger.warning("PNStrategy not implemented.")


STRATEGY_REGISTRY: Dict[str, Type[GuidanceStrategy]] = {
    "local_velocity":  LocalVelocityStrategy,
    "global_position": GlobalPositionStrategy,
    "global_velocity": GlobalVelocityStrategy,
    "pn":              PNStrategy,
}

# =============================================================================
#                           PLOTTING / VISUALIZATION
# =============================================================================

class PlotUpdater:
    """
    Real-time 3D visualization of drone & target in NED.
    Shows path history, current markers, arrows, and engagement metrics.
    """
    def __init__(self):
        plt.ion()
        self.fig = plt.figure()
        self.ax  = self.fig.add_subplot(projection="3d")
        self.drone_line, = self.ax.plot([], [], [], c="blue", label="Drone")
        self.tgt_line,   = self.ax.plot([], [], [], c="red",  label="Target")
        self.drone_sc = self.ax.scatter([], [], [], c="blue", s=50)
        self.tgt_sc   = self.ax.scatter([], [], [], c="red",  s=50)
        self.text     = self.ax.text2D(0.02, 0.95, "", transform=self.ax.transAxes)
        self.ax.set_xlabel("North (m)")
        self.ax.set_ylabel("East (m)")
        self.ax.set_zlabel("Down (m)")
        self.ax.legend()
        self.ax.invert_zaxis()  # so negative-down (higher altitude) appears up
        self.drone_arr = self.ax.quiver(0,0,0,0,0,0)
        self.cam_arr   = self.ax.quiver(0,0,0,0,0,0, color="cyan")
        self.path_drone, self.path_tgt = [], []
        self.zoom = 2.0; self.last = 0.0

    def initialize(self, n0, e0, d0, tn, te, td, yaw):
        """
        Initial draw: paths, scatters, arrows.
        yaw in radians.
        """
        self.path_drone = [(n0,e0,d0)]
        self.path_tgt    = [(tn,te,td)]
        self.drone_line.set_data([n0],[e0]); self.drone_line.set_3d_properties([d0])
        self.tgt_line.set_data([tn],[te]);     self.tgt_line.set_3d_properties([td])
        self.drone_sc._offsets3d = ([n0],[e0],[d0])
        self.tgt_sc._offsets3d   = ([tn],[te],[td])
        self.drone_arr.remove(); self.cam_arr.remove()
        self.drone_arr = self.ax.quiver(n0,e0,d0,
                                        math.cos(yaw), math.sin(yaw), 0,
                                        length=ARROW_LEN, normalize=True)
        cy = yaw + math.radians(CAM_MOUNT_YAW_DEG)
        self.cam_arr = self.ax.quiver(n0,e0,d0,
                                      math.cos(cy), math.sin(cy), 0,
                                      length=ARROW_LEN, normalize=True, color="cyan")
        plt.draw(); plt.pause(0.001)
        self.last = time.time()

    def update(self, cn, ce, cd, tn, te, td, yaw, dist, speed, eta, chi):
        """
        Update plot if enough time elapsed.
        Adds to history, redraws lines, scatters, arrows, zoom.
        """
        now = time.time()
        if now - self.last < 1.0/PLOT_RATE_HZ:
            return
        self.path_drone.append((cn,ce,cd))
        self.path_tgt.append((tn,te,td))
        dn,de,dd = zip(*self.path_drone)
        tn_,te_,td_ = zip(*self.path_tgt)
        self.drone_line.set_data(dn,de); self.drone_line.set_3d_properties(dd)
        self.tgt_line.set_data(tn_,te_); self.tgt_line.set_3d_properties(td_)
        self.drone_sc._offsets3d = ([cn],[ce],[cd])
        self.tgt_sc._offsets3d   = ([tn],[te],[td])
        self.text.set_text(f"D={dist:.1f}m V={speed:.1f}m/s ETA={eta:.1f}s χ={chi:.1f}°")
        self.drone_arr.remove(); self.cam_arr.remove()
        self.drone_arr = self.ax.quiver(cn,ce,cd,
                                        math.cos(yaw), math.sin(yaw), 0,
                                        length=ARROW_LEN, normalize=True)
        cy = yaw + math.radians(CAM_MOUNT_YAW_DEG)
        self.cam_arr   = self.ax.quiver(cn,ce,cd,
                                        math.cos(cy), math.sin(cy), 0,
                                        length=ARROW_LEN, normalize=True, color="cyan")
        all_n = np.array(dn + tn_)
        all_e = np.array(de + te_)
        all_d = np.array(dd + td_)
        self.ax.set_xlim(all_n.min()-self.zoom, all_n.max()+self.zoom)
        self.ax.set_ylim(all_e.min()-self.zoom, all_e.max()+self.zoom)
        self.ax.set_zlim(all_d.max()+self.zoom, all_d.min()-self.zoom)
        plt.draw(); plt.pause(0.001)
        self.last = now

# =============================================================================
#                           TELEMETRY HELPERS
# =============================================================================

async def get_lla_ned(drone: System) -> Tuple[float, float, float, float, float, float]:
    """
    Return (lat_deg, lon_deg, alt_AMSL_m, north_m, east_m, down_m).
    Uses absolute_altitude_m for true AMSL.
    """
    async for p in drone.telemetry.position():
        lat, lon, alt = p.latitude_deg, p.longitude_deg, p.absolute_altitude_m
        break
    async for pv in drone.telemetry.position_velocity_ned():
        return lat, lon, alt, pv.position.north_m, pv.position.east_m, pv.position.down_m

async def get_yaw(drone: System) -> Tuple[float, float]:
    """
    Return (yaw_deg, yaw_rad) from attitude_euler telemetry.
    """
    async for att in drone.telemetry.attitude_euler():
        return att.yaw_deg, math.radians(att.yaw_deg)

async def get_ground_speed(drone: System) -> Tuple[float, float]:
    """
    Return ground speed components (vn, ve) in NED.
    """
    async for pv in drone.telemetry.position_velocity_ned():
        return pv.velocity.north_m_s, pv.velocity.east_m_s

# =============================================================================
#                                   MAIN
# =============================================================================

async def main():
    drone = System()
    await drone.connect(system_address="udp://:14540")
    logger.info("Connecting to PX4 SITL…")
    async for h in drone.telemetry.health():
        if h.is_global_position_ok and h.is_home_position_ok:
            logger.info("Vehicle ready.")
            break

    logger.info("Arming & OFFBOARD…")
    await drone.action.hold()
    await drone.action.arm()
    try:
        # start with zero NED velocity + zero yaw
        await drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, 0, 0))
        await drone.offboard.start()
        logger.info("Offboard engaged.")
    except OffboardError as e:
        logger.error("Offboard start failed: %s", e)
        return

    # --- Takeoff to hover altitude ---
    logger.info("Takeoff to %.1f m", TAKEOFF_ALTITUDE)
    t0 = time.time()
    last = t0
    while True:
        await drone.offboard.set_velocity_ned(VelocityNedYaw(0, 0, ASCENT_SPEED, 0))
        _,_,_,_,_,down = await get_lla_ned(drone)
        alt = -down
        if time.time()-last > 1.0:
            logger.info(" Ascending: %.2f m", alt)
            last = time.time()
        if alt >= TAKEOFF_ALTITUDE:
            logger.info("Reached altitude %.2f m", alt)
            break
        await asyncio.sleep(1/SETPOINT_FREQ)

    # hover
    await drone.offboard.set_velocity_ned(VelocityNedYaw(0,0,0,0))

    # record home state
    lat0, lon0, alt0, n0, e0, d0 = await get_lla_ned(drone)
    yaw_deg, yaw_rad = await get_yaw(drone)
    logger.info("Home LLA=(%.6f,%.6f,%.2f AMSL) NED=(%.2f,%.2f,%.2f) Yaw=%.1f°",
                lat0, lon0, alt0, n0, e0, d0, yaw_deg)

    # --- Compute initial target in WORLD NED using current yaw ---
    body_init = R_CAM2BODY.dot(CAM_TARGET_INIT)
    dn0, de0, dd0 = cam_to_world(body_init, yaw_rad)
    target_n = n0 + dn0
    target_e = e0 + de0
    target_d = d0 + dd0
    # target velocity in world NED
    body_vel = R_CAM2BODY.dot(CAM_TARGET_VEL)
    vel_n, vel_e, vel_d = cam_to_world(body_vel, yaw_rad)
    logger.info("Initial target NED=(%.2f,%.2f,%.2f)", target_n, target_e, target_d)

    # --- Initialize Kalman filter if enabled ---
    kf = None
    if USE_KALMAN:
        kf = FilterPyKalmanNED(
            dt=1/SETPOINT_FREQ,
            q_pos=KF_POS_NOISE,
            q_vel=KF_VEL_NOISE,
            r_meas=KF_MEAS_NOISE,
            miss_timeout=KF_MISS_TIMEOUT
        )
        kf.kf.x[:3] = np.array([target_n, target_e, target_d]).reshape((3,1))

    # --- Yaw to face initial target ---
    raw_bearing = math.degrees(math.atan2(target_e - e0, target_n - n0))
    desired_yaw = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
    logger.info("Yaw→%.1f° for camera-facing", desired_yaw)
    await drone.offboard.set_position_ned(PositionNedYaw(n0, e0, d0, desired_yaw))
    await asyncio.sleep(2.0)
    yaw_deg, yaw_rad = await get_yaw(drone)
    logger.info("Yaw aligned to %.1f°", yaw_deg)

    # --- Setup visualization ---
    plotter = PlotUpdater() if ENABLE_PLOT else None
    if plotter:
        plotter.initialize(n0, e0, d0, target_n, target_e, target_d, yaw_rad)

    # --- Select guidance strategy ---
    strat_cls = STRATEGY_REGISTRY.get(GUIDANCE_MODE, LocalVelocityStrategy)
    strategy = strat_cls()

    prev_t = start_t = time.time()
    print("Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg) | tgt lat | tgt lon | tgt alt (m AMSL)")

    # --- Main pursuit loop ---
    while True:
        now = time.time()
        dt = now - prev_t
        prev_t = now

        # propagate synthetic target in world NED
        target_n += vel_n * dt
        target_e += vel_e * dt
        target_d += vel_d * dt

        # current telemetry
        yaw_deg, yaw_rad = await get_yaw(drone)
        vn, ve = await get_ground_speed(drone)

        # get state based on guidance mode
        if GUIDANCE_MODE.startswith("global"):
            lat, lon, alt, cn, ce, cd = await get_lla_ned(drone)
        else:
            _, _, _, cn, ce, cd = await get_lla_ned(drone)
            lat = lon = alt = None

        # compute relative NED & metrics
        rel_n = target_n - cn
        rel_e = target_e - ce
        rel_d = target_d - cd
        dist  = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
        speed = math.hypot(vn, ve)
        eta   = dist / speed if speed > 0.1 else float('inf')

        # body-frame error
        err_body = np.array([
            rel_n * math.cos(yaw_rad) + rel_e * math.sin(yaw_rad),
            -rel_n * math.sin(yaw_rad) + rel_e * math.cos(yaw_rad),
            rel_d
        ])

        # apply Kalman filter if enabled
        if USE_KALMAN and kf:
            meas = np.array([target_n, target_e, target_d])
            pos_est, _ = kf.step(meas, dt)
            target_n, target_e, target_d = pos_est
            rel_n = target_n - cn; rel_e = target_e - ce; rel_d = target_d - cd
            err_body = np.array([
                rel_n * math.cos(yaw_rad) + rel_e * math.sin(yaw_rad),
                -rel_n * math.sin(yaw_rad) + rel_e * math.cos(yaw_rad),
                rel_d
            ])

        # compute desired yaw so camera X faces target
        raw_bearing = math.degrees(math.atan2(rel_e, rel_n))
        desired_yaw = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
        chi = normalize(desired_yaw - yaw_deg)

        # compute target LLA for logging if global mode
        tgt_lat = tgt_lon = tgt_alt = None
        if GUIDANCE_MODE.startswith("global"):
            dn, de, dd = cam_to_world(err_body, yaw_rad)
            tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
                de, dn, -dd, lat, lon, alt, deg=True
            )

        # dispatch to guidance strategy
        await strategy.run(
            drone,
            err_body,
            dt=dt,
            yaw_rad=yaw_rad,
            desired_yaw=desired_yaw
        )

        # console log
        if GUIDANCE_MODE.startswith("global"):
            print(f"{now-start_t:7.1f} | {dist:7.2f} | {speed:8.2f} | "
                  f"{eta:7.1f} | {chi:6.1f} | "
                  f"{tgt_lat:.6f} | {tgt_lon:.6f} | {tgt_alt:.2f} m", end="\r")
        else:
            print(f"{now-start_t:7.1f} | {dist:7.2f} | {speed:8.2f} | "
                  f"{eta:7.1f} | {chi:6.1f}", end="\r")

        # end checks
        if now - start_t > MAX_MISSION_TIME:
            logger.error("Mission timeout.")
            break
        if dist <= TARGET_THRESHOLD:
            logger.info("Reached target (%.2f m).", dist)
            break

        # plot update
        if ENABLE_PLOT:
            plotter.update(
                cn, ce, cd,
                target_n, target_e, target_d,
                yaw_rad,
                dist, speed, eta, chi
            )

        await asyncio.sleep(1/SETPOINT_FREQ)

    # hold & RTL
    logger.info("Holding for %.1f s", HOLD_TIME_AFTER)
    await asyncio.sleep(HOLD_TIME_AFTER)
    logger.info("Stopping offboard & RTL")
    await drone.offboard.stop()
    await drone.action.return_to_launch()
    logger.info("RTL initiated.")

if __name__ == "__main__":
    asyncio.run(main())
