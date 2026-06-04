# PX4/SITL Validation Strategy Scout

Date: 2026-04-30  
Status: planning scout; no runtime SITL implementation in this slice

## Scope

This scout answers the current PX4-in-loop testing question and reconciles it
with the approved modernization plan. It also records the gimbal-provider
implication from the user's note: the existing Topotek board support should
become one provider instance, not the whole gimbal architecture.

## Sources Consulted

Local:

- PixEagle test suite, fixtures, drone-interface docs, CI, and Makefile.
- `/home/alireza/mavsdk_drone_show` SITL validation platform and plan files.
- `/home/alireza/mavlink-anywhere` current routing defaults and headless CLI.
- Read-only specialist audits for PX4/SITL workflow and tracker/follower/gimbal
  test coverage.

External:

- PX4 prebuilt SITL package and container docs:
  `https://docs.px4.io/main/en/simulation/px4_sitl_prebuilt_packages`
- PX4 MAVSDK integration testing docs:
  `https://docs.px4.io/main/en/test_and_ci/integration_testing_mavsdk`
- PX4 Offboard mode docs:
  `https://docs.px4.io/main/en/flight_modes/offboard`
- MAVSDK Offboard guide:
  `https://mavsdk.mavlink.io/main/en/cpp/guide/offboard.html`
- MAVLink Gimbal Protocol v2:
  `https://mavlink.io/en/services/gimbal_v2.html`
- Topotek SIP-series protocol:
  `https://www.topotek.cn/download/protocol/TopotekSIPseriesProtocol20221010.pdf`
- User-suggested unofficial PX4/Gazebo image:
  `https://github.com/JonasVautherin/px4-gazebo-headless`
  and `https://hub.docker.com/r/jonasvautherin/px4-gazebo-headless`

## Current PixEagle Reality

Working foundations:

- Tracker logic is unit-testable without PX4 using synthetic frames, mock
  detectors, and mock trackers.
- Follower math is unit-testable without PX4, including `gm_velocity_vector`,
  `mc_velocity_position`, and NaN/Inf guard coverage.
- `MockMAVSDKSystem`, `MockPX4Controller`, `MockDroneInterface`, and
  MAVLink2REST response fixtures provide a useful base for deterministic tests.
- Current MavlinkAnywhere-aligned Linux routing is coherent:
  MAVSDK `127.0.0.1:14540`, MAVLink2REST input `127.0.0.1:14569`, QGC
  `14550/udp`, TCP `5760`, local MAVLink `127.0.0.1:12550`.

Gaps:

- No checked-in PX4 SITL runner, Docker Compose, Make target, or CI/nightly job.
- No scenario plan library for target loss, video stall, stale tracker output,
  Offboard loss, MAVSDK disconnect, MAVLink2REST timeout, or operator abort.
- No artifact contract for commands, configs, PX4 params, logs, MAVLink route
  maps, ULog/tlog outputs, video snippets, screenshots, or JUnit/JSON results.
- Existing follower/tracker tests do not launch PX4, observe Offboard mode
  acceptance, verify vehicle motion, or prove tracker-driven setpoints against
  SITL telemetry.
- Offboard heartbeat is still coupled to frame/follower execution, so live PX4
  testing would currently reveal the same architectural risk already tracked as
  PXE-0007 and PXE-0013.
- Windows/X-Plane docs and Windows MAVLink2REST defaults diverge from the
  current Linux source-of-truth routing.

## Best Practice Decision

PixEagle should not rely on one giant full visual simulation as the everyday
test. The reliable path is a validation ladder:

1. **L0 unit/contract tests** run on every commit. They cover follower math,
   tracker contracts, config/schema, typed APIs, command validation, and gimbal
   provider conformance without PX4.
2. **L1 mock integration tests** run on every commit. They cover
   `TrackerOutput -> Follower -> CommandIntent -> FlightControlService` with
   canonical telemetry and MAVSDK/MAVLink2REST fakes.
3. **L2 PX4 headless SITL follower tests** run locally and on dedicated
   validation hosts. They launch PX4, route MAVLink through MavlinkAnywhere,
   feed synthetic targets, and verify Offboard entry, heartbeat continuity,
   setpoints, abort paths, stale target behavior, and disconnect handling.
4. **L3 tracker-in-loop tests** run synthetic or recorded video/gimbal fixtures
   through detector/tracker code and into follower/control contracts. They stay
   deterministic and do not require a photorealistic sim.
5. **L4 full visual SITL** uses X-Plane, Gazebo camera, Unity, or equivalent
   scene/video streams for nightly, release, or manual acceptance. It must
   produce evidence artifacts.
6. **L5 HIL/field validation** needs explicit operator approval and cannot be
   claimed from SITL alone.

## PX4-In-Loop Recommendation

For quick Linux development, the first production-grade live test should be
follower-only PX4 SITL:

```text
PX4 headless SITL
  -> UDP MAVLink 14550/14540
  -> MavlinkAnywhere fanout
  -> MAVSDK 127.0.0.1:14540
  -> MAVLink2REST input 127.0.0.1:14569 / HTTP 127.0.0.1:8088
  -> PixEagle follower/control path fed by synthetic TrackerOutput
```

Use official PX4 images or internally pinned images as the default. PX4 now
documents official `px4io/px4-sitl:<tag>` and `px4io/px4-sitl-gazebo:<tag>`
container images, with UDP ports for QGC and MAVSDK and `HEADLESS=1` for Gazebo
headless mode. Those are the correct base for repeatable development and CI.

The `jonasvautherin/px4-gazebo-headless` image is feasible as an optional
compatibility/reference path. It exposes QGC/MAVSDK ports and can expose an RTSP
camera stream for some vehicles. It should not be PixEagle's primary validation
contract because it is unofficial and its behavior is controlled outside the
PixEagle/PX4 release process. If used, pin exact tags and image digests and
capture them in artifacts.

## Can We Test Followers?

Yes. Follower PX4 SITL is the best first live test because it is deterministic
and directly exercises PixEagle's flight-control risk:

- Feed synthetic target states or gimbal angles into followers.
- Assert generated command intents before MAVSDK dispatch.
- Observe PX4 mode/arming/offboard state and local-position response.
- Verify independent Offboard heartbeat through video stall and target loss.
- Verify operator abort, land/hold/RTL behavior, and disconnect failsafes.

This should be introduced as soon as the dedicated Offboard commander lands, not
at the end of the project.

## Can We Test Trackers?

Yes, but in layers:

- Tracker-only tests should use deterministic synthetic frames, recorded clips,
  and gimbal provider fixtures. This is fast and should run often.
- Tracker-to-follower contract tests should replay tracker traces into followers
  without PX4.
- Full tracker+follower+PX4 tests are feasible but heavier. They should be
  smoke/nightly/release jobs until they are proven stable.
- X-Plane remains valuable for high-fidelity camera and flight dynamics if the
  team wants to maintain it, but it should become a documented evidence workflow
  rather than a vague claim.

## Gimbal Provider Decision

The current board support is best named `topotek_sip_udp` based on the Topotek
SIP-series protocol and the current frame identifiers used in code (`GAC`,
`GIC`, `TRC`, `OFT`). It should become one provider:

```text
GimbalInputProvider
  - SipUdpGimbalProvider        # current Topotek SIP-series UDP support
  - MavlinkGimbalProvider       # MAVLink Gimbal Protocol v2 / MAVSDK path
  - SiyiGimbalProvider          # future vendor adapter
  - GremsyGimbalProvider        # future vendor adapter
  - ViewproGimbalProvider       # future vendor adapter
  - SimulatedGimbalProvider     # deterministic tests and SITL
```

`GimbalTracker` should consume only normalized provider output: yaw/pitch/roll,
coordinate frame, tracking state, timestamp/freshness, health, and diagnostics.
Followers should continue to consume `TrackerOutput(GIMBAL_ANGLES, ...)` and
must not know which gimbal protocol produced it.

Provider conformance tests should cover:

- angle ranges and units
- yaw frame semantics
- coordinate transforms
- state transitions
- stale-data fail-closed behavior
- health/diagnostic reporting
- target-lost behavior before follower command generation

## Planned Work Items Added

- PXE-0016 expanded: gimbal provider abstraction requires conformance tests and
  stale-data fail-closed behavior.
- PXE-0018 added: executable PX4-in-loop validation ladder and artifacted SITL
  harness.
- PXE-0019 added: deterministic tracker-in-loop validation fixtures and evidence.
- PXE-0020 added: Windows/X-Plane SITL and Windows MAVLink2REST cleanup.

## Proposed Implementation Slices

1. **Validation contract slice**
   - Add pytest markers: `sitl`, `px4`, `e2e`, `hardware`.
   - Define `reports/sitl/<timestamp>/manifest.json` artifact schema.
   - Add scenario plan schema under `tools/sitl_plans/`.
   - Document local, dedicated-host, and manual validation modes.

2. **Offboard commander prerequisite**
   - Finish PXE-0007/PXE-0013 before claiming live SITL correctness.
   - Add mock tests proving heartbeat continues during frame/video stalls.

3. **Follower-only SITL smoke**
   - Add a runner that launches PX4 headless, MavlinkAnywhere, MAVLink2REST,
     and PixEagle health probes.
   - Feed synthetic target states to followers.
   - Assert Offboard state, command cadence, abort, and stale-target behavior.

4. **Tracker fixture suite**
   - Add synthetic video scenes and recorded fixtures.
   - Store deterministic tracker traces and follower-command expectations.

5. **Full visual SITL acceptance**
   - Decide whether X-Plane remains the primary high-fidelity path.
   - If yes, rewrite the workflow with current ports, scripts, evidence, and
     exact simulator/PX4/PixEagle versions.
   - If no, move X-Plane docs out of active runtime guidance and use Gazebo or
     another maintained camera-sim path.

6. **Gimbal provider extraction**
   - Add `GimbalInputProvider` and migrate current Topotek SIP support behind
     `SipUdpGimbalProvider`.
   - Add `SimulatedGimbalProvider` for tests.
   - Add MAVLink Gimbal v2 provider after the interface is stable.

## Immediate Answer To The User Question

Best quick Linux dev practice is **not** to run the full X-Plane visual loop for
every change. Use mock/unit tests for fast feedback, then a follower-only
headless PX4 SITL smoke with synthetic target input, then tracker-in-loop video
fixtures, and only then full visual SITL for nightly/release/manual evidence.

The headless PX4 Docker approach is feasible. Prefer official PX4 images or a
pinned internal image. Use MavlinkAnywhere to fan out PX4 MAVLink to MAVSDK and
MAVLink2REST so PixEagle exercises the same integration path it uses on Linux.
The unofficial `jonasvautherin/px4-gazebo-headless` image is useful to evaluate
because it includes MAVSDK/QGC routing and RTSP camera options, but it should be
optional and pinned if adopted.
