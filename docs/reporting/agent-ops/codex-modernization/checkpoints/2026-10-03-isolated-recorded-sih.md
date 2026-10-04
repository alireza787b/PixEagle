# Recorded-video to actual isolated SIH — 2026-10-03

Final v21 operator review: operator reports the recorded workflow worked,
including Chase. Audit confirms 38/38 tracking-start successes, six tracking-stop
successes and a successful native follower selection. All 277 recorded publications
succeeded. Chase retarget generation 40 → 41 restored confirmed authority and
showed simulated yaw response. One earlier prediction-only startup abort and
target-uncertainty confirmed handoffs remain visible, consistent with the explicit
local immediate-handoff policy. This accepts the completed-Stop acquisition repair
and recorded operator workflow, not full 4b.4 or tuning/hardware qualification.
The QGC integration worktree's `custom-pixeagle/SLICE-4B-V21-ACCEPTANCE.md` records
exact evidence and the next 4b.4d network/load/recovery plan. No production setting
or gain changed during this review; physical camera testing stays deferred.

The subsequent 4b.4d repair adds an explicit guarded retry for failed Offboard
cleanup while preserving blocked target admission. The refreshed deterministic
link gate passed with zero obsolete motion and timing limits intact; the full
backend unit sweep passed 3,461 tests (41 optional skips, 14 subtests). Exact
evidence is retained under `slice-4b4-2026-10-03/link-v3-221222/` and
`recorded-sih-v22-unit-final.log` in the baseline cache.

The camera-free recorded-tracker-to-PX4 path is implemented. Physical camera
acceptance and overall release qualification remain open. Integration edits are
uncommitted and unpublished. No gains or numeric guidance limits changed.

## Operator/configuration decision

Keep Dashboard **Follower Test** as its existing local command preview:
`FOLLOWER_EXECUTION_MODE: COMMAND_PREVIEW`, no PX4 publisher, commands blocked.
Actual simulated aircraft motion uses the existing `PX4` execution/publisher path.
One advanced Dashboard Configuration → Follower checkbox, **Allow recorded video
for isolated SIH following**, saves `SIH_RECORDED_VIDEO_FOLLOWING` in canonical
configuration and requires backend restart. Factory default is off. No duplicate
QGC control, execution mode or configuration store was introduced.

Opt-in does not authorize a generic replay deployment. A supported supervisor,
private launcher receipt, current network namespace/installation, loopback
command routes, expected simulated UID and fresh matching telemetry are required.
The start path rechecks before/after Offboard; runtime authorization loss invokes
the existing handoff. A non-video tracker is independent of its optional display.
Current decoded frames and measured tracker output remain mandatory for image
following. Replay provenance remains truthful. CB/flight/altitude/identity guards
remain in force; restart restores CB and never resumes operations.

QGC displays **SIH following** and **SIH ready** from the authoritative optional
native snapshot field. A prediction-only target now reports tracker unavailability
rather than an incorrect replay-authorization error. Routine controls/layout are
preserved. The raw AI review is in the QGC worktree `custom-pixeagle/reviews/recorded-sih-replay-raw.md`;
operator acceptance is a separate checkpoint.

## Evidence

Fresh copied-source `recorded-sih-v20-validation` used actual CSRT selection,
authenticated typed tracking/follow actions and the existing 20 Hz publisher.
It recorded **168 successful publications, zero failures**, independently observed
**−36.99° simulated yaw change**, and **operator Stop → confirmed Hold**. The
preliminary v19 run independently recorded 170 successful publications and −36.33°.

A stable embedded image-text feature supplied repeatable CSRT acquisition for
this delivery probe. This proves the integrated acquisition/admission/publication
path and simulated response; it does not establish moving-object accuracy,
visual closed-loop convergence or physically optimal gains. The video image is
not coupled to SIH pose. Earlier Position/Chase/Distance synthetic-input evidence
remains separately recorded in the QGC worktree `custom-pixeagle/SLICE-4B-RESTART.md`.

Early probes caught valid lost/prediction-only target refusals and a harness
request missing its required start-attempt ID. Freshness protection was preserved.
A shared classifier corrected the misleading replay error label. The probe also
waits for confirmed airborne state rather than altitude alone and records the
actual container runtime interpreter, separately from the profile preparer.

## Renewed gates

- Backend CI Unit: **3,452 passed**, 41 optional dependency skips, 14 subtests passed.
- Integration plus route/config gates: **269 passed** (195 Integration and 74 route/parameter checks).
- Focused replay/startup/preview regressions: **241 passed**.
- Dashboard: **491 passed / 64 suites**; lint and production build passed.
- Schema generation/check, route inventory, touched Python syntax and targeted Ruff checks passed.
- QGC incremental build and applicable locked pre-commit hooks passed; **414/414 Unit/Integration tests passed**, with standard `Flaky|Network` exclusions, after both timing-fixture corrections.
- API-candidate/documentation/Dashboard contracts: **49 passed**; generated API inventory refreshed.

The first QGC run found a missing Ninja PATH for a fixture and an intermittent
late-metadata test. Ninja PATH corrected the fixture; a coarse timer could fire
before the 3-second metadata threshold. The test now uses Qt PreciseTimer.
Two subsequent runs passed 413/414 with an unrelated GPS UI timeout. The GPS
Fact group emits UI updates at one-second intervals; the test's one-second
condition timeout occasionally ended just before notification. The two relevant
checks now use the standard medium condition-wait timeout, preserving assertions
and production behavior. These attempts are retained, not erased by later results.

Fresh supervised restart passed in **7.559 seconds**: stale confirmation refused
with 409, pending configuration cleared, the same sidecars retained, commands
blocked, and no operation resumed.

## Provenance and artifacts

QGC base `2e6190bafc4f4796e29ae24cbd1d27f73b96d07d`; PixEagle base
`989d9662173b364de03b307f4208e9d0ca96451f`. Bases alone do not identify dirty
integration source. Each copied profile contains `profile-manifest.json` hashes;
QGC binary SHA-256 is recorded in `recorded-sih-qgc-binary.sha256`.

Evidence root: `/home/alireza/.cache/pixeagle-qgc-baseline/`:
`recorded-sih-unit-final.log`, `recorded-sih-integration-final.log`,
`recorded-sih-final-review-tests.log`, `recorded-sih-dashboard-tests.log`,
`recorded-sih-dashboard-lint.log`, `recorded-sih-dashboard-build.log`,
`recorded-sih-schema-final.log`, `recorded-sih-qgc-lint.log`,
`recorded-sih-qgc-timer-lint.log`, `recorded-sih-qgc-timer-build.log` and
`recorded-sih-qgc-qualification-final.log`. Earlier attempt logs, including
`recorded-sih-qgc-full-host.log`, `recorded-sih-qgc-full-final.log` and
`recorded-sih-qgc-qualified.log`, retain failures and their diagnostics. The GPS
fixture rebuild/lint results are in `recorded-sih-qgc-gps-build.log` and
`recorded-sih-qgc-gps-lint.log`; additional contracts in `recorded-sih-doc-contracts.log`.

Actual delivery/restart evidence:
`slice-4b4-2026-10-03/recorded-sih-v20-validation/logs/` contains
`recorded-sih-publish-result.json`, actual `traces/offboard-publish.jsonl`,
`traces/tracker-command.jsonl`, private binding/identity receipts and
`restart-probe-result.json`. Launcher/container image identities, source hashes
and historical backend logs remain alongside the results. Credentials are private;
evidence summaries omit passwords.

## Handoff and remaining plan

QGC worktree `custom-pixeagle/OPERATOR-RECORDED-SIH.md` is a fresh, initially command-blocked
five-minute recorded-video profile with local CSRT/installed Smart models and
Position startup. Services are stopped for the operator launch. Factory defaults
remain test4/CSRT/local engine/no gimbal/yaw-only Position/altitude safety/CB on.

Next: operator camera-free feedback, remaining 4b.4d shared-link/load and suspension
checks, final physical camera/process/network-failure retest on return, slice 5
portable harness and Linux/Windows/Android packages/CI/reviewed PRs, then slice 6
Pi/router/PX4 ground acceptance. Existing MC attitude-rate sustained-envelope and
fixed-wing follower qualification blockers remain open. Neither main repository
nor release artifacts have been updated. Real-flight qualification remains later.

### V20 follower-change defect / v21 repair

Operator v20 audit records show native Stop succeeded at 08:48:35 UTC
(12:18:35 Tehran), follower selection succeeded at 08:48:43, and subsequent
tracking-start actions validated but failed without changing target revision.
The completed teardown retained `_following_stopping`, so classic acquisition
was refused even without a follower change. Tracking Stop and Smart-mode changes
could not clear that stale flight lifecycle flag.

Clean teardown now releases that temporary admission block only after following
is inactive, no error remains, and commander/sender ownership has been removed.
The completed future and authoritative handoff result remain available for
concurrent or repeated Stop. Failed Hold, retained publishers and pending teardown
remain blocked. No UI, configuration default, gain or limit changed.

New tests reproduced the original failure before the repair. Regressions cover
pending/canceled/concurrent Stop, repeat Stop, clean PX4/preview acquisition,
failed Hold, retained publisher, and real AppController teardown followed by
native follower selection and native target execution for Position/Chase/Distance.
Fresh CI-environment gates: **3,460 Unit** (41 optional skips, 14 subtests),
**269 Integration/route/config**, **48 API/docs/test-hygiene**; schema, generated
API inventory and critical Ruff checks pass. QGC and Dashboard production source
are unchanged; their preceding **414/491** results are retained, not claimed as
new runs. Broad Ruff still reports legacy style issues; no bulk formatting applied.
The first broad test attempt used the AI runtime environment, which lacks httpx;
the complete gates above use the repository CI test environment instead.

Fresh `recorded-sih-v21-validation` exercised actual recorded CSRT → Position →
Stop → native Chase selection/acquisition/start/Stop → native Visual Centering
selection/acquisition/start/Stop. All **263 publications succeeded**, each Stop
confirmed Hold, and target revisions advanced after both switches. Independent
Position yaw changed −42.78°; Chase and Visual Centering pose observations are
retained. These short probes establish workflow/delivery, not optimal tuning or
visual convergence. A stalled private probe WebSocket reported a keepalive timeout
while held without consuming frames; the actions and publication assertions passed.

Evidence: `recorded-sih-v21-unit-ci.log`, `recorded-sih-v21-integration-ci.log`,
`recorded-sih-v21-contracts.log`, `recorded-sih-v21-schema.log`,
`recorded-sih-v21-api-check.log`, `recorded-sih-v21-switch.log`, and the validation
profile's `logs/recorded-sih-publish-result.json` / `logs/traces/` under the same
baseline cache. Preserve v20 evidence; use a fresh v21 profile for retesting.
Raw independent AI review is retained separately in
`custom-pixeagle/reviews/recorded-sih-replay-raw.md` in the QGC integration worktree.

Remaining shutdown debt: a failed completed teardown is cached and does not yet
provide a cleanup retry in the same episode. It stays fail-closed; this repair
does not reopen target admission after a failed Stop or claim that debt resolved.
