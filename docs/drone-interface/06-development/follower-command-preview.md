# Local Follower Test

Follower Test (`COMMAND_PREVIEW` internally) is the maintained way to exercise follower calculations with a
recorded video while no aircraft or PX4 simulator is connected. It runs the
same tracker-to-follower and schema-aware `CommandIntent` boundary used by the
live path, but replaces the vehicle command publisher with a bounded local
intent recorder.

It is **not** autonomous Following, a PX4 simulator, a MAVLink test, or proof of
vehicle response. `commands_sent_to_px4` remains `false` by contract.

## Safety Boundary

Follower Test requires all of the following:

- `Follower.FOLLOWER_EXECUTION_MODE: COMMAND_PREVIEW`
- `VideoSource.VIDEO_SOURCE_TYPE: VIDEO_FILE`
- an open, fresh replay frame and an active tracker target
- an available and active `FOLLOWER_CIRCUIT_BREAKER`
Both safety-bypass settings default to `false`. If an operator enables either
for a local diagnostic, Follower Test remains available and reports the exact
typed warning from the backend. `CIRCUIT_BREAKER_DISABLE_SAFETY` bypasses local
follower calculations. `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES` is more
dangerous: in live `PX4` mode it may permit dispatch when required safety
infrastructure fails. Neither setting can add a PX4/MAVSDK publisher to
`COMMAND_PREVIEW` or authorize recorded-video replay in live `PX4` mode.

`COMMAND_PREVIEW` is the default selected by the explicit beginner/lab
`make demo` path. The checked-in runtime default remains `PX4`; it requires a
live, non-replay source and an inactive circuit breaker before it can enter the
MAVSDK/PX4 path.

## Configure

The supported setup profile applies the complete preview boundary from the
single checked-in configuration source:

```bash
make setup-profile PROFILE=follower_command_preview
```

For a temporary manual configuration, set the execution mode and select a
video-file source:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
Follower:
  FOLLOWER_EXECUTION_MODE: COMMAND_PREVIEW
```

Keep the circuit breaker active. Leave the two bypasses false unless the local
test specifically needs to inspect follower behavior without those checks. Do
not add a second preview config file or edit generated `configs/config_schema.yaml` by
hand. Run `bash scripts/check_schema.sh` after changing the default schema.
The execution-mode selector applies immediately to the next Start action; it
does not convert or otherwise mutate an active PX4 or preview session.

The dashboard exposes the same setting as the small **Follower test** switch in
the Circuit Breaker card. The switch writes
`Follower.FOLLOWER_EXECUTION_MODE` through the canonical transactional config
API; it does not introduce a second setting. It can be enabled only while PX4
command dispatch is blocked and cannot be changed during an active follower
session. Turn Follower Test off before releasing the circuit breaker for live
PX4 command dispatch.

## Run And Inspect

1. For the shortest beginner path, run `make demo`. It applies the
   `beginner_lab` profile and starts the dashboard plus main app. Developers who
   need only the profile can run `make setup-profile
   PROFILE=follower_command_preview` and start the runtime themselves.
   The beginner profile selects `mc_velocity_chase` so forward and steering
   intents are visible during replay; the standalone preview profile preserves
   the follower already selected by the operator.
2. Open the dashboard and select a classic or Smart target.
3. Confirm the action panel says **Start Follower Test**, not Start Following.
4. If a diagnostic safety bypass is intentionally enabled in Settings, read the
   warning and keep the circuit breaker active. The warning distinguishes the
   local calculation bypass from the dangerous live safety-module bypass;
   neither creates a PX4/MAVSDK publisher in `COMMAND_PREVIEW`.
5. Start the test and watch the follower telemetry card for `COMMAND_PREVIEW`.
6. Inspect the latest fields and `last_command_intent` in the dashboard. API
   clients may read the same typed resource using the authentication required
   by the active exposure profile:

   ```bash
   curl -s -H "Authorization: Bearer $PIXEAGLE_API_TOKEN" \
     http://127.0.0.1:5077/api/v1/following/telemetry | jq
   ```

   `browser_session` deployments should use the signed-in dashboard instead of
   exporting a browser cookie into shell history.

7. Stop the test before changing the follower profile or source.

The action label is selected from the typed execution mode. `COMMAND_PREVIEW`
shows **Start Follower Test**; `PX4` shows **Start Following**. The circuit
breaker is an independent permission gate and never decides which label or
execution path is shown.

### Interpreting Zero Commands

An all-zero field set does not by itself mean command generation failed. The
dashboard distinguishes these states:

- **Intent recorded**: a fresh, schema-valid intent exists, even when every
  numeric field is zero;
- **Hold output**: the prior intent was invalidated and the active profile's
  fail-closed defaults are in force;
- **Waiting for intent**: no current intent has been accepted yet.

`mc_velocity_position` intentionally commands zero forward and lateral speed.
It maintains position and only changes yaw rate and optional altitude, so a
centered target can produce a valid all-zero intent. The beginner lab profile
selects `mc_velocity_chase` to make forward and steering intent changes easier
to see. This is a demonstration choice, not a different safety boundary.

### Retargeting During A Test

Selecting another classic ROI or Smart detection while Follower Test is active
keeps the test session running. PixEagle first invalidates the previous command
intent and verifies commander defaults, then replaces the target. The telemetry
card shows **Hold output** until a fresh target update produces the next intent.

The tracker implementation may also be replaced during `COMMAND_PREVIEW`; the
test stays active in hold and requires a new target. Live `PX4` Following does
not allow tracker implementation replacement. A live operator may reselect a
target with the current tracker, but must stop Following before changing the
tracker implementation.

The typed action endpoint remains `/api/v1/actions/offboard-start` for API
compatibility. Its response and status snapshot identify `execution_mode` and
`commands_sent_to_px4`; the shared endpoint does not mean that Preview enters
Offboard mode.

## What This Proves

Preview evidence can show:

- the selected tracker output reached the active follower;
- follower math produced finite, schema-valid, bounded command fields;
- retargeting, target loss, recovery, and failsafe intent handling behave as
  expected locally;
- the dashboard/API expose the resulting intent and explicit claim boundary.

It does not show:

- MAVSDK connection or Offboard acknowledgement;
- MAVLink routing, PX4 mode transitions, or telemetry freshness;
- PX4 response, vehicle dynamics, geofence behavior, or real-aircraft safety.

Use the maintained follower contract tests for deterministic regression and the
separate SIH/SITL/Gazebo evidence workflows for PX4-in-the-loop validation.

## Troubleshooting

If Start Follower Test is disabled, read the command-preview reason shown by
the typed following status. The common causes are no active target, a closed
video source, a cached/EOF frame, the wrong source type, or an inactive or
unavailable circuit breaker. A safety-bypass flag produces a warning but does
not disable this local-only test.
