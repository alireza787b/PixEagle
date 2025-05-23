#!/usr/bin/env python3
"""
Robust Offboard Pursuit of a Moving Target
with Full 3D PID in CAMERA frame, Yaw Slew Limiting,
Camera Mount Extrinsics (Yaw/Pitch/Roll), and Camera-Frame Target Definition

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
"""

import asyncio
import math
import time

import numpy as np
import matplotlib.pyplot as plt

from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed
from mavsdk.offboard import PositionNedYaw

# =============================================================================
#                            USER-CONFIGURABLE ZONE
# =============================================================================
# CAMERA FRAME TARGET DEFINITION:
# Simulates OAK-D camera detection output in this phase of SITL
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
    return np.array([[1, 0,  0], [0, c, -s], [0, s, c]])


def rotation_y(deg: float) -> np.ndarray:
    """Rotation matrix about Y axis by deg degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[c, 0, s], [0, 1, 0], [-s,0, c]])


def rotation_z(deg: float) -> np.ndarray:
    """Rotation matrix about Z axis by deg degrees."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])

# Build camera-to-body extrinsics
R_CAM2BODY = (
    rotation_z(CAM_MOUNT_YAW_DEG)
    @ rotation_y(CAM_MOUNT_PITCH_DEG)
    @ rotation_x(CAM_MOUNT_ROLL_DEG)
)


async def get_ned(drone: System):
    """Get latest NED position."""
    async for pv in drone.telemetry.position_velocity_ned():
        return pv.position.north_m, pv.position.east_m, pv.position.down_m


async def get_yaw(drone: System):
    """Get latest yaw: degrees and radians."""
    async for att in drone.telemetry.attitude_euler():
        return att.yaw_deg, math.radians(att.yaw_deg)


async def get_position_velocity(drone: System):
    """Get latest position+velocity telemetry."""
    async for pv in drone.telemetry.position_velocity_ned():
        return pv


def init_plot():
    """Initialize 3D plot with paths, arrows, and guide annotation."""
    plt.ion()
    fig = plt.figure()
    ax = fig.add_subplot(projection='3d')
    drone_line, = ax.plot([],[],[], c='blue', label='Drone Path')
    tgt_line,   = ax.plot([],[],[], c='red',  label='Target Path')
    drone_scatter = ax.scatter([],[],[], c='blue', s=50)
    tgt_scatter   = ax.scatter([],[],[], c='red',  s=50)
    engagement_text = ax.text2D(0.02, 0.95, "", transform=ax.transAxes)
    ax.set_xlabel('North (m)'); ax.set_ylabel('East (m)'); ax.set_zlabel('Down (m)')
    ax.legend()
    # placeholder arrows
    drone_arrow = ax.quiver(0,0,0,0,0,0)
    cam_arrow   = ax.quiver(0,0,0,0,0,0, color='cyan')
    return fig, ax, drone_line, tgt_line, drone_scatter, tgt_scatter, engagement_text, drone_arrow, cam_arrow


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
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))
        await drone.offboard.start()
        print("[OFFBOARD] Engaged.")
    except OffboardError as e:
        print(f"[ERROR] Offboard start failed: {e._result.result}")
        return

    # --- takeoff ---
    print(f"[TAKEOFF] Ascending to {TAKEOFF_ALTITUDE:.1f} m...", end='\r', flush=True)
    last_log = time.time()
    while True:
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,ASCENT_SPEED,0))
        _,_,down = await get_ned(drone)
        alt = -down
        now = time.time()
        if now - last_log >= 1.0:
            print(f"[TAKEOFF] Altitude: {alt:.2f} m", end='\r', flush=True)
            last_log = now
        if alt >= TAKEOFF_ALTITUDE:
            print(f"\n[INFO] Reached altitude {alt:.2f} m")
            break
        await asyncio.sleep(1/SETPOINT_FREQ)
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))

    # --- record home state ---
    n0, e0, d0  = await get_ned(drone)
    yaw_deg, yaw_rad = await get_yaw(drone)
    print(f"[DATA] Home NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°")

    # --- prepare target in world ---
    body_init = R_CAM2BODY.dot(CAM_TARGET_INIT)
    body_vel  = R_CAM2BODY.dot(CAM_TARGET_VEL)
    def cam_to_world(vec, yaw_rad):
        bx,by,bz = vec
        dn = bx*math.cos(yaw_rad) - by*math.sin(yaw_rad)
        de = bx*math.sin(yaw_rad) + by*math.cos(yaw_rad)
        dd = bz
        return dn, de, dd

    target_n, target_e, target_d = n0 + np.array(cam_to_world(body_init, yaw_rad))
    vel_n, vel_e, vel_d         = cam_to_world(body_vel, yaw_rad)
    print(f"[COMPUTE] Initial world target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})")

    # --- initial yaw align for camera-facing ---
    raw_bearing = math.degrees(math.atan2(target_e-e0, target_n-n0))
    desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
    print(f"[ACTION] Yaw to {desired_yaw_body:.1f}° for camera-facing...", end='\r', flush=True)
    await drone.offboard.set_position_ned(PositionNedYaw(n0, e0, d0, desired_yaw_body))
    await asyncio.sleep(2.0)
    print(f"\n[INFO] Yaw aligned to {desired_yaw_body:.1f}°")

    # --- setup plot ---
    if ENABLE_PLOT:
        fig, ax, drone_line, tgt_line, drone_scatter, tgt_scatter, engagement_text, drone_arrow, cam_arrow = init_plot()
        path_drone = [(n0,e0,d0)]
        path_tgt   = [(target_n,target_e,target_d)]
        zoom_margin = 2.0
        last_plot = 0.0
        # initial draw
        drone_line.set_data([n0],[e0]); drone_line.set_3d_properties([d0])
        tgt_line.  set_data([target_n],[target_e]); tgt_line.  set_3d_properties([target_d])
        drone_scatter._offsets3d = ([n0],[e0],[d0])
        tgt_scatter  ._offsets3d = ([target_n],[target_e],[target_d])
        # draw initial arrows
        drone_arrow.remove(); cam_arrow.remove()
        drone_arrow = ax.quiver(n0,e0,d0, math.cos(yaw_rad), math.sin(yaw_rad), 0, length=ARROW_LEN, normalize=True)
        yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
        cam_arrow   = ax.quiver(n0,e0,d0, math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0, length=ARROW_LEN, normalize=True, color='cyan')
        plt.draw(); plt.pause(0.001)

    # --- PID state in CAMERA frame ---
    I_cam_x = I_cam_y = I_cam_z = 0.0
    prev_cam_x = prev_cam_y = prev_cam_z = 0.0
    prev_time = start_time = time.time()
    prev_yaw_rate = 0.0
    print("Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg)", end='\r', flush=True)

    # --- pursuit loop ---
    while True:
        now = time.time(); dt = now - prev_time; prev_time = now

        # propagate target in world
        target_n += vel_n * dt
        target_e += vel_e * dt
        target_d += vel_d * dt

        # get telemetry
        cn, ce, cd      = await get_ned(drone)
        yaw_deg, yaw_rad= await get_yaw(drone)
        pv              = await get_position_velocity(drone)
        vn, ve          = pv.velocity.north_m_s, pv.velocity.east_m_s

        # compute relative vector in NED & distance
        rel_n, rel_e, rel_d = target_n - cn, target_e - ce, target_d - cd
        dist = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
        speed= math.hypot(vn, ve)
        eta = dist/speed if speed>0.1 else float('inf')

        # compute error in camera frame
        err_body = np.array([
            rel_n*math.cos(yaw_rad) + rel_e*math.sin(yaw_rad),
            -rel_n*math.sin(yaw_rad)+rel_e*math.cos(yaw_rad),
            rel_d
        ])
        err_cam = R_CAM2BODY.T.dot(err_body)
        err_x_cam, err_y_cam, err_z_cam = err_cam

        # PID in camera axes
        I_cam_x += err_x_cam * dt
        u_cam_x = KP_CAM_X*err_x_cam + KI_CAM_X*I_cam_x + KD_CAM_X*((err_x_cam - prev_cam_x)/dt)
        u_cam_x_cl = clamp(u_cam_x, -MAX_VX_BODY, MAX_VX_BODY)
        if u_cam_x != u_cam_x_cl: I_cam_x -= err_x_cam * dt
        prev_cam_x = err_x_cam

        I_cam_y += err_y_cam * dt
        u_cam_y = KP_CAM_Y*err_y_cam + KI_CAM_Y*I_cam_y + KD_CAM_Y*((err_y_cam - prev_cam_y)/dt)
        u_cam_y_cl = clamp(u_cam_y, -MAX_VY_BODY, MAX_VY_BODY)
        if u_cam_y != u_cam_y_cl: I_cam_y -= err_y_cam * dt
        prev_cam_y = err_y_cam

        if abs(err_z_cam) > CAM_Z_DEADBAND:
            I_cam_z += err_z_cam * dt
            u_cam_z = KP_CAM_Z*err_z_cam + KI_CAM_Z*I_cam_z + KD_CAM_Z*((err_z_cam - prev_cam_z)/dt)
            u_cam_z_cl = clamp(u_cam_z, -MAX_VZ_BODY, MAX_VZ_BODY)
            if u_cam_z != u_cam_z_cl: I_cam_z -= err_z_cam * dt
        else:
            u_cam_z_cl = 0.0
        prev_cam_z = err_z_cam

        vel_body = R_CAM2BODY.dot(np.array([u_cam_x_cl, u_cam_y_cl, u_cam_z_cl]))

        # desired yaw: point camera X at target
        raw_bearing = math.degrees(math.atan2(rel_e, rel_n))
        desired_yaw_body = normalize(raw_bearing - CAM_MOUNT_YAW_DEG)
        chi = normalize(desired_yaw_body - yaw_deg)
        raw_rate = clamp(chi*YAW_GAIN, -YAW_RATE_MAX, YAW_RATE_MAX) if abs(chi)>YAW_DEADBAND else 0.0
        max_d = YAW_SLEW_RATE * dt
        yaw_rate = prev_yaw_rate + clamp(raw_rate - prev_yaw_rate, -max_d, max_d)
        prev_yaw_rate = yaw_rate

        # log status dynamically
        print(f"{now-start_time:7.1f} | {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi:6.1f}", end='\r', flush=True)

        # mission end checks
        if now-start_time > MAX_MISSION_TIME:
            print("\n[ERROR] Mission timeout.")
            break
        if dist <= TARGET_THRESHOLD:
            print(f"\n[INFO] Reached target (dist={dist:.2f} m)")
            break

        try:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(vel_body[0], vel_body[1], vel_body[2], yaw_rate)
            )
        except OffboardError as e:
            print(f"\n[ERROR] Offboard command failed: {e}")

        # update plot
        if ENABLE_PLOT and now - last_plot > 1.0 / PLOT_RATE_HZ:
            path_drone.append((cn,ce,cd))
            path_tgt.append((target_n,target_e,target_d))
            dn, de, dd = zip(*path_drone)
            tn, te, td = zip(*path_tgt)
            drone_line.set_data(dn, de); drone_line.set_3d_properties(dd)
            tgt_line.  set_data(tn, te); tgt_line.  set_3d_properties(td)
            drone_scatter._offsets3d = ([cn],[ce],[cd])
            tgt_scatter  ._offsets3d = ([target_n],[target_e],[target_d])
            engagement_text.set_text(f"Dist={dist:.2f}m, Speed={speed:.2f}m/s, ETA={eta:.1f}s")
            drone_arrow.remove(); cam_arrow.remove()
            drone_arrow = ax.quiver(cn,ce,cd, math.cos(yaw_rad), math.sin(yaw_rad), 0, length=ARROW_LEN, normalize=True)
            yaw_cam_rad = yaw_rad + math.radians(CAM_MOUNT_YAW_DEG)
            cam_arrow   = ax.quiver(cn,ce,cd, math.cos(yaw_cam_rad), math.sin(yaw_cam_rad), 0, length=ARROW_LEN, normalize=True, color='cyan')
            all_n = np.array(dn + tn); all_e = np.array(de + te); all_d = np.array(dd + td)
            ax.set_xlim(all_n.min()-zoom_margin, all_n.max()+zoom_margin)
            ax.set_ylim(all_e.min()-zoom_margin, all_e.max()+zoom_margin)
            ax.set_zlim(all_d.min()-zoom_margin, all_d.max()+zoom_margin)
            plt.draw(); plt.pause(0.001)
            last_plot = now

        await asyncio.sleep(1/SETPOINT_FREQ)

    # --- finish: hold & RTL ---
    print(f"[ACTION] Holding for {HOLD_TIME_AFTER:.1f} s")
    await asyncio.sleep(HOLD_TIME_AFTER)
    print("[OFFBOARD] Stopping & RTL")
    await drone.offboard.stop()
    await drone.action.return_to_launch()
    print("[COMPLETE] RTL initiated.")


if __name__ == "__main__":
    asyncio.run(main())