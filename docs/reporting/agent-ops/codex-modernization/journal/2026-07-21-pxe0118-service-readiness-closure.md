# PXE-0118 Journal: Beta.15 Service Readiness Closure

**Date:** 2026-07-21 UTC
**Outcome:** real Ubuntu update/start/restart gate passed

## Resume State

PXE-0117 had fixed the original systemd ownership false positive and passed
local/CI handoff gates, but the disposable Ubuntu service had not yet been
repaired. SSH key access became available in this slice.

## Work Completed

- repaired the remote tracked mode mutation without deleting operator data;
- reproduced the no-PX4 MAVSDK readiness mismatch;
- removed pre-discovery gRPC port `50051` from generic startup readiness while
  retaining MAVSDK process supervision;
- stopped service/reboot actions from running inside update reconciliation;
- bounded automatic systemd restarts and made explicit operator recovery reset
  the consumed failure budget;
- removed tracked-source chmod side effects from service installation;
- corrected exact tmux window reporting and optional port `5551` status;
- added focused regression coverage and service documentation;
- fast-forwarded and reconciled the Full AI disposable host, then passed exact
  start/restart, ownership, listener, HTTP, MJPEG, and JSONL log checks.

## Commits

- `3b57abc4` - restart-safe service repair and readiness
- `91ce6efb` - explicit recovery after systemd rate limiting
- `ea725c76` - exact tmux/optional-port status clarity

## Validation

- `53 passed` runtime ownership/service tests
- `271 passed` broader setup/update/config lifecycle tests before status polish
- `72 passed` required Phase 0 API/parameter tests
- `25 passed` infrastructure documentation tests
- schema: `40` sections, `535` parameters
- remote exact run: active, healthy pane contract, `NRestarts=0`, three owned
  loopback listeners, successful dashboard/About/MJPEG probes, zero error-like
  active JSONL entries

## Boundary And Resume Point

This is an Ubuntu service/runtime pass, not PX4, QGC, Raspberry Pi, WebRTC,
field, or aircraft evidence. Wait for final CI, publish beta.15, then execute the
fresh Ubuntu beginner flow and exact-tag Raspberry Pi Core-first acceptance.

## Follow-up CI Hygiene

The final review found one bounded repository-maintenance issue before
publication: GitHub workflows still used mutable Node 20-era action tags. That
was corrected in PXE-0119 with immutable action pins, monthly Dependabot
tracking, a corrected gimbal CI example, and a regression guard that enforces
the durable SHA/comment contract without freezing future reviewed updates. The post-pin
CI run, rather than the pre-pin runtime-candidate run, is now the publication
gate.
