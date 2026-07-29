# Phase 5 Installer Reuse, Onboarding, And Handoff Clarity

Date: 2026-07-29
Issue: PXE-0154
Status: implementation and local validation complete

## Scope

Close three issues found during the repeated Ubuntu one-line walkthrough:

- make an expensive OpenCV/GStreamer rebuild explainable and independently
  verifiable;
- let the operator explicitly preserve or replace the dashboard login and
  review managed-service policy after an update;
- remove duplicate beginner-bootstrap summaries without weakening direct
  engineering diagnostics.

## Decisions

- The OpenCV builder remains the single authority for its exact version and
  source revisions. Reuse requires a source provider in the selected venv plus
  GStreamer, FFmpeg, CSRT, and KCF.
- A matching provider is reused without download or compilation. A mismatch
  prints the failed provider/version/capability, and a successful build must
  pass the same probe again before init reports ready.
- `PIXEAGLE_REBUILD_COMPONENTS=opencv` remains the only explicit force-rebuild
  path; no second compatibility table or stale install marker was added.
- Repeated one-line setup asks whether to keep the existing dashboard login.
  Enter preserves it; `n` enters the canonical rotation flow, where Enter keeps
  `admin/admin`.
- Managed-service review runs only after the update transaction releases its
  source/environment locks. The update default preserves existing policy and
  the onboarding path never starts a runtime or reboots the host.
- Compact init/launcher/final output is enabled only by the one-line bootstrap.
  Direct `make init` and `make run` retain their detailed diagnostics.

## Validation

```text
installer/setup/documentation contracts
265 passed

runtime ownership/update/setup-lock/config/network contracts
146 passed / 1 skipped

Phase 0 API inventory and parameter reload
73 passed

schema
39 sections / 518 parameters, current

bash -n
passed

ShellCheck --severity=warning
passed

git diff --check
passed
```

The local provider probe reported a managed OpenCV wheel with GStreamer
unavailable, which correctly explains why this checkout would not satisfy the
source/GStreamer reuse gate. No source build was launched during validation.

## Boundaries

- No runtime was stopped or started, no service or boot policy was changed, no
  sudo action ran, and no firewall rule changed in this slice.
- Local contract tests do not prove a successful repeated one-line update on
  the operator's Ubuntu host or any Raspberry Pi/Jetson target.
- No camera, model, MAVLink, PX4, simulation, HIL, field, or aircraft behavior
  is claimed.

