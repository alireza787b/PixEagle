# QGC slice 4b.2 — shared camera owner and mock controls

User accepted the previous Smart checkpoint and authorized continuing to the
camera bench gate. This checkpoint changes software ownership and mock control
coverage; no physical camera or aircraft was connected or commanded.

## Delivered

- AppController owns one `CameraRuntime`; GimbalTracker borrows the provider.
  Local Classic/Smart can retain independent opt-in manual camera controls.
- Existing typed camera routes gain captured provider/source/engine guards,
  provider mode catalog, independent target engine and movement status.
- Native movement uses credential/client-scoped idempotency, confirmation,
  durable audit, exclusive busy/hold admission, and the follower barrier.
  Stop invalidates late starts and cannot redirect to a replacement camera.
- Context is checked after the protocol handshake immediately before movement;
  the source transaction covers final transmission. Existing finite pulses,
  status confirmation, freshness and independent Stop behavior remain.
- Dashboard preserves local targeting when only movement controls are enabled,
  sends captured camera contexts, and stops holds on source/provider changes.
- `tools/native_integration_fixture.py --mock-camera` exercises production auth,
  camera status, action, guard and audit paths with no hardware sockets.
- Native camera contract, provider guide, QGC camera scenarios and generated
  API candidate provenance were updated. API candidates remain non-callable.

No configuration keys were renamed. `GimbalTracker` remains the single camera
provider configuration. Default `CONTROL_ENABLED: false` starts no camera for
local tracking. Provider/transport settings require a backend restart. Existing
passive Gimbal configurations remain selected through dashboard/saved config.

## Evidence

- Expanded backend gate: **541 passed** in 14.88 seconds, including native camera,
  native targets, camera API/protocol/provider/tracker/freshness, route inventory,
  candidate generation, config reload, restart and Offboard safety tests.
- Dashboard: **62 suites / 472 tests passed**; production build passed.
- Schema check: **606 parameters**, up to date.
- Final focused guard/source-transaction/passive-status tests and provenance check:
  **126 passed** in 9.56 seconds. Mock fixture plus streaming suite: **37 passed**.
  Python syntax and whitespace checks pass.

Local evidence:

- `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b-2026-09-30/backend-camera-4b2-tests.log`
- `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b-2026-09-30/backend-camera-4b2-final-tests.log`

### Joystick review follow-up

Independent AI code review found that `SipGimbalControl.execute()` ignored the
Boolean result of its final pulse Stop. A successful movement transmission could
therefore return success even when all final Stop transmissions failed, allowing
a serial hold client to continue. Pan, tilt, roll and zoom now return a failed
action in that case. Explicit Stop remains retryable; no protocol, pulse bounds,
configuration defaults or camera ownership rules changed.

Regression transport fakes accept movement and reject Stop, verify the failed
result for all four operations, then restore transport and verify explicit Stop
retry. The focused camera, native route and required backend gates passed:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/unit/trackers/test_gimbal_control.py \
  tests/unit/core_app/test_camera_runtime.py \
  tests/unit/core_app/test_api_v1_gimbal_control.py \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_api_tool_candidates.py
PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check
bash scripts/check_schema.sh
.venv/bin/python -m py_compile src/classes/gimbal_control.py \
  tests/unit/trackers/test_gimbal_control.py
```

Result: **264 passed**, two dependency deprecation warnings, 17.53 seconds.
Generated candidate inventory is current; schema has **606 parameters** and is
up to date. Syntax and scoped whitespace checks pass. Test log:
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b-2026-09-30/backend-camera-stop-review-tests.log`.

Raw review observations (AI review, not physical operator evidence):

- Pulse final Stop failure was discarded; corrected above.
- QGC Center captured a hold gesture but did not clear it on completion, so the
  next joystick gesture inherited the old hold deadline. Reported to the QGC
  implementation owner for a separate one-shot completion fix and regression.
- Acknowledged UDP transmission still cannot prove the camera stopped moving.
  Bench qualification remains required for motor direction and network loss.

## Boundaries and next gate

The mock fixture advertises movement-only capabilities. Camera select/mode,
retained frame and protocol handshake tests use separate no-network fixtures.
Physical motor directions, camera Classic/Smart retention, camera mount frame,
latency, network-loss behavior and follower geometry remain unqualified.
Camera firmware Smart is independent of PixEagle local AI models.

Slice 4b.3 requests the operator's actual Ethernet camera only after the complete
QGC/software gate. Record exact model, firmware, topology, RTSP shape without
credentials, mount orientation and bench travel limits. No flight qualification
or automatic restoration of following is implied.
