# PixEagle API Security Policy

PixEagle has a declarative, default-deny route security contract in
`src/classes/api_security_policy.py`. The reusable principal, role, scope, and
authorization types live in `src/classes/api_security_types.py`.

The route policy is now consumed by `src/classes/api_auth_runtime.py` and the
FastAPI/WebSocket entry points. The checked-in runtime mode is
`API_AUTH_MODE=local_compat`, which allows same-host loopback socket clients
without credentials and requires other clients to use scoped machine bearer
tokens. `API_AUTH_MODE=browser_session` adds external hashed users, HttpOnly
session cookies, session-bound CSRF for browser mutations, and typed
`/api/v1/auth/...` routes. The dashboard now uses one credential-aware client
for API calls, login/logout/session state, CSRF injection, cookie-session media,
and authenticated downloads/playback.

## Policy Rules

- Every declared HTTP or WebSocket route must match exactly one policy rule.
- FastAPI's implicit OpenAPI and interactive-documentation routes are included.
- A missing or ambiguous route classification resolves to `deny`.
- Browser sessions use role-derived scopes and require session-bound CSRF for
  mutations.
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
| `public` | Explicit bootstrap routes such as auth session status and login. |
| `authenticated` | A valid session or machine principal with every required scope may access the route. |
| `local_only` | The authenticated principal must also connect through a verified loopback client boundary. |
| `deny` | Unclassified, ambiguous, or intentionally blocked routes fail closed. |

## Runtime Auth Modes

Runtime auth is configured under `Streaming`:

```yaml
Streaming:
  API_AUTH_MODE: local_compat
  API_BEARER_TOKEN_FILE: ""
  API_SESSION_USER_FILE: ""
```

| Auth mode | Current behavior |
| --- | --- |
| `local_compat` | Default. Same-host loopback socket clients without credentials receive the fixed local compatibility principal. Non-loopback clients and proxy-forwarded clients must present a valid scoped bearer token. |
| `machine_bearer` | Requires a valid scoped bearer token for every request, including loopback. This mode is for machine/API clients. Native browser media transports cannot attach bearer headers, so browser dashboard operation should use `browser_session`. |
| `browser_session` | Requires an external hashed user file. Login creates an HttpOnly cookie session, returns a session-bound CSRF token, enables credentialed exact-origin CORS, and authorizes HTTP, MJPEG, video WebSocket, and WebRTC-signaling routes through the same policy engine. |

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

`API_SESSION_USER_FILE` points to an external JSON file. The file contains
hashed browser/operator user records:

```json
{
  "users": [
    {
      "username": "operator",
      "role": "operator",
      "password_pbkdf2_sha256": "pbkdf2_sha256$310000$<base64-salt>$<base64-digest>",
      "enabled": true
    }
  ]
}
```

Use `classes.api_auth_runtime.make_user_record()` or an equivalent offline
PBKDF2-SHA256 generator to create records. Do not put plaintext passwords in
checked-in YAML or JSON. The backend rejects user records that contain
`password` or `plaintext_password` fields.

Browser-session settings:

| Setting | Purpose |
| --- | --- |
| `API_SESSION_USER_FILE` | External JSON user file for `browser_session`. |
| `API_SESSION_TTL_SECONDS` | In-memory session lifetime. |
| `API_SESSION_COOKIE_NAME` | HttpOnly session cookie name. |
| `API_SESSION_COOKIE_SECURE` | Set `true` when PixEagle is served over HTTPS. |
| `API_CSRF_HEADER_NAME` | Header carrying the session-bound CSRF token for browser mutations. |

The public login route has a process-local failed-attempt throttle. This is not
a substitute for deployment-level audit, alerting, lockout policy, or TLS.

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
| `/api/v1/auth/session` and `/api/v1/auth/login` | Public bootstrap routes. Login is security-critical and rate-limited; it does not require CSRF because no session exists yet. |
| `/api/v1/auth/logout` | Authenticated browser session plus session CSRF. |
| Status, telemetry, media, config, models, recordings, control, safety, typed actions, and system reads | Authenticated with the matching read scope. |
| Runtime mutations | Authenticated with the matching write/execute scope, mutation audit, and session CSRF. |
| MJPEG, video WebSocket, WebRTC signaling, and `/api/v1/streams/media-health` | Authenticated `media:read`; authentication must complete before streaming, WebSocket acceptance, or media-health disclosure. |
| Tracking/control mutations | Typed `/api/v1/actions/*` routes with confirmation/idempotency/action-resource semantics. Retired `/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, `/commands/cancel_activities`, `/commands/start_tracking`, `/commands/stop_tracking`, `/commands/redetect`, `/commands/toggle_segmentation`, `/commands/toggle_smart_mode`, and `/commands/smart_click` are not registered HTTP routes. |
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
- exact bearer scopes and no query-string token transport;
- external hashed browser user loading;
- typed `/api/v1/auth/session`, `/api/v1/auth/login`, and
  `/api/v1/auth/logout` routes;
- HttpOnly browser sessions with session-bound CSRF;
- process-local login failure throttling;
- credentialed exact-origin CORS when `API_AUTH_MODE=browser_session`;
- durable sanitized JSONL security audit events for auth decisions,
  login/logout outcomes, denied requests, sensitive reads, mutations, and
  security-critical routes;
- fail-closed handling when an allowed mutation or security-critical request
  cannot be durably audited;
- dashboard `apiClient` boundary for credentialed `fetch`, axios CSRF
  injection, auth-failure refresh, media WebSocket construction, MJPEG image
  credentials, and blob-backed protected downloads/playback;
- dashboard login gate and session status/logout controls;
- frontend guard tests that reject raw production `fetch`, direct axios package
  imports, direct `new WebSocket`, and protected endpoint `href` bypasses.

Still required under PXE-0064:

1. Deployment evidence for the guarded credential rotation and TLS/reverse-
   proxy runbook, including service-user ownership and secure handoff.
2. Broader adversarial/browser-session tests, especially around expiry,
   multi-tab logout, large protected media playback, and role-denied UX.
3. Production remote-profile hardening evidence tying credentials, TLS, Host,
   CORS, media, and operator roles into a repeatable deployment workflow.

Use same-host loopback local access, SSH tunnels, scoped machine bearer tokens,
or explicit `browser_session` test deployments only. Remote native media
clients such as a future authenticated QGroundControl HTTP/WebSocket build need
`media:read` bearer credentials and the exposure profile described in
[Remote Media Security](../video/04-streaming/remote-media-security.md). Do not
place `local_compat` behind an externally reachable reverse proxy. Remote
browser operation is not production-approved until TLS/operator credential
hardening, adversarial auth/media tests, and evidence gates are complete.

## Verification

`tests/test_api_security_policy.py` proves exact coverage of all 136 declared
routes plus FastAPI's implicit docs routes. `tests/unit/core_app/
test_api_auth_runtime.py` covers token-file loading, exact scopes, local-compat
behavior, browser-session user loading, CSRF, login throttling, query-token
rejection, and default-deny transport decisions.
`tests/unit/core_app/test_api_exposure_policy.py` covers the FastAPI and
WebSocket integration path. `tests/test_test_hygiene.py` covers the dashboard
auth-client source guard. Dashboard Jest tests cover the shared client,
login gate, and scoped action-button behavior. The Python tests are part of
`make phase0-check`.
