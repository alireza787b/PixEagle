# app/api/endpoints.py
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from config.config import setup_xpc_path, load_config
import sys
import logging

# Setup the X-Plane Connect path
setup_xpc_path()
import xpc

class DatarefResponse(Dict[str, Any]):
    """
    Pydantic model for Dataref response.
    
    Attributes:
        dataref (str): The name of the dataref.
        value (Any): The value of the dataref.
        status (str): The status of the retrieval ('success' or 'error').
        message (str): Additional message for errors.
    """
    dataref: str
    value: Any
    status: str
    message: str = None

class CommandResponse(Dict[str, Any]):
    """
    Pydantic model for Command response.
    
    Attributes:
        command (str): The command sent to X-Plane.
        status (str): The status of the command execution ('success' or 'error').
        message (str): Additional message for errors.
    """
    command: str
    status: str
    message: str = None

class FastAPIHandler:
    def __init__(self):
        """
        Initialize the FastAPIHandler.

        Sets up the FastAPI application, configures middleware, and initializes
        the X-Plane Connect instance.
        """
        self.app = FastAPI()
        self.router = APIRouter()
        self.config = load_config()

        # Setup CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup endpoints
        self.router.get("/datarefs", response_model=List[DatarefResponse])(self.get_datarefs)
        self.router.post("/command", response_model=CommandResponse)(self.send_command)
        self.app.include_router(self.router)

        # Initialize X-Plane Connect instance
        self.xpc_instance = None
        self.connect_to_xplane()

    def connect_to_xplane(self):
        """
        Attempt to connect to X-Plane using X-Plane Connect.

        Sets self.xpc_instance to the XPlaneConnect instance if successful.
        Logs an error if the connection fails.
        """
        try:
            self.xpc_instance = xpc.XPlaneConnect()
            logging.info("Connected to X-Plane successfully.")
        except Exception as e:
            logging.error(f"Failed to connect to X-Plane: {e}")
            self.xpc_instance = None

    async def get_datarefs(self, datarefs: str):
        """
        Fetch values of specified datarefs.

        Args:
            datarefs (str): Comma-separated list of datarefs.

        Returns:
            List[DatarefResponse]: A list of DatarefResponse objects with the dataref values and statuses.

        Example:
            Request: GET /datarefs?datarefs=sim/cockpit2/gauges/indicators/altitude_ft_pilot,sim/flightmodel/position/latitude
            Response: [
                {
                    "dataref": "sim/cockpit2/gauges/indicators/altitude_ft_pilot",
                    "value": 5000.0,
                    "status": "success"
                },
                {
                    "dataref": "sim/flightmodel/position/latitude",
                    "value": 37.615223,
                    "status": "success"
                }
            ]
        """
        if not self.xpc_instance:
            self.connect_to_xplane()
            if not self.xpc_instance:
                raise HTTPException(status_code=500, detail="Could not connect to X-Plane.")

        try:
            datarefs_list = datarefs.split(',')
            values = self.xpc_instance.getDREFs(datarefs_list)
            response = []
            for dataref, value in zip(datarefs_list, values):
                if value is None:
                    response.append({
                        "dataref": dataref,
                        "value": None,
                        "status": "error",
                        "message": "Dataref not found"
                    })
                else:
                    response.append({
                        "dataref": dataref,
                        "value": value,
                        "status": "success"
                    })
            return response
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error fetching datarefs: {str(e)}")

    async def send_command(self, command: str):
        """
        Send a command to X-Plane.

        Args:
            command (str): The command to send to X-Plane.

        Returns:
            CommandResponse: The status of the command execution.

        Example:
            Request: POST /command
            {
                "command": "sim/autopilot/altitude_hold"
            }
            Response:
            {
                "command": "sim/autopilot/altitude_hold",
                "status": "success"
            }
        """
        if not self.xpc_instance:
            self.connect_to_xplane()
            if not self.xpc_instance:
                raise HTTPException(status_code=500, detail="Could not connect to X-Plane.")

        try:
            self.xpc_instance.sendCOMM(command)
            return {"command": command, "status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error sending command: {str(e)}")

    def start(self):
        """
        Start the FastAPI server using the configuration file settings.

        Loads host and port settings from the configuration file and starts the server.

        Example:
            Configuration file (config.json):
            {
                "server": {
                    "host": "0.0.0.0",
                    "port": 8000
                }
            }

            Starting the server:
            python app/main.py
        """
        import uvicorn
        host = self.config['server']['host']
        port = self.config['server']['port']
        uvicorn.run(self.app, host=host, port=port)
