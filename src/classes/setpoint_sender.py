#src/classes/setpoint_sender.py
import asyncio
import threading
import time
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

class SetpointSender(threading.Thread):
    def __init__(self, px4_controller, setpoint_handler: SetpointHandler):
        super().__init__(daemon=True)
        self.px4_controller = px4_controller
        self.setpoint_handler = setpoint_handler  # Inject the SetpointHandler
        self.running = True
        

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.running:
            # Fetch the current setpoints from the SetpointHandler
            setpoints = self.setpoint_handler.get_fields()

            # Send the velocity commands to the PX4 controller using the setpoints
            #TODO: Depends on the profile of follower setpoint we might need to use other mavsdk offabord (pitch rate, yaw rate, rollrate , thrust , ...)
            loop.run_until_complete(self.px4_controller.send_body_velocity_commands())

            if Parameters.ENABLE_SETPOINT_DEBUGGING:
                self.print_current_setpoint(setpoints)
                
            time.sleep(Parameters.SETPOINT_PUBLISH_RATE_S)
        loop.close()

    def print_current_setpoint(self, setpoints):
        """Prints the current setpoints for debugging purposes."""
        if setpoints:
            print(f"Sending body velocity commands: {setpoints}")

    def stop(self):
        self.running = False
        self.join()  # Wait for the thread to finish


