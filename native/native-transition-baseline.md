# Native-only transition baseline

`tools/run_native_transition_baseline.py` is an opt-in **simulator control tool**,
separate from the read-only visualizer/probe. It prepares native MC Hold,
requests one pilot front transition, observes FW Hold, requests one guarded
back transition and observes MC Hold. It never acquires following, sends an
intent or creates a target publisher. No hardware, device mount, published port
or arbitrary caller-selected airframe is supported.

By default it only prints a plan, without Docker, clients, output directories
or control actions:

```bash
PYTHONPATH=src python tools/run_native_transition_baseline.py \
  --scenario tools/native_baseline_scenarios/gazebo-quadtailsitter-hold-cycle.json
```

Actual execution requires explicit `--execute`, a strictly verified
`--simulation-build-manifest`, a new `--output`, and the existing pinned
`--adapter-bundle` plus `--adapter-file-manifest`. For a reviewed control
firmware authority, `--build-repository` forwards the same explicit source
authority used by the shared validator. Existing artifacts are never repaired
or overwritten. A future reviewed invocation has this shape:

```bash
PYTHONPATH=src python tools/run_native_transition_baseline.py --execute \
  --scenario tools/native_baseline_scenarios/gazebo-quadtailsitter-hold-cycle.json \
  --simulation-build-manifest /reviewed/build/gazebo-build-manifest.json \
  --adapter-bundle /reviewed/runtime-bundle \
  --adapter-file-manifest /reviewed/runtime-files.json \
  --output reports/sitl/new-native-only-baseline
```

The shared launch helper owns the source-built primary image/model/world,
private UID/rootfs and network isolation. The fixed observer image runs the
adapter and DDS Agent in a second token-owned container sharing only the
primary network namespace and private runtime directory. Its mount is
`/runtime`, preserving the observer image's `/work/ws` ROS workspace. There is
no ABI assumption between the two images. Both original CIDs must remain
running and verified before simulated arm/takeoff. The sidecar first runs only
the fixed DDS Agent as its foreground process. The host polls the original
private primary's fixed read-only `px4-uxrce_dds_client --instance 0 status`
command: exact connected status, converged time synchronization and UDP Agent
`127.0.0.1:8888` are required. The pinned native source sets connected only after
session synchronization, entity creation and data requests succeed; exit zero
or the substring `connected` alone is insufficient.

One detached exec then starts the ordinary adapter in that same sidecar. DDS
readiness, this single launch and socket arrival share the original 45-second
startup admission budget, checked around bounded probes and ownership
inspections. It is not a hard cancellation deadline for every Docker inspect.
The adapter's normal ten-second discovery budget is unchanged. A lost launch
reply cannot trigger another adapter launch. Raw DDS status and launch evidence
are retained; full firmware verification and the native handshake still follow
socket arrival. Fresh native observations
and native vehicle-status timestamps qualify each action within one existing
30-second preflight budget. Ordinary startup unavailability may wait; positive
owner, identity or rescue failures do not become retries.

Scenario data selects only the known SIH VTOL models or the manifest-derived
stock Gazebo quadtailsitter, MIS takeoff altitude and explicit native transition
timing/CAS fixture values. Native source bounds are checked. Pinned rcS applies
literal `PX4_PARAM_*` overrides after airframe defaults and before simulator,
commander and Navigator startup. Only a fresh empty parameter store is used;
readback precedes flight actions. No mid-run MIS write/cache barrier is copied
forward. `SDLOG_PROFILE=131` and the accepted additive nineteen-topic file are
fixed; gain, trim and native timeout tuning are not supported.

The production native client sends only hello/bind/observe. The existing stable
predicate still needs seven progressing samples, the same freshness and native
envelope checks. A target phase cannot borrow the prior phase's window. Rescue,
unknown phase, stale data or native Hold exit prevents inverse admission.
Earlier altitude performance failure alone may still permit a healthy inverse
diagnostic, but the result stays failed: the fixed 2 m reference is never reset.
All numeric raw poses, including unusable replies, contribute to the excursion
metric. Closed ULog estimator and actual ground-truth topics independently
cover the full native-clock window without filtering out pose flags or inventing
a host/native clock conversion. Missing truth/coverage, dropouts or corruption
cannot produce a pass. No active external 100 ms publication gate is exercised.

Cleanup closes the observer, attempts one original-primary logger flush and
stops both original token-owned CIDs even after probe/close/flush failure. It
adds no mode action. Commands, original observations, build/isolation/binding
proofs, native clock markers, closed logs and verdicts remain in the output.
Legacy report helpers/raw failures remain unchanged; extraction provenance and
runtime pins are in `native/baseline-runtime.json` without report-path imports.

Reproduce the software checks without any simulator:

```bash
PYTHONPATH=src pytest tests/test_native_transition_baseline.py \
  tests/test_gazebo_native_verifier.py tests/unit/test_sih_baseline.py \
  -m "not sitl and not px4 and not e2e and not hardware and not manual" --strict-config
```

The existing `.github/workflows/tests.yml` coverage step selects `tests/` with
the same external-runtime exclusions, so this unmarked mock-test file is
already included. `requirements.txt` includes the development ULog dependency;
no extra workflow or service is added. Software checks do not establish a
successful SIH/Gazebo flight. This canonical runner is initially **runtime
unqualified**. Its first Gazebo attempt failed before arm because observer
discovery started before PX4/DDS session readiness. That closed R1 evidence is
retained; the sequencing correction has software tests and requires a separately
reviewed actual capture.
These software checks do not qualify sensorless flight, a private airframe,
pursuit or hardware.
