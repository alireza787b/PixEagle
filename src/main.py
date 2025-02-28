import logging
from classes.flow_controller import FlowController

def main():
    """
    Main function to initialize the Pixeagle application and run the main loop.
    Sets up logging, starts the video capture/processing pipeline and the FastAPI server,
    then enters a loop to display frames and handle user key inputs.
    """
    # Configure logging (format and level can be further adjusted as needed)
    logging.basicConfig(level=logging.INFO, 
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Starting main application...")

    # Initialize the FlowController (which sets up the AppController and FastAPI server)
    flow_controller = FlowController()
    
    # Start video capture and processing (starts background threads)
    flow_controller.start()
    
    # Enter the main loop to display frames and check for key inputs
    flow_controller.main_loop()

if __name__ == "__main__":
    main()
