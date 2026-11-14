# Topotek input stimulus

`tools/gimbal_simulator.py` supplies **simulated body angles and tracking
status** to the ordinary Topotek provider. It is a protocol/GUI development
tool, not a physical FL-30 replica, optical tracker or aircraft simulator.
It does not move a Gazebo camera or compensate aircraft attitude yet. That
integration follows the [tailsitter training slices](followers/05-development/ubuntu-training-platform.md#next-checkpoint-vertical-external-gimbal-on-the-tailsitter).

## Run

Use the PixEagle Python environment. The optional desktop GUI needs Tk; on
Ubuntu, install `python3-tk`. Importing the module does not open a window,
start sockets, install packages or configure global logging.

```bash
python tools/gimbal_simulator.py --config /path/to/private/configs/config.yaml
```

The optional configuration is read-only. Its existing
`GimbalTracker.MOUNT_TYPE` and `GEOMETRY_OVERRIDE` determine the slider-to-raw-angle
mapping. Without a configuration, the normal horizontal preset is used.
There is no second saved mounting setting. See the [mounting guide](trackers/06-integration/camera-mounting.md).

The horizontal slider aims left/right; the vertical slider aims up/down.
**Center** restores the configured forward ray (vertical mount: raw Y/P/R
`0/90/0`). The raw-angle readout is diagnostic. These are normalized software
stimulus ranges, not qualified mechanical travel limits.

Choose simulated `TRACKING_ACTIVE`, `TARGET_LOST`, `TARGET_SELECTION` or
`DISABLED` explicitly. Starting/restarting the feed always clears simulated lock.
Changing a target-state stimulus never starts aircraft following. Freeze angles
and freeze lock status independently to exercise normal freshness handling.
Closing the window stops and joins its only UDP worker; it sends no aircraft
Stop, Hold or Start command.

## Connect a disposable backend profile

Keep normal saved hardware/public settings unchanged. Merge these values into
an isolated test profile through the ordinary configuration service:

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: Gimbal
GimbalTracker:
  ENABLED: true
  CONTROL_ENABLED: false
  PROVIDER: topotek_sip_udp
  UDP_HOST: 127.0.0.1
  UDP_PORT: 9003
  LISTEN_PORT: 9004
  MOUNT_TYPE: HORIZONTAL
  COORDINATE_SYSTEM: GIMBAL_BODY
Follower:
  FOLLOWER_MODE: gm_velocity_vector
FOLLOWER_CIRCUIT_BREAKER: true
```

Use `VERTICAL` only for the intended vertical installation, in that same
configuration. Provider setup requires backend restart. External status/angle
input is independent of video and local Classic/Smart tracking. The stimulus
implements no camera motor, image-selection or mode-control commands, so
`CONTROL_ENABLED` stays false. Ordinary QGC/Dashboard following readiness,
explicit Start, continuity, authority and safety guards remain authoritative.
No physical-aircraft test is authorized by this example.

## Protocol and evidence

| Input | Emulated response | Meaning |
| --- | --- | --- |
| Production `GAC` query | `#tpGPCrGAC` + yaw/pitch/roll signed centidegrees + checksum | Body-angle observation |
| Production `TRC` query | `#TPDP2rTRC0` + normalized state + checksum | Independent tracking state |
| Spatial angles, motor or image-selection commands | No response | Not implemented; no fake acknowledgement |

Angle and status streams have independent cadences. Each response uses the
production SIP checksum helper; acceptance is tested through the real
`GimbalInterface` parser against retained hardware packet bytes. Queries need
exact supported addresses, lengths and checksum. `OFT` is a tracking-box family;
it is never emitted or interpreted as angle telemetry. Invalid/nonfinite angles
are rejected before changing state; no hidden clamping or unsigned saturation.

The earlier standalone implementation's fake OFT angles, incorrect response
addresses, automatic motion patterns and duplicate enum definitions are removed.
Its old smoothing was not measured motor behavior and is not retained as a
second mechanical model. Future stabilization, joint limits/rates and rendered
camera pose belong to one explicitly qualified Gazebo model.

For headless protocol tests, construct `GimbalSimulator(SimulatorConfig(...))`,
then call `start()`, `set_gimbal_angles(...)`, `set_tracking_state(...)`, and
`stop()` in `finally`. The constructor starts no worker. A failed or lingering
worker prevents overlapping restart. Tests require no display or Tk:

```bash
PYTHONPATH=src pytest tests/test_gimbal_simulator.py \
  tests/unit/trackers/test_gimbal_interface_protocol.py
```

Local UDP tests prove packet transport/decoding, not real camera dynamics,
mechanical stabilization, optical acquisition, native FW timing or flight safety.
The [provider integration guide](trackers/05-development/external-gimbal-providers.md)
remains authoritative for those boundaries.

## Rendered simulator input contract

The rendered integration uses the same Topotek provider/parser, with optional
`GimbalTracker.GAZEBO_INPUT`. Null (the factory default) retains ordinary UDP.
This launcher-managed mapping declares a private Unix socket, world,
source-clock ID and maximum PX4 attitude-sample skew. `CONTROL_ENABLED` stays
false. Mount definitions and normal camera credential/control APIs are unchanged.

The private envelope carries the SIP packet, actual Gazebo observation time and
the producer's original monotonic receipt. Angle/status ages remain independent.
Repeated/reordered samples, clock/incarnation changes, invalid packets and EOF
retire the input rather than making cached observations fresh. Only angle
packets attach source timing to a tracker observation.

`gazebo_guidance_alignment.py` uses the existing connection-owned raw PX4
attitude history for both images and gimbal bearings. FW readiness and Start
apply the same declared-input gate. Status-only updates retain the original
angle/attitude pair. Video availability, the latest pose and slider positions
cannot substitute for observed-camera timing. Hardware UDP retains its
receipt-only semantics; this does not qualify hardware synchronization.

The input contract is tested offline; rendered-model and full operator
MC/FW Start/Stop/restart qualification remain pending. The first model will use
ideal stabilized pointing with configurable finite motion. Unmeasured FL-30
mechanics and image-roll behavior remain explicit assumptions.
