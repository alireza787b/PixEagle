# Native guidance phase-exit component case

Closed-log attribution is bound to the exact Runtime and asset hashes in
`guidance-evidence-source-v5.json` (schema 3, protocol 5). The archived
`guidance-evidence-source.json` remains the unchanged protocol 4 contract.
Reproduce historical captures with their
recorded source revision and build authority; a newer startup recipe does not
retroactively authorize an older artifact. Stored audits and original verdicts
remain unchanged when these pins advance.

New acquisitions require the exact typed Start context from the final fresh
passive packet before engagement. The request, original acquisition receipt
and last preceding observed context must agree; a newer changed observation
cannot be hidden by an earlier matching one. The shared adapter bootstrap
helper is pinned alongside the Runtime and compiled assets, and its exact hash
is recorded in the host manifest. Unsupported old protocol/context/host records
cannot qualify under this tool; replay them using their frozen original code.
Synthetic protocol projections in unit tests do not upgrade recorded captures.
Normal training-launcher logs are a separate artifact kind and do not establish
canonical isolated Runtime provenance or full-App following qualification.

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
| Native source/plant | Reviewed stock Gazebo quadtailsitter by default; explicit no-pitot fixture requires its matching verified resource variant |
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

After source/scenario preparation, read-only native observations refresh the
accepted pose before initial projection. A composite packet can advance some
sensors without advancing its oldest constituent. It is checked without adding
a timed stability sample; the helper waits at the existing 50 ms cadence for
genuine progress within the original deadline. Invalid intermediate telemetry
still aborts. The qualified phase/binding and projection freshness limits remain
unchanged. Target clocks and old sample receipts are never restamped.

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
refuses FW Start before acquisition on a duplicate-time composite packet.
The corrected helper on `f8615943c` subsequently reaches actual FW acquisition.
Its HORIZONTAL R2 altitude error is 2.1035 m (2.1585 m simulator truth), still a
failure. Neutral-drain and same-tick native boundary payloads outside the strict
auditor's supported forms retain UNKNOWN attribution; they are not silently
counted as pursuit or proof of obsolete commands.

The first actual loss cases on the same source observe brief FW loss,
confirmation/restoration, and a separate long-loss handoff after 8.026 s with
correlated native Hold. Original whole-case failures remain: FW altitude errors
are 2.0922 and 2.2615 m, and strict source-attribution limits remain. Independent
trace audits accompany these cases; no whole-S7, application, retarget/takeover,
sensorless, private-airframe or hardware qualification follows.

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

## Explicit no-pitot guidance fixture

`tools/native_baseline_scenarios/gazebo-guidance-no-pitot.json` selects the
shared `gazebo-quadtailsitter-no-pitot-hold-cycle.json` installation fixture.
It requires the verified `quadtailsitter-no-pitot-v1` manifest resource variant;
stock/variant mismatches fail before staging or launch. Use the existing command
above with `--case-fixture tools/native_baseline_scenarios/gazebo-guidance-no-pitot.json`
and that variant's exact build manifest. Preview remains read-only.

The fresh-rootfs startup overlay adds only `SYS_HAS_NUM_ASPD=0` to MIS30 and
logger profile 131. This declares the physically sensor-absent model installation;
it is not a flight-control bypass. The source-bound native parameter definition
supplies its bounds. `FW_USE_AIRSPD` is not overridden: the reviewed native
default 1 must read back unchanged, retaining native valid-airspeed use and
sensorless behavior. No groundspeed is relabeled as airspeed.

Before each existing arm/takeoff admission, the fixed read-only
`listener differential_pressure -n 1` command requires exact `never published`
with successful exit and no error output. Pinned listener/uORB source proves that
omitting `-i` checks all advertised instances immediately without the polling
branch. Each raw result and its host receipt time are retained; the result also
records the startup contract and source pins. This is point-in-time publisher
absence, not proof of whole-flight absence or stall margin. Existing deadlines,
preflight checks and original-token cleanup remain in force on refusal/cancel.

The no-pitot guidance fixture also declares
`minimum_forward_ground_speed_m_s=14.0`. This is an observed-motion test condition,
using the literal `FW_AIRSPD_MIN 14` from the locked 4018 airframe only as a
numerical reference. The source-bound default Gazebo world has no configured
wind; this fixture assumption is pinned and recorded. It is not a general
airspeed, stall-margin or real-aircraft admission rule. The canonical native
navigation heading and observed NED velocity supply the forward projection;
no tailsitter quaternion transform or command-derived motion is introduced.

All seven original settled FW states must pass, with their last state matching
the actual retained packet. `fw-motion-readiness.json` retains those states,
projections, threshold and source/world hashes. The same FW condition is retained
through the coordinator, read-only post-transition sampler, fresh FW initial
window and final Start refresh. The sampler waits for a complete ready window
within its existing deadline; an old window cannot authorize a newly
stationary/reversed aircraft. MC settling keeps its existing rules while
carrying the FW condition to the later sampler.

The shared additive logger now also requests `differential_pressure 0 0`.
Qualification still requires closed-log sensor/publisher absence and actual
native source selection, using the pinned `AirspeedValidated.msg` enums, plus
actual motion/attitude, ownership, cadence, recovery and height checks. Fixture
existence or native `airspeed_control_enabled=false` is not flight qualification.
Standalone native-transition execution refuses this fixture before launch because
its FW capture remains measured-only; this slice supports the guidance runner.

The no-pitot package keeps its own real ELF/image hashes. It is not a bitmatched
stock control flight. The single guidance source contract records both exact
`runtime_helper_sha256` and `runtime_assets_sha256` values; startup changes renew
both together. Older captures remain bound to their original
frozen helper/assets authority; no old hash is accepted as a new recipe.

The first actual no-pitot capture passed both sensor-absence probes and MC
following/release. FW Start correctly refused a seven-sample window that still
contained accelerating speeds below 14 m/s. The post-transition sampler had not
received the FW motion condition; the correction passes that same condition to
its existing wait, without lowering the threshold or extending the deadline.
The failed capture remains unchanged and contains no FW pursuit acquisition.

## Source-disjoint native Hold endpoint

The closed-log auditor keeps the external authority interval half-open:
`[activation, native mode-exit epoch)`. Its source checks, both edge gaps and
100 ms cadence threshold are unchanged. An endpoint row never supplies an
external receipt or fills a gap.

One narrow FW endpoint form can now be classified separately as
`native_hold_disjoint`. The exact compiled adapter, SDK and firmware provenance
must pass. There must be exactly one row on each FW setpoint topic, correlated
HoldConfirmed at that epoch, and unique same-epoch witnesses showing the original
owner inactive, FW/nontransition Hold and native auto-position control with
Offboard disabled. The lateral row must have finite course and acceleration
with NaN airspeed direction; the longitudinal row must have finite altitude and
NaN EAS, height rate, pitch and throttle. The compiled adapter's validated
normal/activation/transition/neutral paths cannot emit this combination;
the pinned native FMM Hold path can.

`native_right_edge` reports the classification and retained endpoint counts.
Unknown, mixed, external-shaped, duplicate, missing or uncorrelated endpoints
remain nonpassing. Native-looking interior rows still fail source attribution;
MC endpoints have no exception. Independent wire fences, counter plateaus,
retirement, pose and height checks remain required. No within-tick ordering,
absence of overwritten publications, or per-call delivery is inferred.

The source and original H2/V1 raw proof is frozen in
`reports/sitl/follower-consolidation-20261111/software-gates-s7-fw-hold-right-edge-source-review-r1/source-proof.json`.
The original no-pitot V1 FALSE remains unchanged. Any new replay is a separately
versioned derived audit, not a replacement capture or broader qualification.
