# PXE-0148: Bearer-Token Lifecycle

Implemented the bearer-token management slice in the isolated
`codex/bearer-token-management` worktree based on the clean v7.0.0 baseline.
The main PixEagle checkout and frozen QGC candidate were not modified.

The implementation adds hash-only atomic token persistence, typed
administrator routes, compact dashboard create/copy/revoke controls, explicit
bounded and lifetime expiry choices, process-local last-authenticated reporting, and hot
media revocation across MJPEG, video WebSocket, and WebRTC signaling. Token
administration requires a current admin browser session, CSRF, and durable
audit; even a bearer credential with `system:admin` cannot administer tokens.

The final security review separated lab and production token stores, made local
profile transitions clear credential paths, and extended browser-demo cleanup
to remove only the lab store. The dashboard now renders exact scopes, protects
the one-time secret until explicit dismissal, and guides an administrator
through revocation if token issuance has an ambiguous response.

Local backend, setup (`160`), policy/docs, generated-candidate, schema,
dashboard (`57` suites / `384` tests), lint, and build gates pass. End-to-end
QGC bearer use and revocation remain the next
operator acceptance step; no hardware, PX4, deployment, or field claim was
made.
