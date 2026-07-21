# PXE-0121 Journal: Setup Lock Observability

**Date:** 2026-07-21 UTC

## Finding

The supervisor preserved setup ownership correctly after an SSH reset, but its
second-installer failure was not actionable. The OpenCV percentage display was
also quiet during long compilation intervals.

## Result

Added verified active-operation diagnostics, `make setup-status`, UTC lease
start metadata, and a 30-second OpenCV heartbeat. Concurrent setup remains
prohibited and no stale-lock deletion heuristic was introduced.

## Evidence

Focused lock, OpenCV setup, and initializer UX tests passed: 93 passed and one
root-only test skipped. A maintainer VPS rerun remains the external gate.
