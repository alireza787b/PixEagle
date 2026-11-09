# Follower SIH qualification

PixEagle keeps one scenario contract for all registered followers. A scenario
declares the airframe, real input type, command type, independent moving target,
stable-flight gate, altitude mode, speed-source policy, faults, and acceptance
requirements. The visualizer can replay the scenario without claiming flight
evidence; PX4 acceptance requires separate observed pose and publication traces.

## Profiles and airframes

| Profile | PX4 model | Input | Command | Public altitude default |
| --- | --- | --- | --- | --- |
| `mc_velocity_chase`, `mc_velocity_ground`, `mc_velocity_distance`, `mc_velocity_position` | `sihsim_quadx` | image position | body velocity | off |
| `mc_attitude_rate` | `sihsim_quadx` | image position + airframe state | attitude rate/thrust | off |
| `fw_attitude_rate` | `sihsim_airplane` | image position + airframe state | attitude rate/L1-TECS intent | off |
| `gm_velocity_chase`, `gm_velocity_vector` | `sihsim_quadx` | gimbal angles | gimbal-derived body velocity | off |

The private vertical-gimbal profile is an explicit configuration overlay; it may
enable altitude guidance without changing the public factory configuration.
Horizontal and vertical mounts use the shared mounting-geometry contract.

The viewer distinguishes the physical forward axis from MAVLink's heading-only
velocity frame. Command arrows use canonical NED vectors computed by the trace
reader, without another JavaScript quaternion rotation. Missing heading or
command components leave direction unknown. CSV includes `command_n/e/d` beside
the original submitted fields; neither vector is integrated into aircraft pose.

Native FW/VTOL reports use scenario version 2. The registered follower's phase
capabilities determine whether `fixed_wing_external` or `vtol_external` is
compatible; the viewer does not maintain another follower-name matrix. Each
sample retains its actual command contract. FW shows course, EAS request,
native EAS reference, observed EAS, and height rate or AMSL altitude hold.
EAS is not ground velocity or a 3D command magnitude. The course arrow is
horizontal direction only, while observed PX4 pose supplies the flight path.
PX4's native FW forward axis is required for the FW glyph, including tailsitters;
the renderer never substitutes or rotates the physical mount a second time.

The reusable template is
`tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml`. Record the
actual independent target trajectory in `trace/target_truth.jsonl` and native
fields in the existing publication/state traces. Successful submitted commands
take precedence over proposed tracker commands. Timeline strips have separate
units and ranges; gaps remain unknown. Playback uses recorded timestamp spacing.
HTML is self-contained and works offline; CSV and PNG preserve the same command
semantics. This format support is not evidence that native FW/VTOL qualification
has passed.
Imported target truth retains its own `target_timestamp_s` in JSON/CSV. Target
speed is differentiated at those source times, not at interleaved publication
times. A gap in an imported truth trace stays unknown; it is not replaced by
the scenario trajectory. Continuity events/reasons retain their authoritative
state-trace values separately from tracker classification.

For native Vector component checks, `tools/run_native_vector_sih.py` verifies an
already-running isolated Docker SIH instance and its UID before control. It
defaults to read-only verification; `--execute` waits for seven stable airborne
FW Hold samples near `--test-altitude`, then joins the production follower, phase binding, continuity
supervisor and existing command publisher. It never arms or takes off. The
temporary simulator configuration, independent target path, observed pose,
commands, handoff and source revision are retained in its output directory.
This component runner does not qualify the HTTP/App startup path or VTOL
transitions; those remain separate gates. The normal read-only visualizer can
render its `scenario.yaml` and trace directory directly.
The runner also accepts stable native VTOL MC hover without demanding FW
airspeed. `--mc-request` is an explicit simulated operator speed adjustment;
it is not written to the saved configuration. The runner still never requests
VTOL transitions: an independently controlled simulator/pilot must initiate them.
Mixed-phase traces retain the actual contract for each publication.
An optional `--scenario PATH` supplies the independent world-target trajectory
through the same version-2 YAML contract. Mount, altitude mode and actual
airframe must agree. The runner rejects unsupported fault injection and saved
scenario speed edits rather than pretending to execute them; `--mc-request`
remains an explicit simulated operator action. Actual limits and continuity
policy come from the loaded configuration and appear in the retained scenario
and per-phase state trace. Target coordinates are never reanchored to the drone.
Phase spans report actual range/altitude changes without replacing the overall
response checks. In particular, a 6 m/s target can outrun the public 0.25 m/s²
MC startup ramp in a short transition test. Successful ownership transitions
alone do not prove target closure or altitude acceptance.

Native component scenarios support `target_loss` stimuli using the existing
fault shape: `{kind: target_loss, at_s: 4, duration_s: 2}`. Target truth continues
independently while the tracker supplies no angle or usable measurement.
Fresh reacquisition returns through the production continuity supervisor.
Other fault kinds remain explicitly unsupported by this runner.
For an expiry test, pass `--expect-handoff maximum_coast_time_reached`; a missing
or different handoff fails the test. Without that option, every early handoff
fails. The result still requires observed aircraft response, publication,
altitude limits and confirmed Hold with no later publication. Fault declarations
never change recovery budgets or follower tuning.

The component result separately checks observed range reduction, altitude hold
or vertical response, altitude floor, successful handoff and stopped publication.
Completing all command submissions alone cannot mark the run passed. The hold
tolerance is a test acceptance value, not another flight-control limit.

## Safe command

The dry-run validates the selected checked-in scenario and never starts a process:

```bash
PYTHONPATH=src .venv/bin/python tools/run_sih_follower_validation.py \
  --follower mc_velocity_position
```

MC image profiles now use the PixEagle-owned worker with a physically projected
moving world target, not fixed image coordinates. The worker waits for seven
fresh airborne Hold observations before engaging, retains actual PX4 pose and
ULog, and verifies production dispatch, publication, response and Stop. Its
fixed-camera axes/FOV describe a simulated sensor, not a calibrated real camera.

An isolated run is explicit and needs Docker plus the repository's configured
Python environment and pinned sidecars. No host port or hardware is exposed:

```bash
PYTHONPATH=src .venv/bin/python tools/run_sih_follower_validation.py \
  --execute \
  --follower mc_velocity_position \
  --evidence-root reports/sitl/mc-position-$(date +%Y%m%d-%H%M%S)
```

Use `--follower` for each MC image profile. `--enable-altitude-control` explicitly
changes the staged test configuration, never the saved installation. `--scenario`
accepts a validated MC world-target YAML; unsupported faults are rejected.
The retained scenario records actual resolved limits/policy and the once-frozen
target anchor. Nominal and loss cases are separate: use
`tools/sih_visualization_scenarios/mc_velocity_chase-qualification-loss.yaml`
with Chase to check its default immediate handoff. Current scenarios do not
claim retarget, takeover or all fault coverage. Rate-mode qualification still
requires its observed attitude and thrust envelope; successful commands alone
cannot pass it.

Gimbal/FW legacy drivers remain separate command-sign infrastructure; they are
not upgraded to moving-world-target qualification by this change. Use the native
component runner described above for native FW evidence. Remaining host-launcher
consolidation is recorded as S10 debt.

The runner rejects an acceptance result unless it has:

- a target-truth trace independent of PixEagle's transforms;
- synchronized PX4 position and attitude observations;
- successful Offboard publication records;
- no stale pose or publication gaps;
- the profile's declared input and command contract.

The generated `summary.json` and `visualization/index.html` are diagnostic
artifacts. They label the evidence as synthetic replay or PX4-observed SIH;
they never integrate command intent to invent a vehicle trajectory.

## Fixed-wing speed source

`FW_ATTITUDE_RATE.SPEED_SOURCE_POLICY=auto` prefers fresh PX4 airspeed and then
uses fresh ground speed as `ground_speed_proxy`. Reports include the source,
measurement, freshness, trim/reference speed, and parameter provenance. The
reference `INITIAL_ENGAGING_SPEED` is not measured airspeed. Missing or stale
speed fails closed. PX4 speed limits and stall-related parameters take
precedence over local defaults when the telemetry owner supplies them.

## Evidence boundary

The synthetic gallery and fixtures are useful for command-contract regression,
axis signs, limits, loss, retargeting, and report rendering. They are not SIH
acceptance. A run remains pending until the independent PX4 pose, target truth,
publication, parameters, runtime versions, and handoff artifacts are retained
under the same run directory. Camera, field, HIL, and real-aircraft claims are
separate later gates.
