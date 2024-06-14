import asyncio
import json
import random
from datetime import datetime
from aiohttp import web

def normalize(value, min_value, max_value):
    return (value - min_value) / (max_value - min_value) * 2 - 1

async def tracker_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    while True:
        x1 = random.uniform(0, 10)
        y1 = random.uniform(10, 20)
        x2 = random.uniform(20, 30)
        y2 = random.uniform(30, 40)

        # Normalize bounding box and center
        bounding_box = [
            normalize(x1, 0, 30),
            normalize(y1, 10, 40),
            normalize(x2, 0, 30),
            normalize(y2, 10, 40)
        ]
        center = [
            normalize((x1 + x2) / 2, 0, 30),
            normalize((y1 + y2) / 2, 10, 40)
        ]

        data = {
            'bounding_box': bounding_box,
            'center': center,
            'timestamp': datetime.utcnow().isoformat(),
            'tracker_started': True
        }
        await ws.send_str(json.dumps(data))
        await asyncio.sleep(1)  # Send data every second

    return ws

app = web.Application()
app.add_routes([web.get('/ws', tracker_handler)])

if __name__ == "__main__":
    web.run_app(app, port=5551)
