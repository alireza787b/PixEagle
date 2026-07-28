# Phase 5 Checkpoint: Operator Model, Restart, And Media Feedback

Date: 2026-07-28
Issue: PXE-0148
Status: implementation validated; supervised-browser acceptance pending

## Slice

- Preserve registered model artifacts and distinguish upload admission,
  filename collision, active-store contention, provenance, and validation
  failures.
- Replace the retired process Quit route with the existing typed, confirmed,
  audited system-restart action. Manual restart is permitted without pending
  config, but admin scope, runtime policy, idempotency, follower/Offboard
  barriers, and durable audit remain mandatory.
- Make routine tracker/transport video badges less prominent and hide them with
  OSD while preserving errors, target interaction, recording, and fullscreen
  controls.
- Replace the single WebRTC first-frame timer with bounded signaling, offer,
  answer, media, and decoded-frame deadlines that reset only on verified
  progress and close failed transports.

## Validation

- Phase 0 route and parameter reload gate: `73 passed`.
- Focused model, action, route, security, auth, and SITL API regression:
  `403 passed`.
- Streaming lifecycle, stream API, production-remote browser contracts,
  generated API candidates, and infrastructure docs: `100 passed`.
- Dashboard: `58` suites and `389` tests passed.
- Dashboard lint: passed.
- Dashboard production build: passed.
- Generated schema: `39` sections and `518` parameters, current.
- Generated API tool-candidate inventory: current.
- Python compile and `git diff --check`: passed.

## Evidence And Limits

The prior VPS runtime log showed signaling and authorization succeeding, with
the aiortc answer arriving about five seconds after offer handling. The former
eight-second timer began before that work and closed the peer shortly after
candidate exchange. The new phase deadlines address that deterministic client
timeout.

This does not prove public WebRTC media reachability. The target still needs a
working UDP path or configured TURN service, and the updated supervised process
must be retested for both manual restart/reconnect and decoded WebRTC frames.
No PX4, Raspberry Pi, camera/gimbal, field, or aircraft claim is made.

## Files

Primary implementation:

- `src/classes/model_manager.py`
- `src/classes/api_legacy_model_routes.py`
- `src/classes/api_v1_actions.py`
- `src/classes/fastapi_handler.py`
- `dashboard/src/pages/ModelsPage.js`
- `dashboard/src/components/RestartButton.js`
- `dashboard/src/components/VideoStream.js`
- `dashboard/src/components/BoundingBoxDrawer.js`
- `dashboard/src/components/OSDToggle.js`

Contract tests, generated API context, operator docs, changelog, journal, and
issue register were updated in the same slice.

## Next Gate

Publish the exact commit to the supervised lab host. Confirm that an authorized
manual restart reconnects the dashboard and that forced WebRTC either renders
decoded frames or reports the specific failed phase. Keep PXE-0148 open until
that operator evidence is recorded.
