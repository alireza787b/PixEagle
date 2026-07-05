# Phase 4 OSD And Video Overlay Polish Checkpoint

- Date: 2026-07-05
- Phase: 4
- Issue: PXE-0082
- Slice: OSD/status display and stream overlay clarity
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PXE-0082 closes the code/test gate for the demo feedback around video overlay
clarity:

- the tracker overlay badge now says `Tracker: Classic` or `Tracker: AI`;
- the stream protocol badge now always renders explicit text such as
  `Video: WebSocket` plus `HTTP demo`;
- OSD preset/color displays no longer accept empty backend strings as UI state;
- non-empty backend values that are not in the current catalog are surfaced as
  missing instead of silently becoming selectable catalog entries.

## Changed Files

- `dashboard/src/components/BoundingBoxDrawer.js`
- `dashboard/src/components/BoundingBoxDrawer.test.js`
- `dashboard/src/components/OSDToggle.js`
- `dashboard/src/components/OSDToggle.test.js`
- `dashboard/src/components/VideoStream.js`
- `dashboard/src/components/VideoStream.test.js`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `/home/alireza/PIXEAGLE_OSD_VIDEO_OVERLAY_POLISH_2026-07-05.md`

## Behavior

- Classic/smart tracking mode is visible as operator language, not internal
  shorthand.
- Auto streaming on public HTTP/IP resolves to WebSocket using the same page
  context as the WebRTC safety guard.
- The top-right protocol badge is a controlled overlay with explicit typography
  and responsive width instead of a generic chip that can appear blank.
- OSD preset and color catalogs are trimmed and deduplicated.
- Blank backend preset/color values fall back to current/default safe display
  values.
- Non-empty unknown OSD preset/color values show as missing in the status line.
- The OSD color-mode catalog fetch is best-effort so a partial legacy backend
  does not hide the rest of the OSD status panel.

## Evidence Boundary

This slice changes dashboard display behavior only. It does not add typed
`/api/v1/osd/*`, change OSD renderer internals, restart the public demo,
rotate browser credentials, claim WebRTC receipt, claim QGC playback, claim
PX4/SITL/HIL/field behavior, or claim real-aircraft success.

Live public screenshot evidence was not captured because only the hashed demo
browser-user file is present on disk. The active public demo password was not
rotated. Manual public retest remains with the active tester/password session,
or with the later safe demo cleanup/rotation slice.

## Validation

Passed:

```bash
CI=true npm test -- --runTestsByPath src/components/OSDToggle.test.js src/components/VideoStream.test.js src/components/BoundingBoxDrawer.test.js --watchAll=false

CI=true npm run build

PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py

bash scripts/check_schema.sh

git diff --check
```

Results:

- focused dashboard component tests: 20 passed;
- production dashboard build: passed;
- API route inventory plus parameter reload tests: 51 passed;
- schema check: passed, schema up to date;
- whitespace diff check: passed.

## Remaining Slices

- PXE-0079: final clean setup walkthrough evidence.
- PXE-0083: log evidence bundle UX/import design.
- PXE-0084: typed About/System/update-status.
- PXE-0085: SIH Dev/Training validation surface.
- PXE-0086: safe demo cleanup/rotation and safe update workflow.
