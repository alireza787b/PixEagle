# PixEagle API Security Policy

PixEagle has a declarative, default-deny route security contract in
`src/classes/api_security_policy.py`. The reusable principal, role, scope, and
authorization types live in `src/classes/api_security_types.py`.

The route policy is now consumed by `src/classes/api_auth_runtime.py` and the
FastAPI/WebSocket entry points. The checked-in runtime mode is
`API_AUTH_MODE=local_compat`, which allows same-host loopback socket clients
without credentials and requires other clients to use scoped machine bearer
tokens. Browser users, sessions, cookies, and session-bound CSRF are not
implemented yet.

## Policy Rules

- Every declared HTTP or WebSocket route must match exactly one policy rule.
- FastAPI's implicit OpenAPI and interactive-documentation routes are included.
- A missing or ambiguous route classification resolves to `deny`.
- Planned browser sessions use role-derived scopes and require session-bound
  CSRF for mutations.
- Machine bearer tokens retain their exact assigned scopes; scopes are not
  expanded into an operator or admin role.
- The temporary `local_compat` principal is valid only for same-host loopback
  socket clients with no proxy-forwarded client identity headers.
- Local-only routes require both loopback transport and the declared scope.
- HTTP `Host` is never accepted as proof of local transport.
- Authorization decisions never accept credentials from request-body metadata.

## Access Modes

| Mode | Meaning |
| --- | --- |
| `authenticated` | A valid session or machine principal with every required scope may access the route. |
| `local_only` | The authenticated principal must also connect through a verified loopback client boundary. |
| `deny` | Unclassified, ambiguous, or intentionally blocked routes fail closed. |

## Runtime Auth Modes

Runtime auth is configured under `Streaming`:

```yaml
Streaming:
  API_AUTH_MODE: local_compat
  API_BEARER_TOKEN_FILE: ""
```

| Auth mode | Current behavior |
| --- | --- |
| `local_compat` | Default. Same-host loopback socket clients without credentials receive the fixed local compatibility principal. Non-loopback clients and proxy-forwarded clients must present a valid scoped bearer token. |
| `machine_bearer` | Requires a valid scoped bearer token for every request, including loopback. This mode is for machine/API clients; the current browser dashboard and native media transports cannot operate in it until browser sessions land. |

`API_BEARER_TOKEN_FILE` points to an external JSON file. The file contains
hashed, named, revocable token records:

```json
{
  "tokens": [
    {
      "token_id": "ci-readonly",
      "subject": "ci-agent",
      "token_sha256": "<sha256-of-high-entropy-token>",
      "scopes": ["status:read", "telemetry:read"],
      "enabled": true
    }
  ]
}
```

Plaintext bearer tokens are never stored in checked-in YAML. Tokens are not
accepted in query strings for HTTP, MJPEG, WebSocket, or WebRTC-signaling
routes.

## Roles And Scopes

Session roles are convenience bundles. Machine credentials use exact scopes.

| Role | Intended authority |
| --- | --- |
| `viewer` | Read operational status, telemetry, media, model inventory, recordings, control state, safety state, actions, and system state. Full configuration is excluded. |
| `operator` | Viewer authority plus configuration reads, media operations, model selection, recording/control mutations, and typed-action execution. It cannot install/delete models, write config or safety state, administer the system, or inject SITL faults. |
| `admin` | All declared scopes. Local-only and CSRF restrictions still apply. |

Declared scope families are status, telemetry, media, config, models,
recordings, control, safety, actions, system, SITL injection, and debug.
Changing the role bundles or adding a scope requires policy tests and docs in
the same slice.

## Route Treatment

| Route family | Access treatment |
| --- | --- |
| Status, telemetry, media, config, models, recordings, control, safety, typed actions, and system reads | Authenticated with the matching read scope. |
| Runtime mutations | Authenticated with the matching write/execute scope, mutation audit, and session CSRF. |
| MJPEG, video WebSocket, and WebRTC signaling | Authenticated `media:read`; authentication must complete before streaming or WebSocket acceptance. |
| Legacy `/commands/*` control mutations | Local-only until typed-action migration and retirement. |
| Deprecated `/api/yolo/*` aliases | Local-only until canonical model-route migration and retirement. |
| Process restart, safety bypass, docs/OpenAPI, debug data, and SITL injectors | Local-only with elevated scopes; SITL injectors also retain their independent runtime enablement gate. |
| Unknown or multiply classified route | Denied. |

POST config validation, diff, and defaults-sync planning are classified as
read/preview operations. They do not receive mutation authority merely because
they use POST.

## Enforcement Status

Implemented:

- route policy enforcement before HTTP route execution;
- MJPEG authorization before the streaming response is returned;
- video WebSocket and WebRTC-signaling authorization before `accept()`;
- default-deny handling for unclassified paths;
- loopback-only local compatibility;
- refusal to infer local compatibility from `Host` or proxy-forwarding
  metadata;
- hashed machine bearer token loading from an external JSON file;
- exact bearer scopes and no query-string token transport.

Still required under PXE-0064:

1. Browser/operator users, password hashing, secure session cookies,
   login/logout/session routes, and brute-force controls.
2. Real session-bound CSRF for browser mutations and credentialed exact-origin
   CORS behavior.
3. Durable security audit events using the authenticated principal as actor.
4. Dashboard migration to one credential-aware API client plus authenticated
   media transports.
5. Adversarial tests, migration tooling, typed-action-only enforcement, and
   final legacy mutation retirement.

Until browser sessions land, use same-host loopback local access, SSH tunnels,
or machine bearer tokens for non-loopback API clients. Do not place
`local_compat` behind an externally reachable reverse proxy. Remote browser
operation is still not approved.

## Verification

`tests/test_api_security_policy.py` proves exact coverage of all 132 declared
routes plus FastAPI's implicit docs routes. `tests/unit/core_app/
test_api_auth_runtime.py` covers token-file loading, exact scopes, local-compat
behavior, query-token rejection, and default-deny transport decisions.
`tests/unit/core_app/test_api_exposure_policy.py` covers the FastAPI and
WebSocket integration path. These tests are part of `make phase0-check`.
