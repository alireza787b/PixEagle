#!/usr/bin/env python3
"""
Robust Offboard Trajectory Pursuit with Full 3D PID and Yaw Slew Limiting

Features:
  - Full body-frame PID on forward (X), lateral (Y), and vertical (Z).
  - Integral action with clamping anti-windup.
  - Yaw-rate slew limiting for smooth heading control.
  - Altitude derivative damping and deadband.
  - Live progress logging: distance, speed, ETA, heading error.
  - Safe abort on timeout, health checks, and battery monitoring placeholders.
  - Easily extendable for OAK-driven dynamic target updates.
"""

import asyncio
import math
import time
import numpy as np
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed, PositionNedYaw
from mavsdk.telemetry import PositionVelocityNed, EulerAngle

# =============================================================================
#                             USER-CONFIGURABLE ZONE
# =============================================================================
# Static or dynamic target in CAMERA frame: [forward, right, down] (meters)
CAM_TARGET           = np.array([20.0, 0.0, -5.0])

# Camera-to-body rotation (extrinsic calibration matrix)
R_CAM2BODY           = np.eye(3)

# Safe takeoff altitude
TAKEOFF_ALTITUDE     = 5.0   # meters

# Ascent / descent rates (body frame down_m_s negative = up)
ASCENT_SPEED         = -1.0  # m/s
DESCENT_SPEED        =  0.5  # m/s (for RTL)

# PID gains for forward (body X)
KP_X                 = 0.5
KI_X                 = 0.05
KD_X                 = 0.1

# PID gains for lateral (body Y)
KP_Y                 = 0.5
KI_Y                 = 0.05
KD_Y                 = 0.1

# PID gains for vertical (body Z)
KP_Z                 = 0.5
KI_Z                 = 0.02
KD_Z                 = 0.1

# Vertical deadband: ignore |z_error| < Z_DEADBAND
Z_DEADBAND           = 0.1  # meters

# Yaw control parameters
YAW_DEADBAND         = 5.0    # degrees
YAW_GAIN             = 1.0    # deg/s per deg error
YAW_RATE_MAX         = 30.0   # deg/s absolute max
YAW_SLEW_RATE        = 90.0   # deg/s² max rate change

# Speed limits
MAX_VX               = 2.0  # m/s
MAX_VY               = 2.0  # m/s
MAX_VZ               = 1.0  # m/s

# Mission timing / thresholds
TARGET_THRESHOLD     = 0.5   # m to finish
HOLD_TIME_AFTER      = 3.0   # s hold at target
SETPOINT_FREQ        = 20.0  # Hz
MAX_MISSION_TIME     = 120.0 # s abort after

# =============================================================================
#                               END CONFIGURATION
# =============================================================================

def clamp(val, lo, hi):
    return max(lo, min(val, hi))

def normalize(angle: float) -> float:
    """Wrap to [-180, +180]."""
    a = (angle + 180.0) % 360.0 - 180.0
    return a

async def get_ned(drone: System):
    async for pv in drone.telemetry.position_velocity_ned():
        return pv.position.north_m, pv.position.east_m, pv.position.down_m

async def get_yaw(drone: System):
    async for e in drone.telemetry.attitude_euler():
        return e.yaw_deg, math.radians(e.yaw_deg)

async def get_position_velocity(drone: System):
    async for pv in drone.telemetry.position_velocity_ned():
        return pv

async def main():
    drone = System()
    await drone.connect(system_address="udp://:14540")
    print("[INFO] Connecting to PX4 SITL...")

    # Wait for GPS/home lock
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("[INFO] Vehicle ready for Offboard takeoff.")
            break

    # Arm & hold position
    print("[ACTION] Arming...")
    await drone.action.hold()
    await drone.action.arm()

    # Initialize Offboard mode with zero commands
    try:
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, 0, 0)
        )
        await drone.offboard.start()
        print("[OFFBOARD] Mode engaged.")
    except OffboardError as e:
        print(f"[ERROR] Offboard start failed: {e._result.result}")
        return

    # Vertical ascent
    print(f"[ACTION] Ascending to {TAKEOFF_ALTITUDE} m at {-ASCENT_SPEED} m/s.")
    while True:
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0, 0, ASCENT_SPEED, 0)
        )
        _, _, down = (await get_ned(drone))
        if -down >= TAKEOFF_ALTITUDE:
            print(f"[INFO] Reached {TAKEOFF_ALTITUDE} m altitude.")
            break
        await asyncio.sleep(1.0/SETPOINT_FREQ)

    # Stop vertical motion
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))

    # Record home pose
    n0, e0, d0 = await get_ned(drone)
    yaw_deg, yaw_rad = await get_yaw(drone)
    print(f"[DATA] Home NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°")

    # Compute static world‐frame target (can be updated dynamically)
    body_vec = R_CAM2BODY.dot(CAM_TARGET)
    bx, by, bz = body_vec
    d_n = bx*math.cos(yaw_rad) - by*math.sin(yaw_rad)
    d_e = bx*math.sin(yaw_rad) + by*math.cos(yaw_rad)
    d_d = bz
    target_n = n0 + d_n
    target_e = e0 + d_e
    target_d = d0 + d_d
    print(f"[COMPUTE] Target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})")

    # Initialize PID state
    I_x = I_y = I_z = 0.0
    prev_err_x = prev_err_y = prev_err_z = 0.0
    prev_time = time.time()
    prev_yaw_rate_cmd = 0.0

    # Initial yaw alignment
    desired_yaw = math.degrees(math.atan2(target_e-e0, target_n-n0))
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))  # pause motion
    await asyncio.sleep(0.1)
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0,0,0,0))  # double-call for reliability
    print("[ACTION] Yaw-aligning...")
    await drone.offboard.set_position_ned(
        PositionNedYaw(n0, e0, d0, desired_yaw)
    )
    await asyncio.sleep(2.0)

    # Pursuit loop
    print("[PROGRESS] Time(s) | Dist(m) | Speed(m/s) | ETA(s) | χ(deg)")
    start_time = time.time()
    while True:
        # Time & telemetry
        now = time.time()
        dt = now - prev_time
        prev_time = now

        pv = await get_position_velocity(drone)
        cn, ce, cd = pv.position.north_m, pv.position.east_m, pv.position.down_m
        vn, ve, vd = pv.velocity.north_m_s, pv.velocity.east_m_s, pv.velocity.down_m_s

        # Relative NED
        rel_n = target_n - cn
        rel_e = target_e - ce
        rel_d = target_d - cd
        dist = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
        speed = math.hypot(vn, ve)
        eta = dist / speed if speed > 0.1 else float('inf')

        # Body-frame error projections
        yaw_deg, yaw_rad = await get_yaw(drone)
        err_x =  rel_n*math.cos(yaw_rad) + rel_e*math.sin(yaw_rad)
        err_y = -rel_n*math.sin(yaw_rad) + rel_e*math.cos(yaw_rad)
        err_z = rel_d

        # Integral update with anti-windup
        # X-axis
        I_x += err_x * dt
        u_x = KP_X*err_x + KI_X*I_x + KD_X*((err_x - prev_err_x)/dt)
        # clamp and back-calculate integral
        u_x_clamped = clamp(u_x, -MAX_VX, MAX_VX)
        if u_x != u_x_clamped:
            I_x -= err_x * dt
        prev_err_x = err_x

        # Y-axis
        I_y += err_y * dt
        u_y = KP_Y*err_y + KI_Y*I_y + KD_Y*((err_y - prev_err_y)/dt)
        u_y_clamped = clamp(u_y, -MAX_VY, MAX_VY)
        if u_y != u_y_clamped:
            I_y -= err_y * dt
        prev_err_y = err_y

        # Z-axis with deadband & derivative
        if abs(err_z) > Z_DEADBAND:
            I_z += err_z * dt
            u_z = KP_Z*err_z + KI_Z*I_z + KD_Z*((err_z - prev_err_z)/dt)
            u_z_clamped = clamp(u_z, -MAX_VZ, MAX_VZ)
            if u_z != u_z_clamped:
                I_z -= err_z * dt
            prev_err_z = err_z
        else:
            u_z_clamped = 0.0

        # Heading error & yaw-rate command
        desired_yaw = math.degrees(math.atan2(rel_e, rel_n))
        chi_err = normalize(desired_yaw - yaw_deg)
        if abs(chi_err) > YAW_DEADBAND:
            raw_yaw_rate = clamp(chi_err * YAW_GAIN, -YAW_RATE_MAX, YAW_RATE_MAX)
        else:
            raw_yaw_rate = 0.0
        # Slew-rate limit
        max_delta = YAW_SLEW_RATE * dt
        yaw_rate_cmd = prev_yaw_rate_cmd + clamp(raw_yaw_rate - prev_yaw_rate_cmd, -max_delta, max_delta)
        prev_yaw_rate_cmd = yaw_rate_cmd

        # Log progress
        elapsed = now - start_time
        print(f"[{elapsed:6.1f}]   {dist:7.2f} | {speed:8.2f} | {eta:7.1f} | {chi_err:6.1f}", end="\r")

        # Abort on timeout
        if elapsed > MAX_MISSION_TIME:
            print("\n[ERROR] Mission timeout, aborting.")
            break

        # Finish condition
        if dist <= TARGET_THRESHOLD:
            print(f"\n[INFO] Target reached (dist={dist:.2f} m).")
            break

        # Send setpoint
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(u_x_clamped, u_y_clamped, u_z_clamped, yaw_rate_cmd)
        )
        await asyncio.sleep(1.0/SETPOINT_FREQ)

    # Hold at target
    print(f"[ACTION] Holding for {HOLD_TIME_AFTER} s...")
    await asyncio.sleep(HOLD_TIME_AFTER)

    # Exit offboard and RTL
    print("[OFFBOARD] Stopping and returning to launch...")
    await drone.offboard.stop()
    await drone.action.return_to_launch()
    print("[COMPLETE] RTL initiated.")

if __name__ == "__main__":
    asyncio.run(main())
