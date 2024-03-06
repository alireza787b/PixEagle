import asyncio
import threading
import time
from classes.parameters import Parameters

class SetpointSender(threading.Thread):
    def __init__(self, px4_controller):
        threading.Thread.__init__(self)
        self.px4_controller = px4_controller
        self.last_command = (0, 0, 0)  # Default to hover/zero velocity
        self.running = True
        

    def run(self):
        while self.running:
            # Send the last known command
            self.send_command_task = asyncio.run(self.px4_controller.send_velocity_commands(*self.last_command))
            if (Parameters.ENABLE_SETPOINT_DEBUGGING):
                self.print_current_setpoint()
            time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)  # 10 Hz

    def update_command(self, vel_x, vel_y, vel_z):
        self.last_command = (vel_x, vel_y, vel_z)

    def print_current_setpoint(self):
        """
        Prints the current commanded setpoint.
        """
        if hasattr(self, 'last_command'):
            print(f"Sending NED velocity commands: Vx={self.last_command[0]}, Vy={self.last_command[1]}, Vz={self.last_command[2]}")
        else:
            print("NED Velocity Setpoints not calculated or available.")
    def stop(self):
        self.running = False
