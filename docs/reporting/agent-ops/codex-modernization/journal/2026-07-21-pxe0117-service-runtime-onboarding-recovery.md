# PXE-0117 Journal: Service Runtime And Installer Recovery

**Date:** 2026-07-21 UTC

The maintainer supplied a fresh Ubuntu 24.04 Full AI transcript and a failed
systemd start after reboot. The evidence showed an avoidable `setuptools`
upgrade/downgrade cycle, the known single-OpenCV-provider metadata exception,
and an ownership false positive caused by canonical PixEagle markers leaking
into both the systemd supervisor and the outer lock-launcher ancestor.
`/proc` inspection also raced normal process exit. The optional directory
helper made `pixeagle start` look like a shell `cd` invocation, and the final
summary did not plainly distinguish manual start, managed service start, and
local-only authentication.

The slice keeps the ownership scanner fail-closed while moving canonical
markers to the actual lifecycle/component processes. Session creation now
publishes those markers atomically and the service supervisor requires the
complete healthy pane contract before systemd readiness. It removes
independent setuptools upgrading, uses explicit pip warning flags, validates
the OpenCV distribution version namespace, hardens transient `/proc` reads,
separates service disable from uninstall, makes the shortcut and summaries
explicit, and records a canonical-updater repair path. No VPS wipe or service
installation was performed from the development workspace.

Exact candidate `f991a4c1` passed `121` focused dependency/installer/runtime
tests, the `72` required API/reload tests, schema and Phase 0 (`477 passed, 1
warning`), shell/static gates, and dashboard `348` tests/lint/build. Its
dashboard-inclusive clean-checkout handoff passed `27/27` commands at
`evidence/2026-07-21-pxe0117-f991a4c1-beta15-clean-handoff-venv-stopped/`.
Two preliminary handoff attempts remained fail-closed: system Python lacked
the project dependencies, then an exact owned manual runtime occupied the
guarded ports. The owned runtime was stopped with `make stop`; no unowned
process was signalled.

The candidate is pushed to `main`. Target-host repair and beta15 publication
remain pending because the disposable VPS rejected the previously supplied
password and does not authorize the local SSH key. The claim boundary remains
Linux runtime onboarding only; no PX4, simulation, QGC, target-board, field,
or aircraft claim is made.
