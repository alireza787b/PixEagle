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
