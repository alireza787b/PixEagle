#!/usr/bin/env python3
"""
Scalable Offboard Pursuit Module for Interceptor Drones
- Full 3D PID guidance + camera-to-body extrinsics
- Camera mount orientation via full rotation matrix from Euler angles
- Target defined in camera frame; transformed to body and world frames
- Yaw-rate slew limiting + attitude control
- Modular structure: easy integration, future YAML/CLI config
- Robust logging and flexible plotting for analysis
"""
import asyncio
import math
import time
import logging

import numpy as np
import matplotlib.pyplot as plt
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed, PositionNedYaw

# =============================================================================
#                            CONFIGURATION ZONE
# =============================================================================
# -- Camera-frame target (meters)
CAM_TARGET_INIT     = np.array([20.0, 0.0, -5.0])   # X_cam, Y_cam, Z_cam
CAM_TARGET_VEL      = np.array([-3.5, -1.0, 0.0])   # m/s in camera frame

# -- Camera mount orientation (degrees)
CAM_MOUNT_ROLL      = 0.0    # rotation about camera X-axis
CAM_MOUNT_PITCH     = 0.0    # rotation about camera Y-axis
CAM_MOUNT_YAW       = -90.0  # rotation about camera Z-axis (negative = left)

# -- Takeoff & mission
TAKEOFF_ALTITUDE    = 5.0    # meters AGL
ASCENT_SPEED        = -2.0   # body down-rate (m/s), negative = up
TARGET_THRESHOLD    = 1.0    # meters to finish
HOLD_TIME_AFTER     = 3.0    # seconds post-engagement
MAX_MISSION_TIME    = 120.0  # seconds
SETPOINT_FREQ       = 20.0   # Hz control loop

# -- PID gains (body frame) and limits
KP_X, KI_X, KD_X   = 0.5,  0.05, 0.1
KP_Y, KI_Y, KD_Y   = 0.5,  0.05, 0.1
KP_Z, KI_Z, KD_Z   = 0.5,  0.02, 0.1
Z_DEADBAND         = 0.1
MAX_VX, MAX_VY, MAX_VZ = 5.0, 5.0, 1.0

# -- Yaw control parameters
YAW_DEADBAND       = 5.0    # deg
YAW_GAIN           = 1.0    # (deg/s) per deg error
YAW_RATE_MAX       = 30.0   # deg/s
YAW_SLEW_RATE      = 90.0   # deg/s^2

# -- Visualization
ENABLE_PLOT        = True
PLOT_RATE_HZ       = 5
# =============================================================================
#                              END CONFIGURATION
# =============================================================================

# Setup logging
logging.basicConfig(
    format="[%(levelname)s] %(asctime)s %(message)s", level=logging.INFO
)


def euler_to_rotation_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """
    Convert Euler angles (deg) to a 3x3 rotation matrix (Z-Y-X intrinsic).
    Roll: rotation about X, Pitch: about Y, Yaw: about Z.
    """
    r, p, y = map(math.radians, (roll, pitch, yaw))
    R_x = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    R_y = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    R_z = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    return R_z @ R_y @ R_x


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def normalize(angle: float) -> float:
    """Wrap angle to [-180, +180] degrees."""
    return ((angle + 180) % 360) - 180


class OffboardPursuit:
    """
    Encapsulates offboard pursuit logic for a moving target.
    """
    def __init__(self):
        # Compute camera-to-body extrinsics
        self.R_cam2body = euler_to_rotation_matrix(
            CAM_MOUNT_ROLL, CAM_MOUNT_PITCH, CAM_MOUNT_YAW
        )

        # PID state
        self.I_x = self.I_y = self.I_z = 0.0
        self.prev_x = self.prev_y = self.prev_z = 0.0
        self.prev_yaw_rate = 0.0

        # Telemetry handles
        self.drone = System()

    async def connect_and_arm(self):
        logging.info("Connecting to PX4 SITL...")
        await self.drone.connect(system_address="udp://:14540")

        # Wait for GNSS/home
        async for health in self.drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                logging.info("Vehicle ready for Offboard.")
                break

        await self.drone.action.hold()
        await self.drone.action.arm()
        try:
            await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            await self.drone.offboard.start()
            logging.info("Offboard engaged.")
        except OffboardError as e:
            logging.error(f"Offboard start failed: {e._result.result}")
            raise

    async def takeoff(self):
        """Ascending vertically to TAKEOFF_ALTITUDE."""
        logging.info(f"Ascending to {TAKEOFF_ALTITUDE} m")
        last_log = time.time()
        while True:
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0, 0, ASCENT_SPEED, 0)
            )
            n, e, d = await self.get_ned()
            alt = -d
            if time.time() - last_log > 1.0:
                logging.info(f"Takeoff alt: {alt:.2f} m")
                last_log = time.time()
            if alt >= TAKEOFF_ALTITUDE:
                logging.info("Reached takeoff altitude.")
                break
            await asyncio.sleep(1 / SETPOINT_FREQ)
        # hover
        await self.drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))

    async def get_ned(self):
        async for pv in self.drone.telemetry.position_velocity_ned():
            return pv.position.north_m, pv.position.east_m, pv.position.down_m

    async def get_yaw(self):
        async for att in self.drone.telemetry.attitude_euler():
            return att.yaw_deg, math.radians(att.yaw_deg)

    async def get_pos_vel(self):
        async for pv in self.drone.telemetry.position_velocity_ned():
            return pv

    async def run_mission(self):
        # Record home position
        n0, e0, d0 = await self.get_ned()
        yaw_deg, yaw_rad = await self.get_yaw()
        logging.info(f"Home NED=({n0:.2f},{e0:.2f},{d0:.2f}), Yaw={yaw_deg:.1f}°")

        # Transform camera-frame to world
        body_init = self.R_cam2body.dot(CAM_TARGET_INIT)
        body_vel  = self.R_cam2body.dot(CAM_TARGET_VEL)

        def to_world(vec):
            bx, by, bz = vec
            dn = bx * math.cos(yaw_rad) - by * math.sin(yaw_rad)
            de = bx * math.sin(yaw_rad) + by * math.cos(yaw_rad)
            dd = bz
            return dn, de, dd

        target_n, target_e, target_d = n0 + np.array(to_world(body_init))
        vel_n, vel_e, vel_d         = to_world(body_vel)
        logging.info(
            f"Initial target NED=({target_n:.2f},{target_e:.2f},{target_d:.2f})"
        )

        # Yaw-align so camera forward points at target
        los_yaw = math.degrees(math.atan2(target_e - e0, target_n - n0))
        cam_yaw = los_yaw + CAM_MOUNT_YAW
        await self.drone.offboard.set_position_ned(
            PositionNedYaw(n0, e0, d0, cam_yaw)
        )
        await asyncio.sleep(2.0)
        logging.info(f"Aligned camera yaw to {cam_yaw:.1f}°")

        # Optional plotting setup
        if ENABLE_PLOT:
            plt.ion()
            fig = plt.figure()
            ax  = fig.add_subplot(projection='3d')
            drone_path, = ax.plot([], [], [], label='Drone')
            tgt_path,   = ax.plot([], [], [], label='Target')
            scatter_d    = ax.scatter([], [], [], s=50)
            scatter_t    = ax.scatter([], [], [], s=50)
            text_eng = ax.text2D(0.02, 0.95, '', transform=ax.transAxes)
            ax.set_xlabel('North (m)')
            ax.set_ylabel('East (m)')
            ax.set_zlabel('Down (m)')
            ax.legend()
            history_d = [(n0, e0, d0)]
            history_t = [(target_n, target_e, target_d)]
            last_plot = time.time()

        start_time = time.time()
        logging.info("Beginning pursuit loop...")
        while True:
            now = time.time(); dt = now - start_time
            # propagate
            target_n += vel_n * dt; target_e += vel_e * dt; target_d += vel_d * dt
            # state
            cn, ce, cd       = await self.get_ned()
            yaw_deg, yaw_rad = await self.get_yaw()
            pv               = await self.get_pos_vel()
            vn, ve           = pv.velocity.north_m_s, pv.velocity.east_m_s
            # compute errors
            rel_n, rel_e, rel_d = target_n - cn, target_e - ce, target_d - cd
            dist = math.sqrt(rel_n**2 + rel_e**2 + rel_d**2)
            speed = math.hypot(vn, ve)
            # body errors
            err_x =  rel_n*math.cos(yaw_rad) + rel_e*math.sin(yaw_rad)
            err_y = -rel_n*math.sin(yaw_rad) + rel_e*math.cos(yaw_rad)
            err_z =  rel_d
            # PID controls
            # X
            self.I_x += err_x*dt
            u_x = KP_X*err_x + KI_X*self.I_x + KD_X*((err_x - self.prev_x)/dt)
            u_x_cl = clamp(u_x, -MAX_VX, MAX_VX)
            if u_x != u_x_cl: self.I_x -= err_x*dt
            self.prev_x = err_x
            # Y
            self.I_y += err_y*dt
            u_y = KP_Y*err_y + KI_Y*self.I_y + KD_Y*((err_y - self.prev_y)/dt)
            u_y_cl = clamp(u_y, -MAX_VY, MAX_VY)
            if u_y != u_y_cl: self.I_y -= err_y*dt
            self.prev_y = err_y
            # Z
            if abs(err_z) > Z_DEADBAND:
                self.I_z += err_z*dt
                u_z = KP_Z*err_z + KI_Z*self.I_z + KD_Z*((err_z - self.prev_z)/dt)
                u_z_cl = clamp(u_z, -MAX_VZ, MAX_VZ)
                if u_z != u_z_cl: self.I_z -= err_z*dt
            else:
                u_z_cl = 0.0
            self.prev_z = err_z
            # yaw-rate command
            los_yaw = math.degrees(math.atan2(rel_e, rel_n))
            cam_yaw = los_yaw + CAM_MOUNT_YAW
            yaw_err = normalize(cam_yaw - yaw_deg)
            raw_rate = clamp(yaw_err*YAW_GAIN, -YAW_RATE_MAX, YAW_RATE_MAX) \
                       if abs(yaw_err) > YAW_DEADBAND else 0.0
            max_d = YAW_SLEW_RATE*(now - self.prev_yaw_rate)
            yaw_rate = self.prev_yaw_rate + clamp(raw_rate - self.prev_yaw_rate, -max_d, max_d)
            self.prev_yaw_rate = yaw_rate
            # send
            await self.drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(u_x_cl, u_y_cl, u_z_cl, yaw_rate)
            )
            # check termination
            if time.time() - start_time > MAX_MISSION_TIME:
                logging.error("Mission timeout.")
                break
            if dist <= TARGET_THRESHOLD:
                logging.info(f"Target reached (dist={dist:.2f} m)")
                break
            # update plot
            if ENABLE_PLOT and time.time() - last_plot > 1/PLOT_RATE_HZ:
                history_d.append((cn, ce, cd)); history_t.append((target_n, target_e, target_d))
                D = np.array(history_d); T = np.array(history_t)
                drone_path.set_data(D[:,0], D[:,1]); drone_path.set_3d_properties(D[:,2])
                tgt_path.set_data(T[:,0], T[:,1]); tgt_path.set_3d_properties(T[:,2])
                scatter_d._offsets3d = (D[:,0], D[:,1], D[:,2])
                scatter_t._offsets3d = (T[:,0], T[:,1], T[:,2])
                text_eng.set_text(f"Dist={dist:.2f} m, Speed={speed:.2f} m/s")
                plt.draw(); plt.pause(0.001)
                last_plot = time.time()
            await asyncio.sleep(1 / SETPOINT_FREQ)
        # Post-mission
        logging.info(f"Holding for {HOLD_TIME_AFTER} s...")
        await asyncio.sleep(HOLD_TIME_AFTER)
        await self.drone.offboard.stop()
        await self.drone.action.return_to_launch()
        logging.info("Return to Launch initiated.")


if __name__ == "__main__":
    controller = OffboardPursuit()
    asyncio.run(controller.connect_and_arm())
    asyncio.run(controller.takeoff())
    asyncio.run(controller.run_mission())
