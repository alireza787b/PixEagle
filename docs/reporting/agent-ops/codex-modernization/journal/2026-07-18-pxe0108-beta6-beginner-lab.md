# PXE-0108: Beta.6 Beginner Lab And Local Follower Test

## 2026-07-18

- Resumed the interrupted release-preparation slice. The requested operator
  behavior was kept separate from live flight behavior: a video replay may
  exercise tracker-to-follower calculations only through `COMMAND_PREVIEW`.
  Enabling either diagnostic safety-bypass flag does not authorize replay in
  `PX4` mode and does not create a MAVSDK/PX4 publisher.
- Added the explicit `beginner_lab` profile and `make demo` wrapper. It selects
  the included looping video, classic tracker, active circuit breaker, local
  API/dashboard bindings, and `COMMAND_PREVIEW`; it does not start MAVSDK
  Server or MAVLink2REST. The checked-in runtime default remains `PX4`.
- Added readiness warnings and typed API fields for active safety bypasses.
  The dashboard labels the action **Follower Test**, shows the local-only
  boundary, and warns when local safety calculations are bypassed.
- A real `make demo` run first found a bootstrap defect: the comment-preserving
  ruamel emitter joined adjacent keys after `API_ALLOWED_HOSTS` changed from a
  public list to an empty list. A second fallback attempt exposed ruamel
  `ScalarInt`/`ScalarFloat` representer types. The serializer now validates its
  output and falls back to normalized builtin scalars plus deterministic safe
  YAML. The profile transition regression test reproduces both conditions.
- The repaired real beginner run used runtime ID
  `pixeagle_manual_748af2f4-11f8-496a-b183-af661b34878f`. Backend and dashboard
  reached readiness, the replay frame loop was fresh, and the dashboard/API
  ports were local-only.
- Live smoke through typed API actions:
  - enabled the explicit circuit-breaker safety bypass with an idempotent
    action;
  - started a normalized CSRT ROI;
  - started `COMMAND_PREVIEW` successfully;
  - observed 61 accepted local preview intents, including a finite
    `MCVelocityPositionFollower` intent;
  - verified `commands_sent_to_px4=false` and
    `sends_mavsdk_commands=false`;
  - stopped preview/tracking and disabled the bypass through typed actions.
- The same run produced expected tracker-loss/re-detection warnings when the
  deliberately broad smoke ROI was not a stable target. The bounded recovery
  terminated after its configured window; it did not remain stuck. This is
  runtime evidence for the existing fail-closed tracker recovery path, not a
  quality benchmark.
- The first broken `make demo` configuration and all smoke IDs remain local
  evidence only. No PX4, SIH, SITL, HIL, QGC, WebRTC ICE/TURN, Raspberry Pi,
  field, or aircraft claim is made.

## Next

Run the full clean-default suite after the serializer repair, add the beta6
checkpoint/evidence manifest, commit/push `main`, tag `v7.0.0-beta.6`, publish a
GitHub prerelease, and refresh the public lab VPS from that exact commit. Then
hand the maintainer the concise Core Ubuntu instructions before any Raspberry
Pi or PX4-in-loop acceptance.

## 2026-07-19 Release-Candidate Closure

- Replaced the 535-line root README with a concise beginner-first entry page,
  while retaining exact links and contract wording required by maintained docs
  tests. The installer remains one command, followed by an explicit readiness
  review and separate `make demo` start.
- Independent review found that the dashboard was still applying live-PX4
  replay rejection to the local Follower Test button. The UI now trusts the
  separate typed command-preview readiness contract; a real replay-shaped
  payload regression covers the distinction.
- Corrected unsafe global wording for
  `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES`. It can permit live PX4
  dispatch when safety infrastructure fails; only `COMMAND_PREVIEW` guarantees
  that no PX4/MAVSDK publisher exists.
- Added confirmed typed-action tests for each bypass with PX4 connection,
  Offboard-start, command-dispatch, and MAVSDK setter tripwires, plus typed
  live-PX4 replay rejection assertions and tracker-output dispatch.
- Made `beginner_lab` reset stale local video/tracker choices to the bundled
  default video and Core classic tracker from `config_default.yaml`.
- Returned `demo_lan_browser` to a network-only profile so its cleanup does not
  leave new follower/video mutations. Remote Follower Test setup is an explicit
  composition of `beginner_lab` and the browser profile.
- Final gates passed: affected backend/API/docs 285, setup/docs 186, dashboard
  53 suites/343 tests, schema, API inventory, lint, production build, syntax,
  diff, and deterministic `make demo` dry run. The bounded setup and safety
  reviewers both returned `GO` after their concrete findings were closed.
