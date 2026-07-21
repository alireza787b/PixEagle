# Phase 5 Beta.16 Browser-Ready Bootstrap Checkpoint

Date: 2026-07-21  
Phase: 5  
Issues: PXE-0120, PXE-0121, PXE-0124  
Status: implementation and local gates complete; maintainer VPS acceptance pending

## Trigger

A fresh Full AI Ubuntu installation completed its dependencies, but the first
managed-service start failed while setup still held the source/environment
resource. Systemd retried after lock release and eventually became healthy,
which made the failure intermittent and the CLI appear stuck. The operator also
expected the one-line beginner path to end at a browser-reachable dashboard
with credentials instead of a stopped local-only checkout.

## Root Causes

1. Service onboarding could start or reboot before the outer setup supervisor
   released its lock. Runtime components correctly request shared resource
   locks, so that ordering was self-conflicting.
2. `systemctl start` blocked while the cold dashboard build ran and emitted no
   bounded progress through `pixeagle-service`.
3. Lock status treated every active descriptor alike, so a shared runtime reader
   looked like an unexplained setup owner.
4. The one-line bootstrap and browser-demo wrapper were separate workflows.
   No final bootstrap step selected the host, created a lab account, handled
   UFW, started the runtime, checked HTTP, and printed one acceptance URL.
5. The default MAVSDK link retained the deprecated ambiguous `udp://` syntax.

## Implemented Contract

- Setup publishes and verifies all required components under the exclusive
  transaction, releases it, and only then offers service onboarding.
- Service onboarding can install the command, enable boot auto-start, and add
  SSH hints. It never starts PixEagle or reboots the host.
- `pixeagle-service start/restart` queues systemd with `--no-block`, reports
  state every five seconds, waits for the exact runtime identity for at most
  five minutes, and explains that interrupting the wait does not cancel the job.
- `make setup-status` reports `idle`, `exclusive_setup`, or
  `shared_or_unattributed` and gives lifecycle commands without deleting locks.
- The interactive one-line installer offers a final browser lab. Enter accepts
  the detected address and `admin/admin`; a public IP prints the plain-HTTP
  warning. Active UFW receives TCP 3040 and 5077 rules, then the bundled-video
  dashboard/backend runtime starts and must return a local HTTP page.
- The lab does not expose MAVSDK, MAVLink2REST, MAVLink UDP, or PX4 command
  sidecars. A cloud/provider firewall is outside the host and remains an
  explicit remote-receipt check.
- PX4 defaults, examples, schema, tests, and maintained helper scripts use
  explicit MAVSDK v3 `udpin://`/`tcpout://` direction.

## Validation

- Focused installer/setup/service/lock/PX4/API slice: 679 passed, 1 skipped.
- Maintained SIH/SITL plan-contract suite after URI migration: 74 passed.
- Required Phase 0: 482 passed, one upstream deprecation warning.
- Required API route/reload gate: 72 passed.
- Schema generation check: 40 sections, 535 parameters, current.
- Dashboard touched tests: 2 suites, 11 tests passed.
- Dashboard production build: compiled successfully for beta.16.
- Bash syntax: all changed scripts passed; Phase 0 also parsed every shell file.
- ShellCheck: no new warnings; only existing dynamic-source informational notes.
- Python syntax: changed Python modules and MAVSDK fixtures compiled.

## Claim Boundary

This checkpoint does not claim remote browser receipt, public WebSocket/MJPEG
receipt, PX4/SIH/SITL/HIL, QGC, Raspberry Pi, Jetson, GStreamer receiver,
production TLS, field, or aircraft success. It does not publish a beta.16 tag.

## Next Gate

1. Push the reviewed candidate to `main` and let required CI finish.
2. On the disposable VPS, rerun the documented one-line command from a clean or
   safely repairable state. Accept the browser lab and verify the printed URL,
   `admin/admin` login, video, HTTP/WebSocket transport, logs, and clean source.
3. Correct only evidence-backed failures, then publish beta.16.
4. Repeat the exact released Core-first guide on Raspberry Pi before any target
   hardware readiness claim.
