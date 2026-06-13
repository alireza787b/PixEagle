# PixEagle API Security Policy

PixEagle has a declarative, default-deny route security contract in
`src/classes/api_security_policy.py`. The reusable principal, role, scope, and
authorization types live in `src/classes/api_security_types.py`.

This is a policy foundation, not runtime authentication. The current slice
does not create users, sessions, cookies, bearer tokens, credential storage, or
authorization middleware. Existing local-only compatibility behavior remains
unchanged until the enforcement slices are complete and tested end to end.

## Policy Rules

- Every declared HTTP or WebSocket route must match exactly one policy rule.
- FastAPI's implicit OpenAPI and interactive-documentation routes are included.
- A missing or ambiguous route classification resolves to `deny`.
- Browser sessions use role-derived scopes and require session-bound CSRF for
  mutations.
- Machine bearer tokens retain their exact assigned scopes; scopes are not
  expanded into an operator or admin role.
- The temporary `local_compat` principal is valid only for loopback clients.
- Local-only routes require both loopback transport and the declared scope.
- Authorization decisions never accept credentials from request-body metadata.

## Access Modes

| Mode | Meaning |
| --- | --- |
| `authenticated` | A valid session or machine principal with every required scope may access the route. |
| `local_only` | The authenticated principal must also connect through a verified loopback client boundary. |
| `deny` | Unclassified, ambiguous, or intentionally blocked routes fail closed. |

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

## Enforcement Sequence

The following work remains under PXE-0064:

1. Credential configuration, password hashing, session storage, secure cookie
   lifecycle, login/logout/status routes, and brute-force controls.
2. Named, hashed, revocable machine tokens with exact scopes and no URL query
   token support.
3. Authentication middleware that creates the principal and applies this
   policy before route execution, MJPEG body production, or WebSocket accept.
4. Real session-bound CSRF for browser mutations and credentialed exact-origin
   CORS behavior.
5. Durable security audit events using the authenticated principal as actor.
6. Dashboard migration to one credential-aware API client plus authenticated
   media transports.
7. Adversarial tests, migration tooling, typed-action-only enforcement, and
   final legacy mutation retirement.

Until those slices are complete, PixEagle remains local-only by default. The
temporary `trusted_lan_legacy` mode is unauthenticated and not
production-approved.

## Verification

`tests/test_api_security_policy.py` proves exact coverage of all 132 declared
routes plus FastAPI's implicit docs routes, default-deny resolution, dynamic
path matching, least-privilege role behavior, exact bearer scopes, CSRF
semantics, loopback restrictions, media treatment, and legacy/SITL boundaries.
The test is part of `make phase0-check`.
