# Native guidance phase-exit component case

`tools/run_native_guidance_cycle.py` reuses the canonical isolated Runtime,
DDS/bootstrap/readback/pre-arm gates, stable-window predicate and existing
native vector runner. It prepares settled MC, follows an independent world
target, requests one pilot front transition, verifies original-owner retirement,
and requests a new explicit FW Start after settled FW readiness. Each Start uses
production guidance/continuity/commander/transport and a separately correlated
native acquisition. No application startup or hardware is exercised.

The first fixture is `tools/native_baseline_scenarios/gazebo-guidance-phase-exit.json`:

| Stimulus | Declared value |
|---|---|
| Native source/plant | Existing reviewed stock Gazebo quadtailsitter build; sole MIS30/logger131 startup overlays |
| World target | Anchored once from measured initial MC pose/heading, 1000 m forward and 35 m right; moves 0.25 m/s along that original heading for 300 s |
| First Start | MC requested speed 1 m/s; 20 s component budget; one pilot front-transition trigger at 8 s |
| Second Start | Fresh settled FW admission; 15 s of following then ordinary Stop |
| Mounts | One fresh host/capture per HORIZONTAL or VERTICAL invocation |

The geometry gives observable MC and FW intent without requiring an intercept
within either short pursuit. Original world-target YAML/clock bytes survive both
Starts; target motion during native transition is retained, never reset to the
aircraft. `target-anchor.json` and each component's `start-pose.json` archive
actual packet pose/heading. Tracker projection is explicitly simulated; flight
pose and closed ULog ground truth come from the simulator. The loaded continuity
policy, including its existing 4 m/8 s behavior, is not overridden. Short loss
and reacquisition use the same runner's optional FW `faults` declaration:

| Fixture | FW stimulus and expected outcome |
| --- | --- |
| `gazebo-guidance-fw-reacquire.json` | Lose observations at 4 s for 1.5 s; reacquire, then ordinary Stop |
| `gazebo-guidance-fw-loss-expiry.json` | Brief loss at 3 s, recovery, then 9.5 s loss at 9 s; expect `maximum_coast_time_reached` and correlated FW Hold |

Select a fixture using `--case-fixture tools/native_baseline_scenarios/<name>`.
These declarations inject missing tracker evidence through the existing
component runner, never reset target truth or add another recovery timer.
`expected_handoff` checks the observed outcome; it cannot authorize a handoff.
The production FW phase override supplies its eight-second policy without the
MC travel budget. Source traces must independently show loss, confirmation,
restoration, stable course/speed and observed Hold. Declaring a case is not
evidence that its recovery behavior passed.

After source/scenario preparation, one read-only native observation refreshes
the accepted pose before initial projection. It must retain the original
qualified stable phase/binding and admission deadline; existing projection
freshness limits still apply. The target clock and old sample receipts are
never restamped to cover setup latency.

The user's clarified scope separates native pilot-maneuver response from
following ownership. All full raw pose/envelope data and native 2 m failures
remain available. Pursuit altitude/range acceptance uses measured active
pursuit rows, followed by a hard closed-log check using native acquisition,
phase, retirement and external-mode epochs. No maxima are subtracted. Native
publication cadence is checked through the retained external-authority/drain
interval, including both edges, against 100 ms. Cadence qualification requires
the canonical capture's pinned build/compiled producer, original isolated
runtime witnesses, native external-mode epoch and supported command payloads.
Unsupported provenance or equal release-tick ambiguity stays UNKNOWN and cannot
pass. API-call counters and logged receipt counts remain diagnostics; individual
command delivery stays UNKNOWN. The two FW topics are independently stamped
receipts, each requiring the same 100 ms cadence, without an exact timestamp
intersection. Attitude publication ties require strictly advancing native
sample timestamps, bounded age, finite quaternion and stable reset counter.
Invalid/reset/stale raw 3D pose/velocity or attitude data cannot be hidden by
sampling or phase selection. Ground-truth estimator validity flags retain their
source meaning; they are not used to discard numeric simulator truth.

Original-token reactivation, late intent/Hold/engage writes after the phase
witness, changed publication counters after release, uncorrelated receipts or
unqualified phase/readiness are independent failures. A phase exit uses its
matched native retirement and observed requested phase. A native conditional
release may confirm correlated Hold while preserving the transition; an
`owner_already_released` receipt requires independent fresh owner-free state
without demanding a newly executed Hold. Neither permits a new backend handoff
after the phase witness. Ordinary Stop still requires correlated Hold
confirmation. New session/token/native activation are required; production
does not require a network reconnect. This component fixture creates separate
ObservationConnections, so same-App/same-connection HTTP recovery remains gated.

Preview performs no Docker/client/staging/control action:

```bash
PYTHONPATH=src python tools/run_native_guidance_cycle.py --mount HORIZONTAL
```

Execution additionally needs explicit `--execute`, a fresh `--output`, reviewed
`--simulation-build-manifest`/`--build-repository` and pinned `--adapter-bundle` /
`--adapter-file-manifest`. The prospective argv and exact source/config/binary
pins belong to the reviewed run packet. No new firmware build or native tuning
is needed. Cleanup retains the original two token-owned CIDs and logger closure
even when component or evidence gates fail.

Software checks and a replay of a retained actual target-free FW normal-Stop log
validate the tooling only. The old native-only results remain FAILED. The first
actual VERTICAL attempt failed initial projection before acquisition, with zero
publications: source/scenario setup aged the retained stable-state snapshot.
That failed capture remains unchanged. The corrected VERTICAL R2 subsequently
exercises both Starts; MC received cadence and altitude pass, while FW altitude
fails at 2.1956 m against the 2 m gate. HORIZONTAL R1 verifies MC release but
refuses FW Start before acquisition when a fresh composite packet has not yet
advanced its oldest constituent timestamp. Retain both failures; no whole-S7,
application, sensorless, private-airframe or hardware qualification follows.

The existing `.github/workflows/tests.yml` coverage job selects this unmarked
test module through `pytest tests/`. The smaller unit-only job does not select
top-level tooling tests. Reproduce the focused regression checks with:

```bash
PYTHONPATH=src pytest tests/test_native_guidance_cycle.py \
  tests/test_native_guidance_evidence.py \
  tests/test_native_transition_baseline.py tests/test_native_vector_sih.py \
  tests/test_native_ownership_sih.py tests/unit/test_sih_visualization.py \
  tests/unit/core_app/test_retarget_admission.py -q -p no:cacheprovider
```
