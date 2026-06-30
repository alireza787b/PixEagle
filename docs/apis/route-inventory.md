# PixEagle Route Inventory

Phase 0 freezes the current FastAPI route surface before `/api/v1` migration.
The authoritative guard is `tests/test_api_route_inventory.py`.

Current static inventory from `src/classes/fastapi_handler.py` and
`src/classes/fastapi_api_v1_routes.py`:

- total declared route pairs: 133
- declared HTTP route pairs: 131
- `GET`: 74
- `POST`: 53
- `PUT`: 2
- `DELETE`: 2
- `WEBSOCKET`: 2
- duplicate method/path pairs: 0

FastAPI also creates local documentation routes for `/openapi.json`, `/docs`,
`/docs/oauth2-redirect`, and `/redoc`. Their `GET` and `HEAD` policy pairs are
tracked separately because they are framework-provided rather than PixEagle
route declarations.

This inventory intentionally uses AST parsing instead of app instantiation.
Instantiating `FlowController`, `AppController`, or `FastAPIHandler` can touch
video, MAVLink, model, threading, and Uvicorn runtime paths. Route inventory must
stay side-effect-free.

`tests/test_api_security_policy.py` independently requires every declared
method/path pair to match exactly one default-deny security rule. See the
[API security policy](api-security-policy.md). Policy classification does not
yet mean runtime authentication is enabled.

During API modernization, new routes should be added under `/api/v1/...`.
Legacy routes should remain only as temporary compatibility aliases with
deprecation tracking and route inventory updates.
