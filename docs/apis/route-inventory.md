# PixEagle Route Inventory

Phase 0 freezes the current FastAPI route surface before `/api/v1` migration.
The authoritative guard is `tests/test_api_route_inventory.py`.

Current static inventory from `src/classes/fastapi_handler.py`:

- total routes: 117
- `GET`: 65
- `POST`: 46
- `PUT`: 2
- `DELETE`: 2
- `WEBSOCKET`: 2
- duplicate method/path pairs: 0

This inventory intentionally uses AST parsing instead of app instantiation.
Instantiating `FlowController`, `AppController`, or `FastAPIHandler` can touch
video, MAVLink, model, threading, and Uvicorn runtime paths. Route inventory must
stay side-effect-free.

During API modernization, new routes should be added under `/api/v1/...`.
Legacy routes should remain only as temporary compatibility aliases with
deprecation tracking and route inventory updates.
