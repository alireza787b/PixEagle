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
origins. The Pi passed 175 targeted exposure, CORS, route inventory and parameter
reload tests, schema validation (604 parameters, 43 sections), and syntax checks.
After deployment, changing-origin preflights and authenticated status reads
returned 200 with credentialed CORS headers. Live video was observed in the
dashboard and QGC without an aircraft; the operator confirmed Chrome and QGC
worked after signing out and signing in again in QGC. This does not prove
automatic recovery after an external backend restart. Evidence is preserved on
the Windows GCS Desktop in
`pixeagle-qgc-diagnostics-20261006-175613`.

The operator explicitly requested any-origin access for this temporary lab.
This allows any HTTP(S) website origin to attempt authenticated API access;
restricted deployments should use exact origin lists. Authentication, role
permissions, CSRF and media authorization still apply. Windows 10 tablet and
robot-subnet client acceptance remain separate target-system tests.

PR CI passed lint, dashboard and Windows core preview. Its initial backend gate
stopped at stale generated API inventory source hashes. Regenerating on Linux
updated the two changed policy/middleware hashes and two pre-existing stale
hashes; no routes or candidate permissions changed. Full PR CI remains required.
The restricted-Host regression fixture now explicitly supplies the Host allowlist
its name and assertions require; its original failure was reproduced at baseline.

The second backend CI run exposed a restart guard gap: fresh armed-state
telemetry without a discovered aircraft UID was not counted as aircraft
evidence. The guard now considers flight-state evidence before identity
arrival, retaining the required fresh Disarmed state. A router-only connection
without flight-state or aircraft identity remains eligible for backend
administration. Five regression cases cover armed/unknown/disarmed and
router-only states; the existing real restart action tests cover the HTTP
refusal. There is no new policy, route or camera requirement.

Linux closeout: 456 behavior tests passed across native configuration,
Offboard safety, exposure/CORS, parameter reload, routes and documentation.
The source-inventory check was rerun separately after its final hash update.
Schema validation remains current (604 parameters, 43 sections). CI must
renew the complete unit/integration/coverage, dashboard and Windows gates
before merging this PR. Pi sync to the eventual main revision remains a
separate deployment step; these results do not assert a fresh Pi deployment.
