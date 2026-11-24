# AppController

[`AppController`](../../../src/classes/app_controller.py) joins capture, tracking,
following, telemetry and the authenticated API. It owns lifecycle decisions;
trackers produce observations and followers produce command intent. Neither
starts a second aircraft publisher or implements its own recovery supervisor.

## Lifecycle and ownership

Construction initializes synchronous components before starting degradable
workers. Optional video, detector or model failures remain visible in startup
status without taking away configuration and recovery access. Camera/provider
ownership stays in `CameraRuntime`; source and tracking generations invalidate
work created for an older target or installation.

Aircraft mutations run on the existing flight-owner event loop. API and camera
callbacks dispatch to that owner; they cannot replace it with their own loop.
The follower lock serializes explicit startup and teardown. Source/guidance
generations protect asynchronous target and phase changes.

| Entry point | Responsibility |
| --- | --- |
| `observe_native_connection()` | Connect/read aircraft identity without starting a follower or acquiring flight authority |
| `start_tracking()` / `stop_tracking()` | Tracking lifecycle and target ownership |
| `connect_px4()` | Guarded following startup, including connection/readiness, follower creation and one command owner |
| `disconnect_px4()` | Join publication, release the captured owner and retain the observed handoff result |
| `shutdown()` | Join owned operations and workers without replaying earlier actions |
| `get_tracker_output()` | Current typed tracker observation; not flight authority |

Do not confuse observational discovery with `connect_px4()`: the latter starts
following. External clients use the authenticated
[native following actions](../../apis/native-following-operations.md), rather
than calling controller internals or driving MAVSDK directly.

## Following path

The controller normalizes `TrackerOutput` through its command-freshness contract.
Confirmed usable evidence can reach follower math. The shared
`TargetContinuitySupervisor` then decides whether the resulting nominal intent
is authorized, recovering or requires handoff. The existing `OffboardCommander`
publishes the current authorized contract; command submission alone does not
prove aircraft response.

External trackers bypass video-frame freshness only when their capabilities
explicitly declare `requires_video: false`. Their actual target/angle receipt
and provider-session evidence must still be fresh. Classic/Smart image trackers
retain frame provenance and geometry. A new video frame cannot refresh old
camera angles or aircraft telemetry.

The registered Vector follower selects its command strategy from observed
MC/FW/VTOL state. Pure MC retains MAVSDK Offboard. FW and VTOL use one qualified
native owner; phase changes invalidate old command generations while preserving
the session's phase-specific controls and monotonic recovery budget. MAVLink
body velocity is not a FW command contract. See the
[native adapter](../../../native/README.md) and
[FW guidance policy](../../followers/04-configuration/fixed-wing-guidance-policy.md).

Stop joins the publisher before handoff. Pilot takeover or changed aircraft
identity prevents cleanup from issuing a new mode command to an unowned or
replacement aircraft. Failed cleanup remains visible and blocks another Start.
A confirmed Hold result is retained separately from a request or local teardown.

## Configuration and diagnostics

[`configs/config_default.yaml`](../../../configs/config_default.yaml) and its
generated schema are the canonical settings. Use the existing configuration
service and Config Sync; do not add controller-local copies of defaults.
Public defaults keep VIDEO_FILE, PixEagle CSRT, constant-position following,
altitude guidance off, altitude safeguards on and the circuit breaker on.

Read readiness, effective session controls, publication fields and the retained
handoff through the existing API snapshots. Aircraft association requires
matching observed identities and fresh telemetry; a configured system ID,
server address or airframe label cannot supply those observations. See
[connection and aircraft association](../../apis/native-integration-context.md).

## Simulation injection

The existing validation hooks exercise the same control path:

- `inject_tracker_output_for_validation()` accepts typed tracker observations
  only during active following, then applies normal freshness and dispatch.
- `inject_video_stall_for_validation()` reuses normal unavailable-frame handling.
- `inject_commander_publish_failure_for_validation()` exercises publisher-failure
  teardown without inventing successful publications.
- `inject_mavsdk_disconnect_for_validation()` and
  `inject_mavlink2rest_timeout_for_validation()` affect the named local client
  boundary; they do not stop PX4, a router, camera or network interface.

Runtime API injection is disabled unless `PIXEAGLE_ENABLE_SITL_INJECTIONS=1`.
Injected observations/faults must be labelled in evidence. Aircraft movement
truth comes from actual PX4 pose, never from integrating command intent. Use the
[SIH qualification workflow](../../followers/05-development/sih-follower-qualification.md)
for retained traces and read-only interactive reports.

## Related components

- [FlowController](flow-controller.md) owns the processing lifecycle.
- [FastAPIHandler](fastapi-handler.md) exposes the authenticated contracts.
- [VideoHandler](../../video/01-architecture/video-handler.md) owns capture.
- [Native following](../../apis/native-following-operations.md) defines client actions.
