#!/usr/bin/env python3
"""
Robust Offboard Pursuit of a Moving Target
with Full 3D PID, Yaw Slew Limiting, Camera Extrinsics, and Camera-Frame Target Definition

Features:
  - Configuration at top (future YAML).
  - Camera-to-body rotation matrix R_CAM2BODY for arbitrary mount.
  - Moving target defined in CAMERA frame: forward (X), right (Y), down (Z).
  - Conversion of camera-frame target to world NED using extrinsics and yaw.
  - Full body-frame PID on X/Y/Z with anti-windup & deadband.
  - Yaw-rate slew limiting for smooth heading.
  - Optional real-time 3D Matplotlib visualization with dynamic zoom and path history.
  - Informative console logging during takeoff and pursuit, with single-line updates.
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
# X_cam = forward, Y_cam = right, Z_cam = down (meters)
CAM_TARGET_INIT  = np.array([20.0, 0.0, -5.0])   # initial target in CAMERA frame
CAM_TARGET_VEL   = np.array([-3.5, -1.0, 0.0])     # constant velocity in CAMERA frame (m/s)

# Camera-to-body extrinsics (rotation matrix)
# Allows arbitrary azimuth/elevation/roll of camera mount
R_CAM2BODY       = np.eye(3)

# Takeoff settings
TAKEOFF_ALTITUDE = 5.0    # meters above home
ASCENT_SPEED     = -2.0   # m/s (BODY down rate, negative=up)

# PID gains for body-frame X (forward), Y (right), Z (down)
KP_X, KI_X, KD_X = 0.5,  0.05, 0.1
KP_Y, KI_Y, KD_Y = 0.5,  0.05, 0.1
KP_Z, KI_Z, KD_Z = 0.5,  0.02, 0.1
Z_DEADBAND       = 0.1    # m deadband for Z axis

# Yaw control parameters
YAW_DEADBAND     = 5.0    # deg
YAW_GAIN         = 1.0    # deg/s per deg error
YAW_RATE_MAX     = 30.0   # deg/s
YAW_SLEW_RATE    = 90.0   # deg/s^2

# Velocity limits (body frame)
MAX_VX, MAX_VY, MAX_VZ = 5.0, 5.0, 1.0  # m/s

# Mission logic
TARGET_THRESHOLD = 1.0    # m finish radius
HOLD_TIME_AFTER  = 3.0    # s hold at target
SETPOINT_FREQ    = 20.0   # Hz control loop
MAX_MISSION_TIME = 120.0  # s timeout

# Visualization
ENABLE_PLOT      = True
PLOT_RATE_HZ     = 5      # update plot this many times per second
# =============================================================================
#                              END CONFIGURATION
# =============================================================================


def clamp(val, lo, hi):
    return max(lo, min(val, hi))


def normalize(angle: float) -> float:
    """Wrap to [-180, +180] degrees."""
    return ((angle + 180) % 360) - 180

async def get_position_velocity(drone: System):
    async for pv in drone.telemetry.position_velocity_ned():
        return pv



async def get_ned(drone: System):
    async for pv in drone.telemetry.position_velocity_ned():
        return pv.position.north_m, pv.position.east_m, pv.position.down_m


async def get_yaw(drone: System):
    async for e in drone.telemetry.attitude_euler():
        return e.yaw_deg, math.radians(e.yaw_deg)


async def main():
    drone = System()
    await drone.connect(system_address="udp://:14540")
    print("[INFO] Connecting to PX4 SITL...")

    # Wait for GPS and home position
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("[INFO] Vehicle ready for Offboard.")
            break

    print("[ACTION] Arming and holding...")
    await drone.action.hold()
    await drone.action.arm()

    # Start offboard
    try:
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))
        await drone.offboard.start()
        print("[OFFBOARD] Engaged.")
    except OffboardError as e:
        print(f"[ERROR] Offboard start failed: {e._result.result}")
        return

    # Vertical Ascent
    print(f"[TAKEOFF] Ascending to {TAKEOFF_ALTITUDE:.1f} m at {abs(ASCENT_SPEED):.1f} m/s", end="\r", flush=True)
    last_log = time.time()
    while True:
        await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,ASCENT_SPEED,0))
        _,_,down = await get_ned(drone)
        alt = -down
        now = time.time()
        if now - last_log >= 1.0:
            print(f"[TAKEOFF] Altitude: {alt:.2f} m", end="\r", flush=True)
            last_log = now
        if alt >= TAKEOFF_ALTITUDE:
            print(f"\n[INFO] Reached takeoff altitude {alt:.2f} m")
            break
        await asyncio.sleep(1/SETPOINT_FREQ)
    # hover briefly
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))

    # Record home position & yaw
    n0,e0,d0 = await get_ned(drone)
    yaw_deg, yaw_rad = await get_yaw(drone)
    print(f"[DATA] Home NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°")

    # Prepare dynamic world-frame target from camera-frame definition
    # Convert CAMERA-frame initial pos/vel -> BODY-frame -> WORLD NED
    body_init = R_CAM2BODY.dot(CAM_TARGET_INIT)
    body_vel  = R_CAM2BODY.dot(CAM_TARGET_VEL)

    def cam_to_world(vec):
        bx,by,bz = vec
        dn = bx*math.cos(yaw_rad) - by*math.sin(yaw_rad)
        de = bx*math.sin(yaw_rad) + by*math.cos(yaw_rad)
        dd = bz
        return dn,de,dd

    target_n, target_e, target_d = n0 + np.array(cam_to_world(body_init))
    vel_n, vel_e, vel_d       = cam_to_world(body_vel)
    print(f"[COMPUTE] Initial world target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})")

    # Yaw-align to target
    desired_yaw = math.degrees(math.atan2(target_e-e0, target_n-n0))
    print(f"[ACTION] Yawing to {desired_yaw:.1f}°...")
    await drone.offboard.set_position_ned(PositionNedYaw(n0,e0,d0,desired_yaw))
    await asyncio.sleep(2.0)
    print(f"[INFO] Yaw aligned to {desired_yaw:.1f}°")

    # Setup plot
    if ENABLE_PLOT:
        plt.ion()
        fig = plt.figure()
        ax  = fig.add_subplot(projection='3d')
        drone_line, = ax.plot([],[],[],c='blue',label='Drone Path')
        tgt_line,   = ax.plot([],[],[],c='red', label='Target Path')
        drone_scatter = ax.scatter([],[],[],c='blue',s=50)
        tgt_scatter   = ax.scatter([],[],[],c='red', s=50)
        engagement_text = ax.text2D(0.02, 0.95, "", transform=ax.transAxes)
        ax.set_xlabel('North (m)'); ax.set_ylabel('East (m)'); ax.set_zlabel('Down (m)')
        ax.legend()
        path_drone = [(n0,e0,d0)]
        path_tgt   = [(target_n,target_e,target_d)]
        zoom_margin=2.0
        last_plot = 0.0
        # initial draw
        drone_line.set_data([n0],[e0]); drone_line.set_3d_properties([d0])
        tgt_line.  set_data([target_n],[target_e]); tgt_line.  set_3d_properties([target_d])
        drone_scatter._offsets3d = ([n0],[e0],[d0])
        tgt_scatter  ._offsets3d = ([target_n],[target_e],[target_d])
        plt.draw(); plt.pause(0.001)

    # PID state
    I_x=I_y=I_z=0.0
    prev_x=prev_y=prev_z=0.0
    prev_time=start_time=time.time()
    prev_yaw_rate=0.0

    print("Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg)")
    # Pursuit loop
    while True:
        now = time.time()
        dt  = now - prev_time
        prev_time = now

        # update moving target
        target_n += vel_n * dt
        target_e += vel_e * dt
        target_d += vel_d * dt

        # telemetry
        cn,ce,cd = await get_ned(drone)
        yaw_deg,yaw_rad = await get_yaw(drone)
        pv = await get_position_velocity(drone)
        vn,ve = pv.velocity.north_m_s, pv.velocity.east_m_s

        # errors
        rel_n,rel_e,rel_d = target_n-cn, target_e-ce, target_d-cd
        dist = math.sqrt(rel_n**2+rel_e**2+rel_d**2)
        speed= math.hypot(vn,ve)
        eta = dist/speed if speed>0.1 else float('inf')

        # body-frame projection
        err_x = rel_n*math.cos(yaw_rad) + rel_e*math.sin(yaw_rad)
        err_y = -rel_n*math.sin(yaw_rad)+ rel_e*math.cos(yaw_rad)
        err_z = rel_d

        # PID X
        I_x += err_x*dt
        u_x = KP_X*err_x + KI_X*I_x + KD_X*((err_x-prev_x)/dt)
        u_x_cl= clamp(u_x, -MAX_VX, MAX_VX)
        if u_x!=u_x_cl: I_x -= err_x*dt
        prev_x=err_x

        # PID Y
        I_y += err_y*dt
        u_y = KP_Y*err_y + KI_Y*I_y + KD_Y*((err_y-prev_y)/dt)
        u_y_cl= clamp(u_y, -MAX_VY, MAX_VY)
        if u_y!=u_y_cl: I_y -= err_y*dt
        prev_y=err_y

        # PID Z
        if abs(err_z)>Z_DEADBAND:
            I_z+=err_z*dt
            u_z = KP_Z*err_z + KI_Z*I_z + KD_Z*((err_z-prev_z)/dt)
            u_z_cl= clamp(u_z, -MAX_VZ, MAX_VZ)
            if u_z!=u_z_cl: I_z -= err_z*dt
        else:
            u_z_cl=0.0
        prev_z=err_z

        # yaw rate
        desired_yaw=math.degrees(math.atan2(rel_e,rel_n))
        chi=normalize(desired_yaw-yaw_deg)
        raw_rate=clamp(chi*YAW_GAIN,-YAW_RATE_MAX,YAW_RATE_MAX) if abs(chi)>YAW_DEADBAND else 0.0
        max_d=YAW_SLEW_RATE*dt
        yaw_rate=prev_yaw_rate+clamp(raw_rate-prev_yaw_rate,-max_d,max_d)
        prev_yaw_rate=yaw_rate

        # log
        print(f"{now-start_time:7.1f} | {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi:6.1f}",end="\r")

        # abort/finish
        if now-start_time>MAX_MISSION_TIME:
            print("\n[ERROR] Mission timeout.")
            break
        if dist<=TARGET_THRESHOLD:
            print(f"\n[INFO] Reached target (dist={dist:.2f} m)")
            break

        # send command
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(u_x_cl,u_y_cl,u_z_cl,yaw_rate)
        )

        # update plot if needed
        if ENABLE_PLOT and now - last_plot > 1.0 / PLOT_RATE_HZ:
            path_drone.append((cn,ce,cd))
            path_tgt  .append((target_n,target_e,target_d))
            dn,de,dd = zip(*path_drone)
            tn,te,td = zip(*path_tgt)
            drone_line.set_data(dn,de); drone_line.set_3d_properties(dd)
            tgt_line.set_data(tn,te); tgt_line.set_3d_properties(td)
            drone_scatter._offsets3d = ([cn],[ce],[cd])
            tgt_scatter  ._offsets3d = ([target_n],[target_e],[target_d])
            # update engagement text
            engagement_text.set_text(
                f"Dist={dist:.2f}m, Speed={speed:.2f}m/s, ETA={eta:.1f}s"
            )
            # dynamic zoom
            all_n = np.array(dn+tn)
            all_e = np.array(de+te)
            all_d = np.array(dd+td)
            ax.set_xlim(all_n.min()-zoom_margin, all_n.max()+zoom_margin)
            ax.set_ylim(all_e.min()-zoom_margin, all_e.max()+zoom_margin)
            ax.set_zlim(all_d.min()-zoom_margin, all_d.max()+zoom_margin)
            plt.draw(); plt.pause(0.001)
            last_plot = now

        await asyncio.sleep(1/SETPOINT_FREQ)

    # hold and RTL
    print(f"[ACTION] Holding for {HOLD_TIME_AFTER:.1f} s")
    await asyncio.sleep(HOLD_TIME_AFTER)
    print("[OFFBOARD] Stopping & RTL")
    await drone.offboard.stop()
    await drone.action.return_to_launch()
    print("[COMPLETE] RTL initiated.")


if __name__ == "__main__":
    asyncio.run(main())