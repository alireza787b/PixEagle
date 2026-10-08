# PixEagle Dashboard

React operator console for PixEagle live video, tracker/follower state,
recordings, models, and configuration.

## Local Development

```bash
npm install
npm start
```

Default development URL:

```text
http://localhost:3040
```

The backend is local-only by default at `http://127.0.0.1:5077`. Use an SSH
tunnel for remote operator access unless a deployment has passed the remaining
remote-browser gates.

## Auth Boundary

The dashboard uses `src/services/apiClient.js` as the single API boundary:

- all production `fetch` calls go through `apiFetch`;
- production axios users import the client wrapper, not `axios` directly;
- unsafe HTTP methods automatically include the session CSRF header returned by
  `/api/v1/auth/session` or `/api/v1/auth/login`;
- cookies are browser-managed HttpOnly session cookies;
- video WebSocket and WebRTC signaling use cookie-session browser transport,
  not bearer headers or query tokens;
- protected recordings/model downloads are fetched as authenticated blobs.

`API_AUTH_MODE=local_compat` keeps same-host local development simple.
`API_AUTH_MODE=browser_session` shows the operator login gate and uses the
typed `/api/v1/auth/*` routes. `API_AUTH_MODE=machine_bearer` is for machine
API clients and intentionally blocks the browser dashboard.

## Validation

```bash
npm test -- --watchAll=false
npm run build
```

The backend Phase 0 guard also contains a source hygiene test that rejects new
production raw `fetch`, direct axios package imports, direct `new WebSocket`,
and protected endpoint `href` bypasses outside the approved client boundary.

## Remaining Production Gates

The dashboard credential-aware client/media foundation is implemented. Remote
browser operation is still not production-approved until TLS/operator
deployment hardening, broader end-to-end browser/session/media evidence, and
operator acceptance gates are complete. Legacy tracking/control HTTP aliases
have been replaced by typed `/api/v1/actions/*` routes and are no longer
registered.

## Camera hold controls

When the camera advertises `manual_begin` and `manual_update`, held pointer and
keyboard controls use the shared expiring camera gesture API. Begin establishes
ownership; the first acknowledged renewal authorizes motion. Renewals run every
100 ms with at most one outstanding update. Release, focus loss, source changes,
and hidden/unmounted controls request a scoped Stop. A stalled browser cannot
renew the backend's 350 ms lease. These are software expiry guarantees, not a
claim about physical motor stopping or device behavior after process death.

Home and camera-mode changes wait for the current gesture's Stop and use its
returned ownership guard. Errors from obsolete gestures cannot replace current
command feedback; real transmission errors remain visible after automatic Stop.
Older providers retain bounded steps, and assistive clicks without a held pointer
or key remain one discrete step. No vendor protocol or angle remapping belongs
in dashboard controls.


## Video delivery feedback

WebSocket JPEG advertises support for adaptive dimensions. Each JPEG records a
local monotonic receipt timestamp. A frame ACK is sent after canvas drawing,
a decode failure, or supersession, with the outcome explicitly distinguished.
Successful feedback includes receipt-to-canvas-draw milliseconds; this excludes
camera capture and network delay and does not prove physical display scanout.
Queue admission alone never reports a displayed frame. The renderer retains one
active decode plus the latest pending frame, and target coordinates use the
current canvas aspect ratio after resolution changes.
