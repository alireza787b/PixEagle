# SIH guidance visualizer

The SIH guidance visualizer is a read-only diagnostic report generator. It
shows the PX4-observed aircraft pose, an independent world-target trajectory,
tracker/follower command intent, publication status, and active constraints in
one synchronized timeline. It does not start following, publish commands, or
integrate command intent into a predicted aircraft path.

## Offline report

Use a checked-in scenario and an existing SIH evidence directory:

```bash
PYTHONPATH=src python tools/sih_visualizer.py \
  --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
  --evidence-root reports/sitl/<run> \
  --output-dir reports/sitl/<run>/visualization
```

The output contains:

- `index.html`: self-contained playback with 3D NED scene, target/drone paths,
  line of sight, command vector, state badges, timeline, and view toggles;
- `trace.json` and `trace.csv`: aligned evidence rows;
- `summary.json`: evidence counts, gaps, and validation flags;
- `summary.png`: static report figure when matplotlib is available.

The report opens in a draggable 3D NED orbit view. Drag the scene to change
azimuth/elevation, use the wheel to zoom, and use `Reset 3D` to return to the
default camera. The orange point is the current scenario target and the blue
aircraft symbol is the current observed PX4 pose;
their dashed paths are historical evidence, not a predicted future path. The
target path and PX4 path can be hidden independently; history is deliberately
faint and dashed so the solid current markers remain the focus.
`Top`, `Front`, and `Side` expose the corresponding N/E/D projections. The
dashed line between the current markers is the current line of sight. The red
arrow is command intent: it is rotated from body FRD into NED only when a
recorded vehicle attitude is available; otherwise the report labels it as
body-FRD-only instead of inventing a transform. Missing or stale pose and
command records produce visible gaps and `unknown_or_stale_evidence` flags.

## Live read-only observation

The live mode polls an authenticated, read-only MAVLink2REST snapshot and saves
pose records before building the same report:

```bash
PYTHONPATH=src python tools/sih_visualizer.py \
  --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
  --live-url http://127.0.0.1:8080/v1/mavlink \
  --system-id 1 --duration-s 30 \
  --output-dir reports/sitl/live/visualization
```

Use `--token` when the endpoint requires a bearer token. This adapter performs
only `GET` requests and never calls PixEagle, PX4, target, follower, Stop, or
aircraft-control actions. A failed or stale snapshot is recorded as an unknown
interval.

## Scenario files

Scenario files live under `tools/sih_visualization_scenarios/` and use schema
version `1`. They define the follower profile, mount, altitude behavior,
requested speed, constraints, continuity policy, target waypoints, faults, and
expected invariants. Target waypoints use the same local NED frame as PX4.

The initial scenarios cover:

- vertical gimbal Vector guidance with moving target and altitude control;
- horizontal gimbal Vector guidance crossing rearward and entering yaw-first;
- ordinary 2D camera chase with altitude disabled;
- 2D `mc_velocity_chase` with coordinated turn and 2D `mc_velocity_position`
  with sideslip. These retain their own horizontal command semantics and do
  not expose Vector-only speed or gimbal guidance assumptions. The chase
  replay uses a 3.5 m/s configured forward ceiling against a slower moving
  target so successful closure can be distinguished from an underpowered
  pursuit. The position replay is a command-semantics and fault-handling
  check, not a chase catch-up claim.
- horizontal and vertical Vector catch-up checks where the requested 6 m/s
  command is faster than a 1.5 m/s moving target.
- a combined three-axis Vector catch-up check where the target moves north,
  east, and down in one replay.

The combined replay declares an airborne initial NED pose, holds the aircraft
for its first second, then marks the Offboard/follow phase and moves the
observed pose toward the target. The hold and follow phases are synthetic
fixture behavior; a real SIH claim still requires an imported PX4 pose trace.

The 2D reports include a one-second airborne hold, target movement, loss or
delayed-observation windows, and horizontal-only commands. Their target paths
remain at the initial altitude so a nonzero down command is a validation
failure rather than an expected part of the replay.

The catch-up fixtures can be regenerated without hardware:

```bash
PYTHONPATH=src python tools/sih_visualization_catchup_fixture.py \
  --scenario tools/sih_visualization_scenarios/gimbal-vector-catchup-horizontal.yaml \
  --output /tmp/catchup-horizontal/evidence
```

The report summary and current-sample table include observed target range. A
decreasing range demonstrates closure in the supplied evidence; a zero range
in a synthetic fixture does not prove a real PX4 response.
The summary also reports target speed and the applicable speed reference. If a
scenario asks a follower to pursue a faster target, it raises
`target_faster_than_speed_reference`; that is a scenario-design warning, not a
follower failure. Public safety defaults are not changed by these fixtures.

The 3D scene is an orientation aid, not a photorealistic simulator. The sky,
horizon, local N/E/D ground grid, altitude drop lines, axis triad, and aircraft
nose glyph make depth and vertical motion readable while preserving the exact
NED coordinates in the trace and CSV.

The visualizer reuses `tools/sitl_gimbal_geometry_fixture.py` for world-target
angle generation in SIH tests. It does not introduce another mount transform.

## Validation flags

The report checks timestamp gaps, stale pose, missing publication, velocity and
yaw limits, requested/effective speed, altitude-disabled down commands, and
recorded state/event labels. A clean report is evidence that the supplied
artifacts are internally consistent; it is not a substitute for PX4, camera,
HIL, or field acceptance.
