#src\udp_to_websocket.py
import asyncio
import json
import socket
from aiohttp import web
from classes.parameters import Parameters
# UDP server configuration
UDP_HOST = Parameters.UDP_HOST
UDP_PORT = Parameters.UDP_PORT

WEBSOCK_HOST = Parameters.WEBSOCK_HOST
WEBSOCK_PORT = Parameters.WEBSOCK_PORT

# Create a UDP socket
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind((UDP_HOST, UDP_PORT))

clients = []

async def udp_listener():
    loop = asyncio.get_event_loop()
    while True:
        data, _ = await loop.run_in_executor(None, udp_socket.recvfrom, 4096)
        message = data.decode('utf-8')
        print(f"Received UDP data: {message}")
        for ws in clients:
            await ws.send_str(message)

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.append(ws)
    print("WebSocket connection established")

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            print(f"Received message from client: {msg.data}")
        elif msg.type == web.WSMsgType.ERROR:
            print(f"WebSocket connection closed with exception {ws.exception()}")

    print("WebSocket connection closed")
    clients.remove(ws)
    return ws

async def start_background_tasks(app):
    app['udp_listener'] = asyncio.create_task(udp_listener())

async def cleanup_background_tasks(app):
    app['udp_listener'].cancel()
    await app['udp_listener']

app = web.Application()
app.add_routes([web.get('/ws', websocket_handler)])
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

if __name__ == "__main__":
    web.run_app(app, port=5551)
