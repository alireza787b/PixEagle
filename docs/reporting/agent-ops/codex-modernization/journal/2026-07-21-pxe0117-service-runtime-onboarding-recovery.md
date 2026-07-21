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

Local implementation validation reached `131 passed, 1 skipped` across the
focused ownership, installer UX, PyTorch policy, and setup-lock suites. Full
repository gates, beta15 publication, and disposable-host repair are the next
checkpoint. The claim boundary remains Linux runtime onboarding only; no PX4,
simulation, QGC, target-board, field, or aircraft claim is made.
