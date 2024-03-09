import asyncio
import threading
import time
from classes.parameters import Parameters

class SetpointSender(threading.Thread):
    def __init__(self, px4_controller):
        super().__init__(daemon=True)
        self.px4_controller = px4_controller
        self.last_command = (0, 0, 0)  # Default to hover/zero velocity
        self.running = True
        

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.running:
            loop.run_until_complete(self.px4_controller.send_velocity_commands(self.last_command))
            if Parameters.ENABLE_SETPOINT_DEBUGGING:
                self.print_current_setpoint()
            time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)
        loop.close()

    def update_command(self, vel_x, vel_y, vel_z):
        self.last_command = (vel_x, vel_y, vel_z)

    def print_current_setpoint(self):
        if hasattr(self, 'last_command'):
            print(f"setting NED velocity commands: Vx={self.last_command[0]}, Vy={self.last_command[1]}, Vz={self.last_command[2]}")

    def stop(self):
        self.running = False
        self.join()  # Wait for the thread to finish

