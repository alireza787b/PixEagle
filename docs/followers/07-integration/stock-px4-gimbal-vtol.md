# Stock PX4: gimbal following on MC and VTOL

Use standard PX4 firmware for the ordinary integration. The aircraft model is
not a runtime allowlist. Detect aircraft type, settled phase, telemetry and
supported control interfaces; a configuration label cannot create a capability.

**Current status:** ordinary MC uses the existing MAVSDK path. The current
VTOL application path still requires the experimental native owner; stock
VTOL hover and stock FW transport are not yet implemented/qualified replacements.
This guide defines the next acceptance workflow, not flight clearance. Existing
patched-simulator passes do not qualify unmodified firmware.

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
| Settled FW | A verified stock FW interface | Native airspeed/energy control, vertical path, link-loss behavior, Stop and takeover |

FW cannot consume MC velocity-only setpoints. Stock ROS 2 lateral/longitudinal
control is one option without private PX4 messages, but needs a functioning DDS
communication path. MAVLink2REST does not provide that path, and an existing
MAVLink UART must not be reassigned implicitly. Retain the working MAVLink link;
a supported spare serial/USB or network path can carry DDS after setup review.
The complete course/airspeed/vertical-path stock interface is the first candidate
for FW qualification, rather than a second companion energy controller.

Current PX4 main also documents MAVLink Guided Course commands for course,
altitude and EAS. Availability depends on the installed firmware. It holds its
course until another command/mode is received; it must not be adopted as a
streaming follower merely because commands are accepted. Companion failure,
command expiry and recovery must pass first. MAVLink position/path Offboard is
another distinct contract; velocity magnitude is not its FW airspeed command.
Do not add parallel guidance controllers or silently substitute these transports.

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
values; do not invent measured airspeed or treat groundspeed as stall margin.
An operator fallback may only use a declared, validated configuration contract;
there is no new transport/airspeed fallback setting to enter for this checkpoint.

`no_upper_speed_bound` remains an unsupported experiment on this stock path.
A private config cannot grant unrestricted speed, pitch or dive angle. Preserve
experimental requests separately rather than presenting them as effective.
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
