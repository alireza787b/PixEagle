import asyncio
import logging
import signal
import sys
from aiohttp import web
from classes.parameters import Parameters
from classes.websocket_manager import websocket_manager

logging.basicConfig(level=logging.DEBUG)

async def handle_websocket(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    logging.info('Client connected to video stream')
    print("Client connected to video stream")

    await websocket_manager.register(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                logging.debug(f'Received message: {msg.data}')
            elif msg.type == web.WSMsgType.ERROR:
                logging.error(f'WebSocket connection closed with exception: {ws.exception()}')
    except Exception as e:
        logging.error(f'Exception in WebSocket handling: {e}')
    finally:
        await websocket_manager.unregister(ws)
        logging.info('Client disconnected from video stream')
        print("Client disconnected from video stream")

    return ws

async def init_app():
    app = web.Application()
    app.router.add_get(Parameters.VIDEO_STREAM_URI, handle_websocket)
    return app

def run_app():
    loop = asyncio.new_event_loop()  # Create a new event loop
    asyncio.set_event_loop(loop)  # Set it as the current event loop
    app = loop.run_until_complete(init_app())
    web.run_app(app, host=Parameters.WEBSOCK_HOST, port=Parameters.WEBSOCK_PORT)

def signal_handler(sig, frame):
    print("\nSignal received, shutting down gracefully...")
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    print(f"Starting Video Streaming WebSocket Server at {Parameters.WEBSOCK_HOST}:{Parameters.WEBSOCK_PORT}")
    try:
        run_app()
    except KeyboardInterrupt:
        print("Interrupted by user, shutting down...")
    finally:
        print("Shutdown complete")
        sys.exit(0)
