# PXE-0172: Camera Smart selection and restart recovery

Date: 2026-09-19. Branch: `feat/optional-gimbal-control-bench`.
Scope: finish the optional camera selection modes and fix the reproduced
restart failure. Hardware qualification remains pending operator reconnection.

## Result and boundaries

The default-off integration now offers **Classic Tracker** (manual point) and
**Smart Tracker** (camera recognition/fuzzy click). These are selection behaviors
inside the existing external provider, not new local tracker algorithms or YOLO
instances. Normal Classic/Smart users see no new mode or camera controls unless
`GimbalTracker.CONTROL_ENABLED` is true and the active provider supports them.

The operator reported that tracking moved the wrong way in the official camera
app too, and that changing camera-side image rotation corrected it. Read-only
session `20260919T025716Z-rotation-config` returned `ROT02` repeatedly, confirming
the camera setting. No rotation write was sent by that probe. The earlier
wall-switch recording independently showed the target staying briefly inside
its box while moving away from the image center. Together these support the
orientation diagnosis, but corrected tracking retention and AI target selection
have not yet been qualified through PixEagle. Do not automatically force camera
rotation for other installations or change initial click coordinates to hide
this behavior.

The operator is away from the camera. All work after that notice used tests,
source review, file video and an isolated local API; no camera command or flight
command was sent.

## Modular selection implementation

- `src/classes/gimbal_control.py` remains the provider command boundary. The SIP
  implementation advertises `set_mode`; future providers can implement that
  capability or omit it without changing the dashboard or follower.
- Typed action `set_mode` requires `selection_mode: classic|smart`. Other actions
  reject that field. Status reports provider selection intent separately from
  raw camera state. Existing scopes, confirmation, idempotency, audit and
  following interlocks remain in force.
- Smart mode disables the previous session, sends `TRC02` and observes ready.
  Candidate boxes are the camera's native video overlay. A ready-state click
  preserves the detection session and sends the official Qt point format:
  wire size 62×111, descriptor bytes `00 09`. Active/lost retarget first returns
  to ready. No class IDs, confidence semantics or metadata geometry are guessed.
- Classic retains a manual 64-pixel region and descriptor 0. Mode changes to
  Classic cancel the old session. Cancel/movement stop camera tracking; Smart
  can be selected again to prepare detection. Provider recreation resets mode
  intent to Classic. Nothing automatically resumes a target or following.
- Mode buttons follow capabilities and actual returned status. Smart is labeled
  as camera AI. Default local Classic/Smart behavior is unchanged.

Firmware controls fuzzy matching and no-candidate fallback. This slice does not
claim confirmed AI identity, enumerate detections through ODR, implement a local
candidate overlay, or add drag selection. Those are unnecessary for the native
camera-overlay workflow and remain separate possible extensions.

## Restart root causes and correction

The restart API transferred the follower lifecycle lock to its shutdown task.
That task waited for shutdown while still holding the lock; shutdown's PX4
teardown needed the same lock. The observed 10-second timeout was therefore a
reproducible lifecycle deadlock, not evidence of camera connection failure.

`fastapi_handler.py` now marks shutdown, releases the transferred lock and then
awaits teardown. `app_controller.py` rejects queued preview/live follow starts
once shutdown begins. Camera target/mode/movement starts are also blocked during
shutdown, while best-effort Stop remains available. After follower teardown,
shutdown closes the external tracker/provider: enabled controls stop motion and
cancel only a target/session they own; the default telemetry-only provider sends
no camera control commands. Tests exercise both ownership cases.

A second cause was specific to our temporary direct launcher: it had no process
to relaunch exit code 42. Also, Parameters loaded the bench config while Settings
persisted to the normal config. The replacement local launcher,
`reports/gimbal-manual-integration/restartable_bench.py`, supervises exit 42 and
uses the same isolated file for loading, Settings, backups and audit. It checks
command preview, active circuit breaker, disabled MAVLink and loopback binding.
The supported normal shell launcher already supervises exit 42; this change does
not install or modify a system service. Operator edits to `configs/config.yaml`
are preserved.

## Offline verification

- 216 tests covering camera protocol/control, API, generated inventory, config
  reload, restart lifecycle and command preview: passed.
- 183 additional system-about and AppController Offboard/lifecycle regressions:
  passed. **399 backend tests total** in these two checkpoint runs.
- Dashboard: **61 suites / 433 tests passed**, production build passed.
- Schema check: passed, 43 sections / 604 parameters; Python compilation and
  `git diff --check` passed. Existing Starlette deprecation warnings remain.
- Isolated launcher `--check` verified identical load/persistence paths without
  starting runtime subsystems.

An actual process/API restart check used `resources/test4.mp4`, CSRT, disabled
GimbalTracker, command preview, disabled MAVLink and loopback port 5079. It saved
rotation 0→180 using the existing Settings API and invoked the typed restart
action. Backend PID changed 12586→12672; the replacement API was reachable about
5.26 seconds after the action response. Startup records confirmed rotations
[0,180], runtime status showed no pending restart, no shutdown timeout appeared,
and camera wire capture was empty. The user's normal config SHA-256 was unchanged.
The test supervisor and child were stopped afterward.

Commands and evidence:

- `PYTHONPATH=src .venv/bin/pytest -q tests/unit/core_app/test_backend_restart_lifecycle.py tests/unit/core_app/test_command_preview.py tests/unit/core_app/test_api_v1_gimbal_control.py tests/unit/trackers/test_gimbal_control.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_parameters_reload.py tests/unit/trackers/test_gimbal_interface_protocol.py tests/unit/trackers/test_gimbal_interface_status_freshness.py tests/unit/trackers/test_gimbal_provider.py`
- `PYTHONPATH=src .venv/bin/pytest -q tests/unit/core_app/test_api_v1_system_about.py tests/unit/core_app/test_app_controller_offboard_safety.py`
- `cd dashboard && CI=true npm test -- --watchAll=false --runInBand && npm run build`
- `.venv/bin/python reports/gimbal-manual-integration/restartable_bench.py --check`
- `.venv/bin/python reports/gimbal-restart-offline/check_restart.py`

[Evidence and exact scripts](../evidence/2026-09-19-gimbal-smart-restart/README.md)
include source hashes, logs, API results and the file-video configuration.
[Operator instructions](../../../../trackers/02-reference/gimbal-tracker.md)
explain setup, modes, orientation, restart supervision and limitations.
No SITL, HIL, flight, platform-wide or corrected-camera retention claim is made.

## Next hardware session

When the operator returns, use the isolated supervised launcher and keep
following stopped. Do not change the operator's camera rotation blindly.

1. Read camera orientation and inspect native/video display orientation. Confirm
   the same steady object centers correctly in the official app and PixEagle.
2. Classic: select an off-center target, verify it moves toward center and holds,
   select another target, then Cancel. Capture actual object/box and angle motion.
3. Smart: prepare camera detections with a suitable person/vehicle in view, click
   a visible candidate, verify the selected identity, retarget and cancel. Check
   no-candidate behavior without promising that firmware refuses fallback.
4. Exercise roll, zoom and Stop, then save a display setting and use Restart.
   Confirm the backend returns, the saved view loads, no target resumes and
   following remains off. Do not infer a hardware watchdog from software cleanup.

After these bounded checks, prepare the feature PR with the remaining hardware
limits explicit. No PR has been published from this workspace yet.
