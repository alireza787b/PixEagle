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
      * "global_position": compute target LLA → offboard PositionGlobalInt.
      * "global_velocity": compute target LLA → convert back to NED → body-velocity offboard.
"""

import asyncio
import math
import time

import numpy as np
import matplotlib.pyplot as plt
import pymap3d as pm  # for geodetic ↔ ENU conversions

from mavsdk import System
from mavsdk.offboard import (
    OffboardError,
    VelocityBodyYawspeed,
    PositionNedYaw,
    PositionGlobalInt
)

# =============================================================================
#                            USER-CONFIGURABLE ZONE
# =============================================================================
# CAMERA FRAME TARGET DEFINITION:
# Simulates OAK-D camera detection output in SITL
# X_cam = forward, Y_cam = right, Z_cam = down (meters)
CAM_TARGET_INIT     = np.array([20.0,  0.0, -5.0])
CAM_TARGET_VEL      = np.array([-2.5, -1.0,  0.0])

# Camera mount extrinsics: yaw, pitch, roll (degrees)
CAM_MOUNT_YAW_DEG   = 0.0   # + rotates camera left of vehicle X+ axis
CAM_MOUNT_PITCH_DEG = 0.0   # + tilts camera nose up
CAM_MOUNT_ROLL_DEG  = 0.0   # + rolls camera clockwise looking forward

# Takeoff settings
TAKEOFF_ALTITUDE    = 5.0    # meters above home
ASCENT_SPEED        = -2.0   # m/s down rate (negative=up)

# PID gains for CAMERA-frame X (forward), Y (right), Z (down)
KP_CAM_X, KI_CAM_X, KD_CAM_X = 0.5,  0.05, 0.1
KP_CAM_Y, KI_CAM_Y, KD_CAM_Y = 0.5,  0.05, 0.1
KP_CAM_Z, KI_CAM_Z, KD_CAM_Z = 0.5,  0.02, 0.1
CAM_Z_DEADBAND      = 0.1    # m deadband in camera Z

# Yaw control parameters
YAW_DEADBAND        = 5.0    # deg
YAW_GAIN            = 1.5    # deg/s per deg error
YAW_RATE_MAX        = 60.0   # deg/s
YAW_SLEW_RATE       = 120.0   # deg/s^2

# Velocity limits (body frame)
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
# Options:
#   "local_velocity"   → camera-frame PID → body-velocity offboard
#   "global_position"  → compute target LLA → offboard PositionGlobalInt
#   "global_velocity"  → compute target LLA → convert back to NED → body-velocity offboard
GUIDANCE_MODE = "local_velocity"
# =============================================================================
#                              END CONFIGURATION
# =============================================================================


def clamp(val, lo, hi):
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


# Build camera-to-body extrinsics: R_CAM2BODY = R_z(yaw) @ R_y(pitch) @ R_x(roll)
R_CAM2BODY = (
    rotation_z(CAM_MOUNT_YAW_DEG)
    @ rotation_y(CAM_MOUNT_PITCH_DEG)
    @ rotation_x(CAM_MOUNT_ROLL_DEG)
)


async def get_lla_ned(drone: System):
    """
    Get latest LLA (latitude, longitude, altitude) and NED position.
    Returns:
      lat_deg, lon_deg, alt_m, north_m, east_m, down_m
    """
    # Fetch geodetic position
    async for pos in drone.telemetry.position():
        lat_deg = pos.latitude_deg
        lon_deg = pos.longitude_deg
        alt_m   = pos.relative_altitude_m  # altitude above home (m)
        break

    # Fetch NED position
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
    Returns all handles for updating.
    """
    plt.ion()
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    drone_line, = ax.plot([], [], [], c='blue', label='Drone Path')
    tgt_line,   = ax.plot([], [], [], c='red',  label='Target Path')
    drone_scatter = ax.scatter([], [], [], c='blue', s=50)
    tgt_scatter   = ax.scatter([], [], [], c='red',  s=50)
    engagement_text = ax.text2D(0.02, 0.95, "", transform=ax.transAxes)
    ax.set_xlabel('North (m)')
    ax.set_ylabel('East (m)')
    ax.set_zlabel('Down (m)')
    ax.legend()
    # placeholder arrows (will be removed and redrawn)
    drone_arrow = ax.quiver(0, 0, 0, 0, 0, 0)
    cam_arrow   = ax.quiver(0, 0, 0, 0, 0, 0, color='cyan')
    return fig, ax, drone_line, tgt_line, drone_scatter, tgt_scatter, engagement_text, drone_arrow, cam_arrow


def cam_to_world(vec: np.ndarray, yaw_rad: float):
    """
    Convert a vector in BODY frame to WORLD NED frame.
    vec: (bx, by, bz) in BODY (forward, right, down).
    yaw_rad: current vehicle yaw in radians.
    Returns: (dn, de, dd) in WORLD NED.
    """
    bx, by, bz = vec
    dn = bx * math.cos(yaw_rad) - by * math.sin(yaw_rad)
    de = bx * math.sin(yaw_rad) + by * math.cos(yaw_rad)
    dd = bz  # down in body = down in NED
    return dn, de, dd


# -----------------------------------------------------------------------------
#                     MODE: Local Velocity Guidance
# -----------------------------------------------------------------------------
async def guidance_local_velocity(drone: System, err_body: np.ndarray,
                                  vel_body: np.ndarray, yaw_rate: float):
    """
    Local Velocity Mode:
      - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
      - vel_body: [u_x, u_y, u_z] from camera-frame PID rotated to BODY.
      - yaw_rate: commanded yaw-rate (deg/s).
    Action: send BODY-frame velocity + yaw_rate offboard.
    """
    try:
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(vel_body[0],
                                 vel_body[1],
                                 vel_body[2],
                                 yaw_rate)
        )
    except OffboardError as e:
        print(f"[ERROR] Local Velocity command failed: {e}")


# -----------------------------------------------------------------------------
#                     MODE: Global Position Guidance
# -----------------------------------------------------------------------------
async def guidance_global_position(drone: System, err_body: np.ndarray,
                                   yaw_rad: float, desired_yaw_body: float):
    """
    Global Position Mode:
      - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
      - yaw_rad: current yaw in radians.
      - desired_yaw_body: desired vehicle yaw (deg) to point camera at target.
    Action: compute target LLA (ENU→geodetic) and send PositionGlobalInt + yaw.
    """
    # 1) Fetch current LLA + NED
    lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)

    # 2) BODY → WORLD NED offset
    offset_n, offset_e, offset_d = cam_to_world(err_body, yaw_rad)

    # 3) NED → ENU conversion
    enu_e = offset_e
    enu_n = offset_n
    enu_u = -offset_d  # down positive → up negative

    # 4) ENU → geodetic (target LLA)
    tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
        enu_e, enu_n, enu_u,
        lat_cur, lon_cur, alt_cur,
        deg=True
    )

    # 5) Send global-position setpoint + yaw
    try:
        await drone.offboard.set_position_global_int(
            PositionGlobalInt(
                int(tgt_lat * 1e7),    # latitude in 1e-7 deg
                int(tgt_lon * 1e7),    # longitude in 1e-7 deg
                int(tgt_alt * 1000),   # altitude in millimeters
                yaw_deg=desired_yaw_body
            )
        )
    except OffboardError as e:
        print(f"[ERROR] Global Position command failed: {e}")


# -----------------------------------------------------------------------------
#                     MODE: Global Velocity Guidance
# -----------------------------------------------------------------------------
async def guidance_global_velocity(drone: System, err_body: np.ndarray,
                                   vel_body: np.ndarray, yaw_rad: float,
                                   yaw_rate: float):
    """
    Global Velocity Mode:
      - err_body: [X_body_error, Y_body_error, Z_body_error] in BODY frame.
      - vel_body: [u_x, u_y, u_z] from camera-frame PID rotated to BODY.
      - yaw_rad: current yaw in radians.
      - yaw_rate: commanded yaw-rate (deg/s).
    Action:
      1) Compute target LLA (ENU→geodetic).
      2) Convert back geodetic → ENU → NED offset.
      3) Issue the same BODY velocity command.
    This mode uses GPS only for coord transforms, but still relies on PID for velocities.
    """
    # 1) Fetch current LLA + NED
    lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)

    # 2) BODY → WORLD NED offset
    offset_n, offset_e, offset_d = cam_to_world(err_body, yaw_rad)

    # 3) NED → ENU conversion
    enu_e = offset_e
    enu_n = offset_n
    enu_u = -offset_d

    # 4) ENU → geodetic (target LLA)
    tgt_lat, tgt_lon, tgt_alt = pm.enu2geodetic(
        enu_e, enu_n, enu_u,
        lat_cur, lon_cur, alt_cur,
        deg=True
    )

    # 5) geodetic → ENU (back conversion)
    enu_e_back, enu_n_back, enu_u_back = pm.geodetic2enu(
        tgt_lat, tgt_lon, tgt_alt,
        lat_cur, lon_cur, alt_cur,
        deg=True
    )
    offset_n2 = enu_n_back
    offset_e2 = enu_e_back
    offset_d2 = -enu_u_back

    # 6) Now offset_n2, offset_e2, offset_d2 matches original offset_n, offset_e, offset_d.
    #    We simply reissue the PID-based body velocities + yaw_rate.
    try:
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(vel_body[0],
                                 vel_body[1],
                                 vel_body[2],
                                 yaw_rate)
        )
    except OffboardError as e:
        print(f"[ERROR] Global Velocity command failed: {e}")


# =============================================================================
#                                   MAIN
# =============================================================================
async def main():
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
        _, _, down = await get_lla_ned(drone)[3:]  # ignore lat/lon/alt, use down from NED
        alt = -down
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
    print(f"[DATA] Home LLA=({lat0:.6f},{lon0:.6f},{alt0:.2f} m), "
          f"NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°")

    # --- prepare initial world-frame target ---
    body_init = R_CAM2BODY.dot(CAM_TARGET_INIT)
    body_vel  = R_CAM2BODY.dot(CAM_TARGET_VEL)

    target_n, target_e, target_d = n0 + np.array(cam_to_world(body_init, yaw_rad))
    vel_n, vel_e, vel_d         = cam_to_world(body_vel, yaw_rad)
    print(f"[COMPUTE] Initial world target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})")

    # --- initial yaw align for camera-facing ---
    raw_bearing = math.degrees(math.atan2(target_e - e0, target_n - n0))
    desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
    print(f"[ACTION] Yaw to {desired_yaw_body:.1f}° for camera-facing...", end='\r', flush=True)
    await drone.offboard.set_position_ned(PositionNedYaw(n0, e0, d0, desired_yaw_body))
    await asyncio.sleep(2.0)
    print(f"\n[INFO] Yaw aligned to {desired_yaw_body:.1f}°")

    # --- setup plot ---
    if ENABLE_PLOT:
        fig, ax, drone_line, tgt_line, drone_scatter, tgt_scatter, engagement_text, drone_arrow, cam_arrow = init_plot()
        path_drone = [(n0, e0, d0)]
        path_tgt   = [(target_n, target_e, target_d)]
        zoom_margin = 2.0
        last_plot = 0.0
        # Initial draw
        drone_line.set_data([n0], [e0])
        drone_line.set_3d_properties([d0])
        tgt_line.set_data([target_n], [target_e])
        tgt_line.set_3d_properties([target_d])
        drone_scatter._offsets3d = ([n0], [e0], [d0])
        tgt_scatter._offsets3d   = ([target_n], [target_e], [target_d])
        # Draw initial arrows
        drone_arrow.remove()
        cam_arrow.remove()
        drone_arrow = ax.quiver(n0, e0, d0,
                                math.cos(yaw_rad), math.sin(yaw_rad), 0,
                                length=ARROW_LEN, normalize=True)
        yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
        cam_arrow = ax.quiver(n0, e0, d0,
                              math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0,
                              length=ARROW_LEN, normalize=True, color='cyan')
        plt.draw()
        plt.pause(0.001)

    # --- PID state in CAMERA frame ---
    I_cam_x = I_cam_y = I_cam_z = 0.0
    prev_cam_x = prev_cam_y = prev_cam_z = 0.0
    prev_time = start_time = time.time()
    prev_yaw_rate = 0.0
    print("Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg)", end='\r', flush=True)

    # --- pursuit loop ---
    while True:
        now = time.time()
        dt = now - prev_time
        prev_time = now

        # Propagate simulated target in world NED
        target_n += vel_n * dt
        target_e += vel_e * dt
        target_d += vel_d * dt

        # Get telemetry: yaw + ground speed
        yaw_deg, yaw_rad = await get_yaw(drone)
        pv = await get_position_velocity(drone)
        vn, ve = pv.velocity.north_m_s, pv.velocity.east_m_s

        # Depending on GUIDANCE_MODE, fetch LLA+NED or only NED
        if GUIDANCE_MODE in ("global_position", "global_velocity"):
            lat_cur, lon_cur, alt_cur, cn, ce, cd = await get_lla_ned(drone)
        else:
            # local_velocity mode: ignore LLA fields
            _, _, _, cn, ce, cd = await get_lla_ned(drone)
            lat_cur = lon_cur = alt_cur = None

        # Compute relative vector in NED & distance
        rel_n = target_n - cn
        rel_e = target_e - ce
        rel_d = target_d - cd
        dist = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
        speed = math.hypot(vn, ve)
        eta = dist/speed if speed > 0.1 else float('inf')

        # Compute error in BODY frame: rotate NED error by yaw
        err_body = np.array([
            rel_n * math.cos(yaw_rad) + rel_e * math.sin(yaw_rad),
            -rel_n * math.sin(yaw_rad) + rel_e * math.cos(yaw_rad),
            rel_d
        ])

        # Rotate to CAMERA frame
        err_cam = R_CAM2BODY.T.dot(err_body)
        err_x_cam, err_y_cam, err_z_cam = err_cam

        # PID in CAMERA axes
        # X axis (forward)
        I_cam_x += err_x_cam * dt
        u_cam_x = KP_CAM_X * err_x_cam + KI_CAM_X * I_cam_x + KD_CAM_X * ((err_x_cam - prev_cam_x) / dt)
        u_cam_x_cl = clamp(u_cam_x, -MAX_VX_BODY, MAX_VX_BODY)
        if u_cam_x != u_cam_x_cl:
            I_cam_x -= err_x_cam * dt
        prev_cam_x = err_x_cam

        # Y axis (right)
        I_cam_y += err_y_cam * dt
        u_cam_y = KP_CAM_Y * err_y_cam + KI_CAM_Y * I_cam_y + KD_CAM_Y * ((err_y_cam - prev_cam_y) / dt)
        u_cam_y_cl = clamp(u_cam_y, -MAX_VY_BODY, MAX_VY_BODY)
        if u_cam_y != u_cam_y_cl:
            I_cam_y -= err_y_cam * dt
        prev_cam_y = err_y_cam

        # Z axis (down) with deadband
        if abs(err_z_cam) > CAM_Z_DEADBAND:
            I_cam_z += err_z_cam * dt
            u_cam_z = KP_CAM_Z * err_z_cam + KI_CAM_Z * I_cam_z + KD_CAM_Z * ((err_z_cam - prev_cam_z) / dt)
            u_cam_z_cl = clamp(u_cam_z, -MAX_VZ_BODY, MAX_VZ_BODY)
            if u_cam_z != u_cam_z_cl:
                I_cam_z -= err_z_cam * dt
        else:
            u_cam_z_cl = 0.0
        prev_cam_z = err_z_cam

        # Rotate camera velocities → BODY velocities
        vel_body = R_CAM2BODY.dot(np.array([u_cam_x_cl, u_cam_y_cl, u_cam_z_cl]))

        # Desired yaw: bearing to target minus camera mount yaw
        raw_bearing = math.degrees(math.atan2(rel_e, rel_n))
        desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
        chi = normalize(desired_yaw_body - yaw_deg)
        raw_rate = clamp(chi * YAW_GAIN, -YAW_RATE_MAX, YAW_RATE_MAX) if abs(chi) > YAW_DEADBAND else 0.0
        max_d = YAW_SLEW_RATE * dt
        yaw_rate = prev_yaw_rate + clamp(raw_rate - prev_yaw_rate, -max_d, max_d)
        prev_yaw_rate = yaw_rate

        # Dispatch to chosen guidance mode
        if GUIDANCE_MODE == "local_velocity":
            await guidance_local_velocity(drone, err_body, vel_body, yaw_rate)

        elif GUIDANCE_MODE == "global_position":
            await guidance_global_position(drone, err_body, yaw_rad, desired_yaw_body)

        elif GUIDANCE_MODE == "global_velocity":
            await guidance_global_velocity(drone, err_body, vel_body, yaw_rad, yaw_rate)

        else:
            print(f"[ERROR] Invalid GUIDANCE_MODE \"{GUIDANCE_MODE}\". Using local_velocity.")
            await guidance_local_velocity(drone, err_body, vel_body, yaw_rate)

        # Dynamic console log (single-line update)
        print(f"{now - start_time:7.1f} | {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi:6.1f}",
              end='\r', flush=True)

        # Mission end checks
        if now - start_time > MAX_MISSION_TIME:
            print("\n[ERROR] Mission timeout.")
            break
        if dist <= TARGET_THRESHOLD:
            print(f"\n[INFO] Reached target (dist={dist:.2f} m)")
            break

        # Update plot if enabled
        if ENABLE_PLOT and now - last_plot > 1.0 / PLOT_RATE_HZ:
            path_drone.append((cn, ce, cd))
            path_tgt.append((target_n, target_e, target_d))
            dn, de, dd = zip(*path_drone)
            tn, te, td = zip(*path_tgt)

            drone_line.set_data(dn, de)
            drone_line.set_3d_properties(dd)
            tgt_line.set_data(tn, te)
            tgt_line.set_3d_properties(td)
            drone_scatter._offsets3d = ([cn], [ce], [cd])
            tgt_scatter._offsets3d   = ([target_n], [target_e], [target_d])
            engagement_text.set_text(f"Dist={dist:.2f}m, Speed={speed:.2f}m/s, ETA={eta:.1f}s")

            # Redraw arrows
            drone_arrow.remove()
            cam_arrow.remove()
            drone_arrow = ax.quiver(cn, ce, cd,
                                    math.cos(yaw_rad), math.sin(yaw_rad), 0,
                                    length=ARROW_LEN, normalize=True)
            yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
            cam_arrow = ax.quiver(cn, ce, cd,
                                  math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0,
                                  length=ARROW_LEN, normalize=True, color='cyan')

            # Dynamic zoom
            all_n = np.array(dn + tn)
            all_e = np.array(de + te)
            all_d = np.array(dd + td)
            ax.set_xlim(all_n.min() - zoom_margin, all_n.max() + zoom_margin)
            ax.set_ylim(all_e.min() - zoom_margin, all_e.max() + zoom_margin)
            ax.set_zlim(all_d.min() - zoom_margin, all_d.max() + zoom_margin)

            plt.draw()
            plt.pause(0.001)
            last_plot = now

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
