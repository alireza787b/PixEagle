# Follower Command Preview

Command Preview is the maintained way to exercise follower calculations with a
recorded video while no aircraft or PX4 simulator is connected. It runs the
same tracker-to-follower and schema-aware `CommandIntent` boundary used by the
live path, but replaces the vehicle command publisher with a bounded local
intent recorder.

It is **not** autonomous Following, a PX4 simulator, a MAVLink test, or proof of
vehicle response. `commands_sent_to_px4` remains `false` by contract.

## Safety Boundary

Command Preview requires all of the following:

- `Follower.FOLLOWER_EXECUTION_MODE: COMMAND_PREVIEW`
- `VideoSource.VIDEO_SOURCE_TYPE: VIDEO_FILE`
- an open, fresh replay frame and an active tracker target
- an available and active `FOLLOWER_CIRCUIT_BREAKER`
- `CIRCUIT_BREAKER_DISABLE_SAFETY: false`
- `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES: false`

The default `PX4` mode is unchanged. It requires a live, non-replay source and
an inactive circuit breaker before it can enter the MAVSDK/PX4 path. Changing a
circuit-breaker safety bypass does not authorize replay or turn the preview
into a flight mode.

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

Keep the three circuit-breaker values above in their safe state. Do not add a
second preview config file or edit generated `configs/config_schema.yaml` by
hand. Run `bash scripts/check_schema.sh` after changing the default schema.
The execution-mode selector applies immediately to the next Start action; it
does not convert or otherwise mutate an active PX4 or preview session.

## Run And Inspect

1. Start PixEagle with a video file and the `follower_command_preview` profile.
2. Open the dashboard and select a classic or Smart target.
3. Confirm the action panel says **Start Command Preview**, not Start Following.
4. Start the preview and watch the follower telemetry card for `COMMAND_PREVIEW`.
5. Inspect the latest fields and `last_command_intent` in the dashboard. API
   clients may read the same typed resource using the authentication required
   by the active exposure profile:

   ```bash
   curl -s -H "Authorization: Bearer $PIXEAGLE_API_TOKEN" \
     http://127.0.0.1:5077/api/v1/following/telemetry | jq
   ```

   `browser_session` deployments should use the signed-in dashboard instead of
   exporting a browser cookie into shell history.

6. Stop the preview before changing the follower profile or source.

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

If Start Command Preview is disabled, read the command-preview reason shown by
the typed following status. The common causes are no active target, a closed
video source, a cached/EOF frame, the wrong source type, or an inactive or
unavailable circuit breaker. Do not solve this by disabling the safety gate;
fix the selected profile or input state.
