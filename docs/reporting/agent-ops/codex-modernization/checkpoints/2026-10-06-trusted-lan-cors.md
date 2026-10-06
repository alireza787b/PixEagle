# Trusted-LAN browser CORS repair

An authenticated Raspberry Pi demo used `trusted_lan_legacy` with empty Host
and Origin lists while switching between Wi-Fi and robot-subnet addresses.
Native QGC video connected, but dashboard API requests failed: HTTP preflight
returned 400 `Disallowed CORS origin`, and auth-session responses omitted
credentialed CORS headers. The browser displayed backend offline despite a
running backend.

The exposure policy now provides the HTTP CORS regex for the existing
address-agnostic trusted-LAN Origin behavior and enables credentialed responses
for that explicit lab setting. FastAPI uses that policy alongside the existing
Host/Origin, route authorization and CSRF middleware. Local-only and explicit
non-empty origin lists retain their boundaries. No route, flight command,
authentication record, firewall rule or config schema is changed.

Validation: ten focused tests cover changing addresses, preflight, credentialed
401 visibility, explicit-list rejection, empty local-only policy and invalid
origins. Python syntax checks and diff whitespace checks pass. Broader backend
CI and deployed browser/QGC acceptance remain required before claiming the
repair complete. Evidence is preserved on the Windows GCS Desktop in
`pixeagle-qgc-diagnostics-20261006-175613`.

The operator explicitly requested any-origin access for this temporary lab.
This allows any HTTP(S) website origin to attempt authenticated API access;
restricted deployments should use exact origin lists. Authentication, role
permissions, CSRF and media authorization still apply. Windows 10 tablet and
robot-subnet client acceptance remain separate target-system tests.
