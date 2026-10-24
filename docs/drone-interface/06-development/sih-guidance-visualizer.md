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

The 3D view uses local NED coordinates: north, east, down. The drone marker and
path are drawn only from PX4 pose records. The red command arrow is intent and
is never treated as a vehicle trajectory. Missing or stale pose and command
records produce visible gaps and `unknown_or_stale_evidence` flags.

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
- ordinary 2D camera chase with altitude disabled.

The visualizer reuses `tools/sitl_gimbal_geometry_fixture.py` for world-target
angle generation in SIH tests. It does not introduce another mount transform.

## Validation flags

The report checks timestamp gaps, stale pose, missing publication, velocity and
yaw limits, requested/effective speed, altitude-disabled down commands, and
recorded state/event labels. A clean report is evidence that the supplied
artifacts are internally consistent; it is not a substitute for PX4, camera,
HIL, or field acceptance.
