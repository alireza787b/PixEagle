import queue
import threading
import asyncio
from classes.px4_controller import PX4Controller

class DroneControlThread(threading.Thread):
    def __init__(self, command_queue):
        threading.Thread.__init__(self)
        self.command_queue = command_queue
        self.px4_controller = PX4Controller()
        self.loop = asyncio.new_event_loop()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.drone_control_loop())

    async def drone_control_loop(self):
        await self.px4_controller.connect()
        while True:
            command = await self.loop.run_in_executor(None, self.command_queue.get)
            if command[0] == 'start_following':
                await self.px4_controller.start_offboard_mode()
            elif command[0] == 'stop_following':
                await self.px4_controller.stop_offboard_mode()
            elif command[0] == 'send_velocity':
                _, vel_x, vel_y, vel_z = command
                await self.px4_controller.send_velocity_commands(vel_x, vel_y, vel_z)
            elif command[0] == 'exit':
                break
        await self.px4_controller.disconnect()


