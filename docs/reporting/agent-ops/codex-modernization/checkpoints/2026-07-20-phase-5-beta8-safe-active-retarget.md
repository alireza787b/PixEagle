# Phase 5 Checkpoint: Beta.8/9 Safe Active Retarget

**Date:** 2026-07-20
**Slice:** PXE-0109
**Status:** Beta.9 published and public acceptance passed; maintainer VPS/fresh-Ubuntu acceptance pending

## Operator Feedback And Decision

The beta7 runtime did generate follower intents. Its selected
`mc_velocity_position` profile is a position-hold follower: forward and lateral
velocity are always zero, altitude control was disabled, and a centered target
made yaw zero. The resulting all-zero intent was valid but ambiguous in the UI.

PixEagle now represents three states explicitly:

- **Intent recorded** means a fresh schema-valid intent exists, including an
  intentional all-zero intent;
- **Hold output** means the previous intent was invalidated and commander
  defaults are active;
- **Waiting for intent** means no accepted current intent exists.

The explicit `beginner_lab` profile selects `mc_velocity_chase` so a recorded
video test normally shows changing forward and steering fields. This choice is
limited to that profile. It does not mutate the checked-in PX4 default, the
standalone command-preview profile, or existing operator deployments.

## Active-Transition Contract

Classic ROI and Smart target replacement may occur while Following or Follower
Test remains active. The controller serializes the transition with existing
follower/tracker lifecycle ownership, invalidates the follower's previous
intent, activates commander schema defaults, verifies hold status when the
commander exposes it, and only then mutates target state. Missing or failed
transition contracts reject the operation.

Target replacement is not tracker-implementation replacement:

- live `PX4` Following permits a fresh target with the current implementation,
  but still blocks changing the tracker implementation;
- `COMMAND_PREVIEW` may change the implementation while the local commander is
  held at defaults, then requires a new target before intent generation resumes.

The action label is derived exclusively from typed execution mode. Circuit
breaker state remains an independent permission gate and cannot change a PX4
action into a local test or vice versa.

## Files Changed

- `src/classes/app_controller.py`
- `src/classes/follower.py`
- `src/classes/followers/base_follower.py`
- `scripts/setup/apply-setup-profile.py`
- `dashboard/src/components/FollowerStatusCard.js`
- `dashboard/src/components/TrackerSelector.js`
- `dashboard/src/pages/DashboardPage.js`
- focused backend, setup, and dashboard regression tests
- follower-preview/tracker integration docs, changelog, version metadata, issue
  register, and this reporting record

## Validation

- Focused active-retarget/setup backend gate: **340 passed**.
- Affected API/docs gate: **127 passed**.
- Minimum Phase 0 gate: **477 passed**, with one existing Starlette/httpx
  deprecation warning.
- Dashboard focused gate: **3 suites / 31 tests passed**.
- Dashboard complete gate: **53 suites / 348 tests passed**.
- Dashboard ESLint and production build passed; build artifact was
  `main.496c1d64.js`.
- Maintained non-hardware/non-SITL suite: **3,371 passed, 47 expected skips,
  1 deliberate deselection**, with the same existing deprecation warning.
- Schema and API tool-candidate inventories are current.
- Python compile, selected fatal Python lint, shell syntax, and
  `git diff --check` passed.
- The first beta.8 public probe confirmed that the hold executed and target
  replacement succeeded, but exposed that the classic HTTP executor rebuilt
  the result without its `target_transition` field. Beta.9 preserves that
  evidence and adds executor-level coverage. The post-fix gates passed **397
  behavior tests**, **85 API/inventory/Phase 0 tests**, **4 version-consistency
  tests**, schema validation, compile, and diff hygiene.

Two delegated bounded reviewers exhausted their separate usage quota without
returning a verdict. No independent-review result is claimed. The local bounded
safety/API/UI/setup review found no release-blocking issue, and the slice is not
being expanded into unrelated follower internals or logging refactors.

## Claim Boundaries

These gates prove deterministic local contracts and dashboard behavior. They do
not prove PX4 command response, MAVLink transport, SIH/SITL/HIL, QGC playback,
Raspberry Pi compatibility, optional AI/GStreamer target installation, public
WebRTC ICE/TURN, production TLS, flight behavior, or real-aircraft safety.

## Release And Acceptance Gates

1. Commit the candidate and run the maintained clean-checkout Ubuntu handoff
   harness against that exact commit. **Done:** candidate
   `54271ceecddc06cb17765a3f8c575d1c006e629c` passed all 26 checks from a
   temporary clean checkout, including fresh dashboard install/test/build.
2. Push `main`, create annotated tag `v7.0.0-beta.8`, and publish a GitHub
   prerelease without rewriting history. **Done, then superseded:** the public
   probe found the typed-response omission above. The published tag is retained
   as immutable history; beta.9 is the tester candidate.
3. Publish the narrow beta.9 correction after its focused/API/version gates,
   then restart the public bench from that exact release. **Done:** commit
   `81894cde14a478033c761904bf6056ade015cbb8`, annotated tag, pushed `main`,
   and GitHub prerelease are aligned.
4. Preserve ignored configuration and the existing owner credential, apply the
   explicit beginner lab profile, and restart the public browser-only VPS bench
   from the released source. **Done:** both credential files remained
   byte-identical and the effective public profile was verified before and
   after run `pixeagle_manual_70f6c1fe-289f-4a48-9c7d-09b59afc131f`.
5. Run unauthenticated dashboard/MJPEG/WebSocket probes and an authenticated,
   reversible command-preview probe that observes a finite chase intent,
   verifies `commands_sent_to_px4=false`, replaces a target while the session
   stays active, and stops cleanly. **Done.**
6. Give the maintainer the concise VPS and fresh-Ubuntu acceptance handoff. Only
   after Ubuntu acceptance proceed to physical Raspberry Pi Core/Full/model
   evidence. QGC remains a later slice as previously agreed.

## Evidence

Clean candidate:
`54271ceecddc06cb17765a3f8c575d1c006e629c`

Clean-checkout handoff:
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0109-54271cee-exact-clean-handoff/manifest.json`

The harness reported **26/26 passed**, `source_clean_at_start=true`, and clean
initial/final temporary-checkout state. The updater dry-run was deliberately
omitted because the beta7 public runtime remained active and update ownership
requires a stopped runtime. The isolated checkout was deleted after completion.

Beta.9 release:
https://github.com/alireza787b/PixEagle/releases/tag/v7.0.0-beta.9

Beta.8 release head:
`385ae4a017de45cfbce4877e747a836ead87d345`

First beta.8 public run:
`pixeagle_manual_f80299ac-a72a-4c70-baf9-bf70a5038d73`

The anonymous/authenticated identity and media probe passed dashboard, MJPEG,
WebSocket JPEG, browser-session admin auth, version, and exact commit checks.
The reversible functional probe then confirmed finite nonzero
`mc_velocity_chase` preview intent with `commands_sent_to_px4=false` and a
successful active retarget. Runtime logs proved the fail-closed hold executed,
but the typed action response omitted its transition evidence. Cleanup left
Following inactive. This is the reason beta.8 is not the maintainer handoff.

Accepted beta.9 release head:
`81894cde14a478033c761904bf6056ade015cbb8`

Accepted public run:
`pixeagle_manual_70f6c1fe-289f-4a48-9c7d-09b59afc131f`

The identity/media probe passed anonymous session isolation, admin login,
version/commit identity, runtime/media health, MJPEG JPEG, and WebSocket JPEG.
The reversible functional probe passed initial Classic target selection,
Follower Test startup, finite nonzero `mc_velocity_chase` intent, explicit
`COMMAND_PREVIEW`, `commands_sent_to_px4=false`, verified hold-before-retarget,
continued Following, fresh post-retarget intent, and inactive cleanup. Effective
config retained video replay, CSRT, chase profile, command preview, active
command inhibit, both diagnostic bypasses false, browser-session auth, and the
explicit anonymous-media lab exception.

Structured runtime logs contain 204 INFO, 5 WARNING, one intentional lab
exposure CRITICAL, and zero ERROR entries in the backend; dashboard has 57 INFO
and no warning/error entries. PX4/MAVLink disconnected status is expected for
this browser-only run and is not represented as vehicle evidence.
