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
credentials are enabled only when `API_AUTH_MODE=browser_session` is selected.

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

Runtime local compatibility trusts only the immediate loopback socket peer.
HTTP `Host` is not accepted as local proof, and proxy-forwarded client identity
headers disable local compatibility and local-only route elevation. PixEagle
cannot reliably detect an externally reachable reverse proxy that strips those
headers, so do not expose `local_compat` through a reverse proxy. Use an SSH
tunnel for local browser operation, or use scoped bearer tokens for machine API
clients. Browser/operator sessions are available through explicit
`API_AUTH_MODE=browser_session` deployments, but production remote-browser
approval still requires TLS/operator deployment hardening, retirement of
remaining legacy tracking/control aliases, adversarial auth/media tests, and
evidence gates.

## Exposure Modes

| Mode | Bind policy | Intended use | Production status |
|------|-------------|--------------|-------------------|
| `local_only` | Explicit loopback only | Same-host dashboard or SSH tunnel | Current local-only default |
| `trusted_lan_legacy` | Explicitly permits non-loopback bind | Temporary compatibility on an isolated, trusted network | Requires scoped API auth or explicit browser-session auth; production remote browser use is not approved yet |

To use the temporary compatibility mode, both the mode and desired bind must be
set explicitly. Browser origins must be exact; do not use wildcards.

```yaml
Streaming:
  API_EXPOSURE_MODE: trusted_lan_legacy
  HTTP_STREAM_HOST: 0.0.0.0
  API_CORS_ALLOWED_ORIGINS:
    - http://192.168.10.20:3040
```

This mode exposes the backend bind/CORS surface beyond loopback. Non-loopback
HTTP, MJPEG, video WebSocket, and WebRTC-signaling requests still pass through
the API authorization runtime and require either scoped bearer credentials or an
explicit browser-session deployment. Use this mode only on a
physically/logically isolated trusted network and remove it after use.

Existing local `configs/config.yaml` files from older releases may still set
`HTTP_STREAM_HOST: 0.0.0.0` without an exposure mode. Runtime startup coerces
that legacy missing-mode case to `127.0.0.1` instead of preserving broad
exposure. If a deployment truly needs temporary LAN compatibility, add
`API_EXPOSURE_MODE: trusted_lan_legacy` and exact
`API_CORS_ALLOWED_ORIGINS` entries intentionally.

If the dashboard uses a custom port, add both loopback browser origins for that
port to `API_CORS_ALLOWED_ORIGINS`. A non-loopback reverse-proxy browser origin
cannot be used in `local_only`. `trusted_lan_legacy` can open the bind/CORS
boundary, but remote browser operation remains deferred until TLS/operator
deployment hardening, retirement of remaining legacy tracking/control aliases,
adversarial auth/media tests, and evidence gates are completed.

## Current And Planned Controls

Implemented in the secure-default foundation:

- local-only checked-in bind;
- explicit exposure-mode validation;
- startup rejection for contradictory local-only configuration;
- explicit CORS allowlist with wildcard rejection;
- no credentialed wildcard CORS;
- credentialed exact-origin CORS only for `API_AUTH_MODE=browser_session`;
- HTTP Host/authority allowlisting;
- HTTP browser Origin/fetch-site rejection before route execution;
- same-site resource and anti-framing response headers;
- WebSocket and WebRTC-signaling Origin rejection before connection acceptance;
- loopback-first Linux and Windows dashboard launchers;
- loopback-first Linux and Windows MAVLink2REST HTTP API launchers;
- tests covering checked-in defaults and fail-closed policy behavior.

Implemented as a runtime authorization foundation:

- typed session, bearer, anonymous, and local-compat principal contracts;
- explicit viewer/operator/admin role bundles and exact machine scopes;
- one declarative policy classification for every declared route and implicit
  FastAPI documentation route;
- `API_AUTH_MODE=local_compat` same-host loopback default,
  `API_AUTH_MODE=machine_bearer` bearer-only mode, and
  `API_AUTH_MODE=browser_session` cookie-session mode;
- external JSON bearer token file with hashed, named, revocable records;
- external JSON browser user file with PBKDF2-SHA256 password hashes;
- typed browser auth routes, HttpOnly session cookies, session CSRF, and
  process-local login throttling;
- HTTP/MJPEG authorization before route execution or streaming response
  creation;
- video WebSocket and WebRTC-signaling authorization before `accept()`;
- refusal to treat `Host` or proxy-forwarded client metadata as local
  transport proof;
- local-only treatment for legacy mutations, administration, debug, and SITL
  injection surfaces;
- authenticated media treatment and default-deny handling for missing or
  ambiguous classifications;
- query-string token rejection.
- dashboard credential-aware API client, login/logout gate, session status
  indicator, CSRF-aware `fetch`/axios boundary, cookie-session MJPEG,
  WebSocket/WebRTC construction, and blob-backed protected downloads/playback.

See the [API security policy](api-security-policy.md). The backend session and
dashboard client/media and durable security-audit foundations exist, but
production remote-browser approval remains open.

Still required before authenticated remote operation can be approved:

- retirement of remaining legacy tracking/control aliases;
- TLS/operator deployment guidance, migration tooling, and adversarial
  browser/session/media tests.

Until those controls land, use local access or an SSH tunnel for the default
local-only mode. Non-loopback reverse-proxy/VPN browser origins are not a
complete browser-operator solution by themselves. Remote network reachability is
not authorization.

## Operator Checks

Before starting PixEagle:

1. Confirm `API_EXPOSURE_MODE` matches the intended deployment.
2. Confirm `HTTP_STREAM_HOST` is loopback unless temporary legacy exposure is
   explicitly required.
3. Confirm every CORS origin is an exact trusted browser origin.
4. Confirm no firewall or reverse-proxy rule exposes port `5077` to an
   untrusted network.
5. For non-loopback machine API clients, set `API_BEARER_TOKEN_FILE` to an
   external JSON token file and grant only the scopes needed by that client.
6. For browser-session tests, set `API_AUTH_MODE=browser_session`, provide an
   external `API_SESSION_USER_FILE`, and use exact CORS origins. Do not approve
   production remote browser operation without the remaining PXE-0064 gates.

The API process emits a critical log when it starts with non-loopback
`trusted_lan_legacy` exposure.
