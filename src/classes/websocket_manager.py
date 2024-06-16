import logging
from aiohttp import web

class WebSocketManager:
    _instance = None

    def __init__(self):
        if WebSocketManager._instance is not None:
            raise Exception("This class is a singleton!")
        self.clients = []
        WebSocketManager._instance = self

    @staticmethod
    def get_instance():
        if WebSocketManager._instance is None:
            WebSocketManager()
        return WebSocketManager._instance

    async def register(self, ws):
        self.clients.append(ws)
        logging.info(f"Client connected. Total clients: {len(self.clients)}")

    async def unregister(self, ws):
        self.clients.remove(ws)
        logging.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def broadcast(self, message):
        for ws in self.clients:
            await ws.send_str(message)

websocket_manager = WebSocketManager.get_instance()
