# PXE-0154: Installer Reuse, Onboarding, And Handoff Clarity

Date: 2026-07-29
Status: implementation and local validation complete

Repeated one-line setup now explains why the OpenCV/GStreamer provider can or
cannot be reused. A matching exact source/capability contract skips compilation;
a mismatch names the failed condition, and a completed build is reverified by
the parent initializer before it is reported ready.

The same guided update now offers no-change-default dashboard-login and
managed-service review after the update lock is released. The one-line path
uses concise setup/runtime/final summaries, while direct maintenance commands
keep full diagnostics.

Local gates pass `265` setup/docs contracts, `146` lifecycle/update contracts
with one skip, Phase 0 `73`, schema `39/518`, Bash syntax, warning-level
ShellCheck, and whitespace checks. No build, sudo, service, runtime, firewall,
hardware, PX4, or field action was performed.

