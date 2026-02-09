# src/main.py
import os
import logging

# Disable Ultralytics runtime auto-installs in production runtime.
# Dependencies should be installed during init/setup, not during live inference.
os.environ.setdefault("YOLO_AUTOINSTALL", "False")

from classes.flow_controller import FlowController

def main():
    """
    Main function to initialize the application and run the main loop.
    """
    logging.basicConfig(level=logging.INFO)
    logging.debug("Starting main application...")

    flow_controller = FlowController()
    flow_controller.main_loop()

if __name__ == "__main__":
    main()
 
