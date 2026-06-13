# PixEagle API Exposure Boundary

PixEagle's HTTP, MJPEG, WebSocket, and WebRTC-signaling endpoints share one
FastAPI process and one exposure policy. The checked-in default is local-only:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
    - http://127.0.0.1:5077
    - http://localhost:5077
```

`local_only` fails startup when the bind host or a configured CORS origin is
not explicitly loopback. Wildcard CORS origins are prohibited, and CORS
credentials are disabled while PixEagle has no browser-session authentication
contract.

The managed dashboard launchers and generated dashboard `.env` also bind
`127.0.0.1` by default. A non-loopback dashboard bind requires both
`PIXEAGLE_DASHBOARD_HOST` and
`PIXEAGLE_DASHBOARD_EXPOSURE_MODE=trusted_lan_legacy`.
The managed MAVLink2REST launchers likewise require
`PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy` before accepting a
non-loopback HTTP bind.

HTTP requests are rejected before route execution when their `Host` authority
does not match the selected exposure policy. In `local_only`, only loopback
authorities on the configured backend port are accepted. Modern-browser
requests are also rejected when their `Origin` is not allowlisted or
`Sec-Fetch-Site` identifies a cross-site request. Responses set same-site
resource and anti-framing headers. Video and WebRTC-signaling WebSockets
validate `Origin` before acceptance. These controls reduce DNS-rebinding,
browser-to-localhost, and cross-site media exposure; they do not authenticate
callers or protect against a hostile local process.

## Exposure Modes

| Mode | Bind policy | Intended use | Production status |
|------|-------------|--------------|-------------------|
| `local_only` | Explicit loopback only | Local dashboard, SSH tunnel, same-host loopback reverse proxy | Current local-only default |
| `trusted_lan_legacy` | Explicitly permits non-loopback bind | Temporary compatibility on an isolated, trusted network | Unauthenticated; not production-approved |

To use the temporary compatibility mode, both the mode and desired bind must be
set explicitly. Browser origins must be exact; do not use wildcards.

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  API_CORS_ALLOWED_ORIGINS:
    - http://192.168.10.20:3040
```

This mode exposes sensitive video, telemetry, configuration, model-management,
system-management, and flight-adjacent legacy mutations without authentication.
Use it only on a physically/logically isolated trusted network and remove it
after use. It is not a substitute for authentication or authorization.

Existing local `configs/config.yaml` files from older releases may still set
`HTTP_STREAM_HOST: 0.0.0.0` without an exposure mode. Runtime startup coerces
that legacy missing-mode case to `127.0.0.1` instead of preserving broad
exposure. If a deployment truly needs temporary LAN compatibility, add
`API_EXPOSURE_MODE: trusted_lan_legacy` and exact
`API_CORS_ALLOWED_ORIGINS` entries intentionally.

If the dashboard uses a custom port, add both loopback browser origins for that
port to `API_CORS_ALLOWED_ORIGINS`. A non-loopback reverse-proxy browser origin
cannot be used in `local_only`; it remains `trusted_lan_legacy` until the
authenticated remote-browser slice is implemented.

## Current And Planned Controls

Implemented in the secure-default foundation:

- local-only checked-in bind;
- explicit exposure-mode validation;
- startup rejection for contradictory local-only configuration;
- explicit CORS allowlist with wildcard rejection;
- no credentialed wildcard CORS;
- HTTP Host/authority allowlisting;
- HTTP browser Origin/fetch-site rejection before route execution;
- same-site resource and anti-framing response headers;
- WebSocket and WebRTC-signaling Origin rejection before connection acceptance;
- loopback-first Linux and Windows dashboard launchers;
- loopback-first Linux and Windows MAVLink2REST HTTP API launchers;
- tests covering checked-in defaults and fail-closed policy behavior.

Implemented as a non-enforcing authorization foundation:

- typed session, bearer, anonymous, and local-compat principal contracts;
- explicit viewer/operator/admin role bundles and exact machine scopes;
- one declarative policy classification for every declared route and implicit
  FastAPI documentation route;
- local-only treatment for legacy mutations, administration, debug, and SITL
  injection surfaces;
- authenticated media treatment and default-deny handling for missing or
  ambiguous classifications;
- pure authorization-decision tests for scope, CSRF, and loopback behavior.

See the [API security policy](api-security-policy.md). These declarations are
not middleware and do not enable credentials or sessions by themselves.

Still required before authenticated remote operation can be approved:

- authenticated browser/operator sessions and machine bearer tokens;
- CSRF and request-origin enforcement for browser mutations;
- runtime enforcement of the declared role/scope policy for reads, video,
  WebSockets, and mutations;
- authenticated WebSocket/MJPEG/WebRTC signaling;
- typed action enforcement and retirement of immediate legacy mutations;
- security audit events, migration tooling, and adversarial tests.

Until those controls land, use local access or an SSH tunnel for the default
local-only mode. Non-loopback reverse-proxy/VPN browser origins require
temporary `trusted_lan_legacy`. Remote network reachability is not
authorization.

## Operator Checks

Before starting PixEagle:

1. Confirm `API_EXPOSURE_MODE` matches the intended deployment.
2. Confirm `HTTP_STREAM_HOST` is loopback unless temporary legacy exposure is
   explicitly required.
3. Confirm every CORS origin is an exact trusted browser origin.
4. Confirm no firewall or reverse-proxy rule exposes port `5077` to an
   untrusted network.

The API process emits a critical log when it starts with non-loopback
`trusted_lan_legacy` exposure.
