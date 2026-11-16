# Stock PX4: gimbal following on MC and VTOL

Use standard PX4 firmware for the ordinary integration. The aircraft model is
not a runtime allowlist. Detect aircraft type, settled phase, telemetry and
supported control interfaces; a configuration label cannot create a capability.

**Current status:** ordinary MC uses the existing MAVSDK path. Unmodified PX4
SIH passes the production MC Position and vertical Gimbal Vector component runs.
A shared-ray MAVLink attitude/thrust FW component also passes moving-target
normal, descent and climb checks. It is not connected to application Start,
session controls or recovery yet. The VTOL application still requires the
experimental native owner; its replacement remains closed pending qualification.
These component results are not flight clearance or end-to-end acceptance.

## One mount across both phases

Keep `GimbalTracker.MOUNT_TYPE` at the actual installation, including `VERTICAL`
on a vertically mounted tailsitter. Do not switch it to `HORIZONTAL` after
transition. Provider angles first become a physical aircraft-body ray; aircraft
attitude then rotates that ray into the navigation frame. The FW strategy uses
its declared navigation frame without applying the tailsitter rotation twice.

The current Topotek vertical preset uses negative raw roll for azimuth and raw
pitch minus 90 degrees for depression. This is a provider convention, not a
universal gimbal rule. Verify signs, body/earth stabilization reference and
measurement timing on the installation. See [camera mounting](../../trackers/06-integration/camera-mounting.md).

## Control and communication

| Stage | Intended stock interface | Qualification required |
| --- | --- | --- |
| MC or settled VTOL hover | Existing MAVLink/MAVSDK MC command publisher | Fresh phase, physical attitude, vector/frame conversion, speed editing, Stop and takeover |
| Transition | Pilot/PX4 owns transition; following ends | No pursuit, no delayed command that replaces the pilot's mode, no automatic restart |
| Settled FW | MAVLink attitude/thrust projection under qualification | Speed/path feedback, altitude response, link-loss behavior, Stop and takeover |

Keep the existing UART/MAVLink link. MAVLink2REST provides observations and
MAVSDK publishes control; no extra USB cable or DDS runtime is required for the
current stock-MAVLink work. Changing the MAVLink stream mode does not create a
new control interface. High-rate Onboard defaults may overload a 57600-baud link;
measure its budget and request the relevant message intervals instead.

FW cannot consume MC velocity-only setpoints. The stock-MAVLink component keeps
the shared world target ray and requested speed, then produces coordinated bank,
pitch and normalized thrust through supported attitude Offboard. PX4 retains
attitude/rate control and allocation. This path does **not** retain native TECS
energy/underspeed control: its companion speed/path feedback must be qualified.
Normal requests respect resolved PX4 speed, pitch and climb/sink settings.
The isolated expert fixture removes upper-speed and pitch/sink soft limits,
retaining the shared altitude floor, actuator/bank bounds and climb-speed priority.
Neither requested speed nor pitch guarantees an achievable aircraft response.

DDS remains a deferred alternative for native PX4 course/airspeed/vertical-path
control. It can use a configured serial or network transport, but cannot silently
share a UART currently assigned to MAVLink. Its benefit is access to the native
controller interface, not improved video quality.

Current PX4 main also documents MAVLink Guided Course commands for course,
altitude and EAS. Availability depends on the installed firmware. It holds its
course until another command/mode is received; it must not be adopted as a
streaming follower merely because commands are accepted. Companion failure,
command expiry and recovery must pass first. MAVLink position/path Offboard is
another distinct contract; velocity magnitude is not its FW airspeed command.
Do not run competing command publishers or silently substitute transports.
Fresh `HEARTBEAT`/`EXTENDED_SYS_STATE` observation is now implemented in the
existing telemetry identity owner. Cached or reordered phase packets cannot
renew phase freshness. Phase observation alone grants no following authority.

## Configuration

Use the existing keys, through Dashboard Settings while following is inactive:

| Setting | Meaning |
| --- | --- |
| `Tracking.DEFAULT_TRACKING_ALGORITHM: Gimbal` | External angle tracker, rather than a local image tracker |
| `GimbalTracker.ENABLED` / `CONTROL_ENABLED` | Provider reception and operator camera control |
| `GimbalTracker.MOUNT_TYPE` | One physical installation for both phases |
| `Follower.FOLLOWER_MODE: gm_velocity_vector` | Shared angle-guidance profile; phase-specific command strategies |
| `Follower.AIRFRAME_LAYOUT: AUTO` | Verify the observed aircraft without forcing MC/FW state |
| `Follower.FollowerOverrides.GM_VELOCITY_VECTOR.ENABLE_ALTITUDE_CONTROL` | Explicit target-directed climb/descent choice |
| `GM_VELOCITY_VECTOR.REQUESTED_SPEED` | MC startup request; zero is allowed, never reused as a FW airspeed |
| `Safety.GlobalLimits` | Saved MC speed/rate and relative-altitude envelope |
| `FixedWingGuidance.UPPER_SPEED_POLICY: px4_configured_max` | Normal native FW envelope |
| `FixedWingGuidance.MIN_DIVE_THROTTLE: null` | Native throttle behavior |

Read FW minimum/trim/maximum and climb/sink/attitude limits from PX4 through the
existing parameter owner where supported. Keep provenance and explicit missing
values. The component prefers fresh selected airspeed, then a qualified estimate
if supplied; otherwise it labels NED velocity magnitude `ground_speed_proxy`.
The proxy supports degraded feedback, but cannot establish actual stall margin.
VFR_HUD reports selected calibrated airspeed; a cached read is not a new packet,
and an absent sensor is not evidence of a wind-based estimate.

`no_upper_speed_bound` is tested only in the isolated MAVLink component. It is
not advertised or enabled for stock application following yet. A private config
cannot bypass that admission gate. The existing native-policy semantics remain
separate until the qualified MAVLink transport is integrated; changing this flag
alone must not silently enable a steep-dive envelope in an existing installation.

The bench aircraft's 20 m/s maximum and ±30-degree pitch limits are saved PX4
values, not universal Offboard limits. Native FW guidance still resolves its
airspeed request against PX4's performance envelope. Direct MAVLink attitude
and thrust Offboard is a different supported contract: an attitude request can
exceed the TECS pitch limits, but it does not request airspeed or retain TECS
energy/underspeed control. Testing that interface is not qualification of a
gimbal follower, its altitude protection, or an unrestricted-speed policy.
Keep requested attitude, observed attitude, requested airspeed and observed
airspeed separate in evidence; an accepted request proves none of the others.

## Reproduce the software checkpoint

Build an exact unmodified baseline without starting it:

```bash
PYTHONPATH=src python tools/build_native_guidance.py --target sih \
  --firmware-policy stock --px4-source /path/to/pinned/PX4-Autopilot \
  --output-dir reports/native-guidance/stock-build
```

Then explicitly start the network-isolated component test, using a new directory
for each run:

```bash
PYTHONPATH=src python tools/run_mavlink_fw_vector_sih.py --execute \
  --simulation-build-manifest reports/native-guidance/stock-build/sih-build-manifest.json \
  --output reports/sitl/stock-fw-normal
```

`--unconstrained` selects only a disposable expert fixture. Target offsets and
takeoff altitude can be varied with `--target-forward-m`, `--target-down-m`
(positive down) and `--takeoff-altitude-m`. These are simulator test inputs,
not new operator settings. The test records actual PX4 pose, independent moving
target truth, submitted attitude/thrust, requested/observed speed, original source
clocks, configuration, source checksums and ULogs. It does not exercise the App,
HTTP actions, UI, target-loss recovery or physical camera. Existing evidence is
never overwritten. Post-Stop speed/altitude are separate from following evidence.
The safe MC qualification scenarios start at 40 m, above the shared public
30 m floor; ground-view targets remain on the ground.

Public factory defaults remain MC Position, VIDEO_FILE/CSRT, optional altitude
guidance off, circuit breaker on and the shared 30 m relative-altitude floor.
Private test overlays do not change those defaults.

## Operator sequence after stock qualification

1. Bench: retain the circuit breaker; verify sign-in, fresh telemetry/video,
   point/region selection, gimbal controls and physical angle signs.
2. In the separately approved MC test, settle above the configured floor and
   warning band. Start tracking, then following. Increase the MC request from
   zero in bounded steps; verify Stop and fresh restart.
3. Stop following and confirm its result **before** the pilot commands transition.
4. Let PX4 settle in FW. Confirm the target and make a new explicit Start.
   Initialize the FW request from qualified engagement speed or the declared PX4
   reference; never carry over MC zero. Show request and observed speed separately.
5. Retain feasible FW motion during bounded target loss; expiry hands off to
   native FW Hold/loiter. Retargeting cannot reset the loss budget. Later target
   detection cannot restart following automatically.

Until the stock simulation and installation gates pass, perform step 1 only.
Keep the existing VTOL admission closed rather than relabelling the aircraft as MC.

Sources: [MAVLink state](https://mavlink.io/en/messages/common.html#EXTENDED_SYS_STATE),
[PX4 Offboard](https://docs.px4.io/main/en/flight_modes/offboard),
[PX4 native FW interface](https://docs.px4.io/main/en/ros2/px4_ros2_control_interface),
[Guided Course](https://docs.px4.io/main/en/flight_modes_fw/guided_course),
[DDS ports](https://docs.px4.io/main/en/middleware/uxrce_dds).
