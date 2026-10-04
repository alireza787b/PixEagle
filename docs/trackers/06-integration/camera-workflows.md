# Camera video, tracking and control ownership

A camera's RTSP video is independent of where tracking runs. A camera with
built-in tracking can still provide video to PixEagle Classic or Smart. Choose
the workflow in the web Dashboard configuration; QGC retains operational
tracker/model/follower choices and a link to the Dashboard.

Fresh configuration uses the bundled `resources/test4.mp4`, CSRT on PixEagle,
no camera provider or controls, `mc_velocity_position` with yaw enabled and
altitude guidance disabled, altitude safety enabled and the circuit breaker
active. Thus the default follower rotates toward the image target without
horizontal translation or automatic climb/descent. A valid tracker alone never
starts following. Explicit saved camera installations are preserved; use Config
Sync preview/apply while following is inactive to adopt changed defaults.

| Workflow | Video source | Startup tracker | Camera provider/control | Follower input |
| --- | --- | --- | --- | --- |
| Ordinary camera, including RTSP from a gimbal | RTSP, USB, CSI or another supported source | Local Classic, for example CSRT | Disabled for strict video-only use | Local image position |
| Local tracking with optional camera joystick | Supported video | Local Classic/Smart | Enabled; manual control enabled | Local image position |
| Camera-owned Classic/Smart | Matching full-frame camera RTSP | Gimbal | Enabled; control enabled for native selection | Fresh camera angles and target state |
| External camera application owns tracking | Matching camera RTSP if wanted | Gimbal | Enabled; native control disabled | Fresh camera angles and target state |

## Use the gimbal as an ordinary RTSP camera

Merge these paths into the existing configuration; this is not a complete
configuration replacement:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_OPENCV
  RTSP_URL: rtsp://192.168.0.108/stream=0

Tracking:
  DEFAULT_TRACKING_ALGORITHM: CSRT

GimbalTracker:
  ENABLED: false
  CONTROL_ENABLED: false

Follower:
  FOLLOWER_MODE: mc_velocity_position

FOLLOWER_CIRCUIT_BREAKER: true
```

Use your camera's actual RTSP URL. `mc_velocity_position` is the ordinary
default: zero horizontal translation, with visual yaw and optional altitude
guidance. Select another compatible follower intentionally; local tracking
cannot supply gimbal angles to a `gm_*` follower. Local Smart additionally needs
the Full AI runtime and an installed compatible model. Switching to PixEagle
tracking does not install AI or enable it automatically.

To switch the engine interactively, use **Tracking runs on: PixEagle** in
Advanced settings. It applies and saves the local startup choice through the
same backend service in QGC and the Dashboard. Select the local tracker/model
in operational options. Engine switching does not silently choose a different
follower, restore a target or start following. Provider/video configuration
changes require a backend restart; stop tracking/following and apply them with
the existing launcher/service workflow. See
[configuration application](../../apis/native-configuration.md).

Stop camera tracking/manual movement before handing video to local tracking.
Disable any independent camera application that could keep moving the lens.
An RTSP-only configuration neither locks the camera mechanically nor controls
another application's camera commands. For image-guided following, maintain
the intended lens orientation; a moving viewpoint changes image errors.

## Keep the joystick with local tracking

Keep a local startup tracker, set `GimbalTracker.ENABLED: true` and
`CONTROL_ENABLED: true`, and configure the actual provider/network. The single
camera owner exposes manual controls while local Classic/Smart supplies target
positions. Camera-owned target selection is absent in this workflow. Manual
movement and aircraft following remain mutually exclusive; moving the camera
does not create valid angle input for a normal follower.

## Camera-owned tracking and mounting

Use `Tracking.DEFAULT_TRACKING_ALGORITHM: Gimbal`, an enabled provider and
a compatible `gm_velocity_chase` or `gm_velocity_vector` follower. Enable camera
controls for QGC/Dashboard Classic/Smart target selection; leave them disabled
when the external camera application owns selection. Camera Smart runs in camera
firmware; PixEagle Smart uses local models. See the
[gimbal tracker reference](../02-reference/gimbal-tracker.md).

`GimbalTracker.MOUNT_TYPE: HORIZONTAL|VERTICAL` selects the supported raw-angle
installation preset. Provider-specific expert corrections live in the same
`GEOMETRY_OVERRIDE` group. They affect angle followers, not pixel-following
geometry or motor/image rotation. Raw camera telemetry remains unchanged.

For ordinary cameras, `VideoSource.FRAME_ROTATION_DEG` and `FRAME_FLIP_MODE`
orient the video, while each normal follower declares its viewing assumptions.
For example, Ground is intended for downward/oblique views; Chase assumes a
forward fixed camera. Ground's existing `IS_CAMERA_GIMBALED` correction describes
stabilization, not the camera-owned tracker engine. There is no universal
fixed-camera horizontal/vertical installation transform equivalent to the
gimbal angle presets. `Setpoint.CAMERA_YAW_OFFSET` is not a replacement for a
complete installation rotation. Do not guess an axis swap for unsupported
mounts; arbitrary mounting geometry remains later scope.

## Qualification boundaries

Synthetic tracker observations in SIH can prove follower command signs,
publication and simulated aircraft response. They cannot prove acquisition,
visual convergence, camera motor stopping or physical mounting conventions.
Keep PixEagle aircraft commands blocked for hardware ground checks. Physical
camera acceptance, network/process-failure motor behavior and real flight have
separate gates.

## Fixed-wing without an airspeed sensor

Sensorless fixed-wing support is an explicit remaining requirement. A speed
policy belongs in Dashboard Advanced configuration, not routine QGC controls.
Prefer qualified PX4 measured or synthetic airspeed (ground minus estimated
wind) with source/freshness/wind validity. The explicit `FW_ATTITUDE_RATE.ALLOW_GROUND_SPEED_FALLBACK` checkbox remains
false by default. Enabling it allows fresh ground velocity as a control-speed
proxy only when airspeed is unavailable; valid low airspeed is never bypassed.
The source stays labelled as ground velocity, not measured airspeed. The current
speed limits still apply. Save while following is inactive; the existing schema
reports follower restart. Full airframe, wind, trim, bank/climb and handoff
qualification remain open, and `fw_attitude_rate` remains live-unqualified.

PX4's [airspeed selection](https://docs.px4.io/v1.17/en/sensor/airspeed) describes
synthetic estimation. Its [sensorless VTOL guidance](https://docs.px4.io/main/en/config_vtol/vtol_without_airspeed_sensor)
addresses position-controlled flight and airframe-specific preparation, not
acceptance of PixEagle raw-rate Offboard guidance. Simulator startup-only success
and synthetic Command Preview remain distinct from actual follower publication.


## Recorded video: preview or actual isolated SIH

Dashboard **Follower Test** uses `Follower.FOLLOWER_EXECUTION_MODE: COMMAND_PREVIEW`.
It records intents without sending PX4 commands and requires the flight-command
block to remain enabled. Reuse this mode for mathematics and workflow previews.

To move the simulated aircraft, use the existing `PX4` execution mode and the
advanced Dashboard Configuration → Follower setting **Allow recorded video for
isolated SIH following** (`SIH_RECORDED_VIDEO_FOLLOWING`). Its factory default is
`false`; saving requires a backend restart. There is no extra QGC switch.

The checkbox alone cannot authorize replay on a hardware deployment. Admission
requires the supported isolated SIH launcher, its private current-network-namespace
binding, matching simulated command/telemetry identities and loopback routes.
Current decoded frames, valid measured tracking, aircraft association, flight
state, altitude safety and the circuit breaker still apply. Source metadata
continues to identify recorded video. Frozen frames and EOF boundaries cannot
become fresh commands. QGC labels authorized operation **SIH following**.

Prepare an explicit test profile with the existing tool:

```bash
python tools/prepare_sitl_gimbal_profile.py --directory /path/to/new-private-profile \
  --tracking-engine local --recorded-video test11.mp4 \
  --follower-mode mc_velocity_position --allow-recorded-sih-following
bash tools/run_gimbal_sih_probe.sh --hold /path/to/new-private-profile
```

This starts command-blocked. Verify the simulated aircraft, take off above the
lower safety margin, select a tracked target, explicitly unblock commands and
start following. Stop and re-enable the block before closing the test. A backend
restart restores the block and resumes no operations. Profile manifests are
immutable launch receipts: after saving configuration, prepare a new profile
before relaunching instead of editing its manifest.

`test11.mp4` supplies about 4 minutes 50 seconds of bundled thermal footage. It
loops with an explicit source boundary; target loss/reacquisition remains real.
Its moving image is independent of SIH vehicle pose. Publication and simulated
response establish delivery, not visual convergence or physical gain tuning.
