# PixEagle Changelog

## Version 7.0.0-beta.13 (2026-07-20) - Profile-Driven Python Compatibility

- Replaced the global PyTorch/Python version gate with one schema-validated,
  profile-owned compatibility policy. Core, CPU, CUDA, macOS, and Jetson
  profiles now state their own Python ranges, exclusions, maintenance track,
  and evidence basis in `scripts/setup/pytorch_matrix.json`.
- Added a reusable compatibility checker for the initializer and standalone
  PyTorch installer. It validates the Python 3 language family, exact profile
  ranges, patch exclusions, and policy integrity without adding interpreter-
  specific shell branches.
- Current Linux CPU Full AI is validated on Python 3.14.4 with the reviewed
  CPU wheels (`torch 2.12.1+cpu`, `torchvision 0.27.1+cpu`). Unsupported
  accelerator profiles may fall back to the reviewed CPU profile in automatic
  mode; interactive Full setup offers Core, while unattended setup fails
  closed instead of silently changing intent.
- Repair runs reuse a valid existing PixEagle virtual environment and create
  new environments with the selected interpreter. Profiles without torchaudio
  remove stale torchaudio metadata before installation.
- Added policy, interpreter-selection, fallback, and Python 3.14 regression
  coverage plus isolated Ubuntu 26.04/Python 3.14 install evidence. This beta
  still does not claim Raspberry Pi, PX4/SIH/SITL/HIL, QGC, GStreamer target,
  production networking, field, or aircraft readiness.

## Version 7.0.0-beta.12 (2026-07-20) - Interrupted Setup Recovery

- Made fresh, repair/resume, and update/repair intent explicit in the guided
  terminal flow. Existing-checkout recovery now states exactly which operator
  data is preserved and retries invalid confirmation input; it never performs
  a hidden reset.
- Added `make repair` for current-source reconciliation without a Git update.
  The existing one-line path remains fast-forward update plus repair, while
  build/cache cleanup, config reset, and isolated clean installation retain
  separate, narrowly documented meanings.
- Replaced duplicated dashboard dependency-cache logic with one shared
  lockfile authority. A repair reuses `node_modules` only when package hashes
  match and an offline full-tree `npm ls --all` succeeds; interrupted, stale,
  missing, or invalid state falls back to strict `npm ci` with no mutable
  `npm install` fallback.
- Documented SSH/power interruption boundaries and safe rerun behavior. This
  release does not claim that host package transactions are rollback-capable,
  nor does it add a destructive full-install reset.

## Version 7.0.0-beta.11 (2026-07-20) - Interactive Bootstrap Prompt Recovery

- Fixed the documented `curl | bash` path over an interactive SSH session so
  the bootstrap makes one terminal decision and explicitly gives that terminal
  to the initializer or updater. Guided setup now waits for Core/Full and later
  choices instead of re-probing the child process and rejecting the session.
- Added a pseudo-terminal regression that feeds the bootstrap through stdin,
  selects Full at the child profile prompt, and proves that the choice reaches
  the initializer. No-terminal automation remains explicit and defaults to
  Core only through the documented bootstrap policy.
- Made profile and optional-component prompt failures visible, retry invalid
  yes/no answers, and reduced duplicate banner output while preserving concise
  step headers and animated progress for silent long-running operations.
- This prerelease repairs installer interaction only. It does not yet claim the
  maintainer's complete fresh Ubuntu rerun, Raspberry Pi, AI/model inference,
  GStreamer, PX4/SIH/SITL/HIL, QGC, production networking, field, or aircraft
  readiness.

## Version 7.0.0-beta.10 (2026-07-20) - Fresh Installer Recovery

- Fixed no-controlling-terminal detection so piped and remote bootstrap runs
  do not attempt to read an unusable `/dev/tty`; the one-line beginner path
  explicitly selects Core while direct unattended init requires a profile.
- Fixed verified nvm staging and non-terminal progress handling, then proved
  the repaired path on the official Ubuntu 26.04 image with the pinned nvm
  commit, Node.js 24 LTS, and npm 11.
- Established one Node.js contract through `.nvmrc`, setup, dashboard runtime,
  package metadata, and CI. A later Node failure no longer discards an already
  verified Python environment.
- Added a profile-aware PyTorch compatibility gate. Full AI with the checked-in
  PyTorch 2.6 matrix accepts Python 3.9-3.13 and rejects Python 3.14 before apt
  or virtual-environment mutation; Core remains independently resolved and
  validated on the host.
- Made apt execution deterministic and fail-closed, clarified Core versus Full
  product language, and consolidated explicit optional dlib, GStreamer,
  current-user shell shortcut, and standalone service choices.
- This prerelease proves installer contracts and the isolated Ubuntu 26.04
  Node recovery. It does not claim a complete fresh-host Core acceptance,
  Full AI on Python 3.14, Raspberry Pi, PX4/SIH/SITL/HIL, QGC, production TLS,
  public WebRTC, field, or aircraft validation.

## Version 7.0.0-beta.9 (2026-07-20) - Typed Retarget Evidence

- Preserved the fail-closed `target_transition` evidence returned by classic
  active target replacement through the typed tracking-start action response.
  The beta.8 runtime applied the hold correctly but its HTTP executor rebuilt
  the response without that field; the public acceptance probe caught the
  mismatch before maintainer handoff.
- Added executor-level regression coverage. Beta.9 supersedes beta.8 for
  operator testing; flight/PX4 and hardware claim boundaries are unchanged.

## Version 7.0.0-beta.8 (2026-07-20) - Safe Active Retargeting

- Added a fail-closed active-target transition: classic ROI and Smart target
  replacement invalidate the previous follower intent and activate commander
  defaults before target state changes, while keeping the Following or local
  Follower Test session active.
- Kept live PX4 tracker-implementation replacement blocked. Local
  `COMMAND_PREVIEW` may switch implementations while held at defaults and then
  requires a fresh target.
- Made the dashboard distinguish a valid all-zero command intent, hold output,
  and no accepted intent. The Follower Test/Following action label remains
  authoritative from execution mode and independent of circuit-breaker state.
- Made the explicit beginner lab profile select `mc_velocity_chase` so replay
  produces visibly changing forward/steering intents; standalone preview and
  existing deployment profiles preserve the operator-selected follower.
- Added backend, dashboard, setup-profile, and documentation regression
  coverage. This prerelease adds no PX4/SIH/SITL/HIL, vehicle-response,
  Raspberry Pi, QGC, public WebRTC, production TLS, field, or aircraft claim.

## Version 7.0.0-beta.7 (2026-07-19) - CI Portability Correction

- Fixed an undefined yaw-telemetry variable in the multicopter velocity-distance
  follower; telemetry now reports activity from the final smoothed degree-per-second
  command that is actually published in the command intent.
- Fixed Python 3.11 startup by constructing immutable authentication mapping
  defaults through dataclass factories.
- Fixed Windows staged-config ACL handling by passing the canonical path through
  an explicit environment boundary, assigning a canonical owner-only ACL, and
  verifying its owner after publication. ACL validation prefers the current
  PowerShell runtime and falls back to Windows PowerShell when needed.
- Made the Playwright browser-metadata contract hermetic so the Python-only CI job
  validates known metadata without depending on a dashboard `node_modules` tree.
- Made AI/runtime ownership, OpenCV rollback, and Offboard safety tests independent
  of repository-local virtual environments, random backup-name alphabets, and
  ignored deployment overrides, preserving clean-checkout test behavior.
- Supersedes beta.6 for tester handoff. The beginner demo behavior and safety claim
  boundary are otherwise unchanged.

## Version 7.0.0-beta.6 (2026-07-19) - Beginner Lab Follower Test

- Added `make demo` as the concise post-install beginner path. Its explicit
  `COMMAND_PREVIEW` profile uses recorded video and starts only the main app and
  dashboard; MAVSDK Server and MAVLink2REST are not started. The established
  checked-in PX4 execution default is unchanged for existing deployments.
- Renamed the operator-facing preview action to `Follower Test` while retaining
  the stable internal API action contract.
- Allowed local follower tests to run when diagnostic safety-bypass flags are
  active, with typed warnings that distinguish the local calculation bypass
  from the dangerous live safety-module failure bypass. The active circuit
  breaker remains mandatory, replay remains prohibited from autonomous
  Following, and `COMMAND_PREVIEW` has no PX4/MAVSDK publisher.
- Kept AI, dlib, GStreamer, models, QGC profiles, and service/auto-start setup as
  explicit optional capabilities rather than silent beginner-host mutations.
- Reworked the root README into a concise beginner-first project entry point
  with an explicit two-step safe demo, audience-based documentation routes,
  accurate capability language, and current repository discoverability terms.
- Kept browser exposure profiles network-only, made `beginner_lab` select the
  bundled video and Core classic tracker deterministically, and separated local
  preview readiness from live-PX4 replay rejection in the dashboard.
- This prerelease adds no PX4/SIH/SITL/HIL, vehicle-response, Raspberry Pi,
  QGC, public WebRTC, production TLS, field, or real-aircraft claim.

## Version 7.0.0-beta.5 (2026-07-18) - Follower Command Preview

- Added an explicit, default-off `COMMAND_PREVIEW` execution mode for recorded
  video. It runs the maintained tracker-to-follower calculation path and
  records bounded, schema-valid command intents locally without connecting to
  MAVSDK/PX4 or starting Offboard mode.
- Kept live autonomous Following fail closed for replay sources. Preview
  requires a fresh replay frame, usable tracker target, and active circuit
  breaker. Safety-bypass settings are disabled by default; beta6 documents the
  warning-only behavior when an operator explicitly enables one for diagnostics.
- Added a supported `follower_command_preview` setup profile, typed API claim
  boundaries, mode-specific dashboard actions/status, focused backend/frontend
  tests, and operator documentation.
- This prerelease adds no PX4/SIH/SITL/HIL, vehicle-response, Raspberry Pi,
  QGC, public WebRTC, production TLS, field, or real-aircraft claim.

## Version 7.0.0-beta.4 (2026-07-18) - Tracker Acceptance Correction

- Increased the checked-in point-click target ROI default from 5% to 8% and
  kept the dashboard fallback synchronized with the setup default.
- Replaced classic detector identity state on every manual target selection so
  retargeting cannot reuse the prior target's template or appearance baseline.
- Enforced configured, method-aware template-recovery thresholds and fail-closed
  handling for invalid/non-finite scores.
- Made exposed CSRT validation and OpenCV learning-rate settings effective,
  retired unreachable FeatureMatching/ORB/RANSAC configuration through schema
  `1.4.0`, and removed the unreachable detector prototypes.
- Added focused detector, tracker, config-migration, and dashboard regression
  coverage. This prerelease adds no Raspberry Pi, PX4/SIH/SITL/HIL, QGC,
  public WebRTC, production TLS, field, follower-response, or aircraft claim.

## Version 7.0.0-beta.3 (2026-07-17) - Pre-Ubuntu Acceptance Polish

- Increased the default point-click target region from 4% to 5% after live
  operator feedback while retaining the existing environment override.
- Added a reusable fullscreen control to Live Feed and replaced light-only
  stream-panel colors with responsive theme tokens.
- Updated browser WebRTC offer negotiation to use an explicit `recvonly` video
  transceiver. Remote public-IP ICE/TURN acceptance remains a separate gate;
  Auto continues to use WebSocket there.
- Added `make follower-contract-test` for deterministic visual/gimbal
  tracker-to-follower command-intent and stale-target checks without PX4 or
  MAVLink publication.
- Preserved replay, circuit-breaker, Offboard, authentication, and public-demo
  safety boundaries. This prerelease adds no Raspberry Pi, PX4, SIH/SITL/HIL,
  QGC, production TLS, field, follower-response, or aircraft claim.

## Version 7.0.0-beta.2 (2026-07-17) - Live Acceptance Fix

- Bounded classic-tracker confidence at the detector, smoothing, and output
  contract boundaries so floating-point cosine roundoff cannot invalidate an
  otherwise usable first tracking measurement.
- Added focused regression coverage for above-one roundoff and non-finite
  confidence values.
- Preserved the beta.1 API, configuration, dashboard, security, setup, and
  acceptance boundaries; this prerelease adds no PX4, SITL/HIL, field, QGC, or
  Raspberry Pi claim.

## Version 7.0.0-beta.1 (2026-07-17) - Modernization Acceptance Beta

This prerelease consolidates the Codex modernization work into the first
tester-facing beta. It is intentionally a major-version prerelease because the
maintained API, security, configuration, and setup contracts include breaking
changes from historical PixEagle tags.

### Highlights

- Added typed `/api/v1` state and action contracts, structured errors,
  operation identifiers, route inventory checks, and a blocked-by-default MCP
  candidate inventory.
- Added explicit API exposure profiles, browser-session and scoped bearer
  authentication, CSRF protection, durable security audit records, and
  responsive browser-user administration with host-side recovery tooling.
- Made configuration schema/default synchronization transactional and
  versioned, with explicit retirements, extension preservation, rollback, and
  coherent runtime publication.
- Hardened tracker selection, retargeting, SmartTracker click handling, target
  freshness, Offboard preflight, and PX4 command-inhibit behavior.
- Modernized the dashboard's responsive operator flows, restart visibility,
  runtime logs, streaming status, account controls, and typed API adoption.
- Added maintained setup profiles, clean-checkout handoff validation, pinned
  binary/model provenance, runtime ownership, and broad backend/dashboard CI
  coverage.

### Breaking Changes

- Retired legacy public mutation and tracker aliases after typed replacements.
- Remote access now requires an explicit exposure/authentication profile;
  checked-in defaults remain local-only.
- Registered obsolete configuration keys are removed only through the
  versioned config-sync workflow.
- The follower circuit breaker is a fail-closed PX4 command-dispatch inhibit,
  not a simulator or autonomous-following preview mode.

### Beta Boundaries

- This beta is for controlled browser/VPS and fresh-install acceptance.
- It does not claim Raspberry Pi, PX4/SIH/SITL/HIL, QGroundControl, field,
  aircraft, production TLS, or autonomous follower-response acceptance until
  those separate evidence gates pass.

## Historical Development Snapshot (2026-02-10) - Dashboard State Sync & Model Metadata UX

### 🚀 Improvements

- Hardened dashboard state synchronization for live toggles:
  - OSD toggle now continuously reconciles with backend state and refreshes on focus/visibility changes.
  - Smart mode toggle now confirms backend state after mutation instead of relying on local inversion.
  - Circuit breaker toggles now reconcile with authoritative status updates to reduce stale UI drift.
- Added active-model capability metadata for SmartTracker:
  - `GET /api/models/active-model`
  - `GET /api/models/models/{model_id}/labels` (paginated/searchable label listing)
- Extended `GET /api/models/models` response with `active_model_summary`, `active_model_source`, and schema metadata.
- Upgraded model selector UI with:
  - "Active Model Capabilities" summary chips (task, geometry, source, NCNN/custom flags, label count)
  - Click-to-open label browser dialog with search and bounded payload behavior.

### 🧪 Validation

- Added/updated unit coverage for model identifier normalization and label extraction helpers.
- Python compile checks and JS syntax checks passed on all touched files.

## Version 3.2.1 (2026-02-05) - Resilience & Version Consistency

### 🚀 Improvements

- Added degraded-mode startup: backend stays online when video source is unavailable.
- Added video resilience endpoints:
  - `GET /api/video/health`
  - `POST /api/video/reconnect`
- Prevented app shutdown on temporary or persistent frame loss.
- Added camera status and reconnect action in dashboard Settings.
- MC Velocity Chase now allows user-selected lateral guidance mode (`coordinated_turn` or `sideslip`), with fixed-camera advisory hints surfaced via schema/UI.

### 🔧 Version Consistency

- Unified API-exposed project version via central `src/classes/app_version.py`.
- FastAPI app version and frontend runtime config now use the same project version.
- Dashboard package version updated to `3.2.1`.

## Version 3.2 (2025-10-10) - Professional OSD System

### 🚀 New Features

- **Aviation-Grade OSD System** - Professional HUD layouts following DJI/ArduPilot/PX4 standards
- **TrueType Font Rendering** - High-quality PIL/Pillow text rendering (4-8x better than OpenCV)
- **Resolution-Independent Scaling** - Professional 1/20th frame height sizing formula (aviation standard)
- **Real-Time Preset Switching** - API endpoint for instant preset changes without restart
- **Three Professional Presets** - Minimal (racing), Professional (default), Full Telemetry (debug)
- **RobotoMono Font Integration** - Professional monospaced font with automatic detection

### 🔧 Improvements

- **Improved Font Discovery** - Custom fonts directory checked first with proper name normalization
- **Better Text Positioning** - 8% safe zones (aviation standard) for critical data visibility
- **Visual Hierarchy** - Critical data (altitude, battery) displayed larger with plate backgrounds
- **Smaller Attitude Indicator** - Reduced from 60% to 8% screen size for professional appearance
- **Symmetric Layout Design** - Balanced left/right data organization
- **Enhanced OSD Renderer** - Immediate reinitialization when presets change via API

### 📖 Documentation

- Removed duplicate README from fonts directory (consolidated into OSD_GUIDE.md)
- Updated main README to reference comprehensive OSD documentation
- All preset files now include aviation design principles and sizing rationale

### 🐛 Bug Fixes

- Fixed custom fonts directory not stripping `-regular` suffix from font names
- Fixed preset switching requiring app restart
- Fixed font size being too small (changed from 1/30th to 1/20th of frame height)

### 🔄 Breaking Changes

None - Fully backward compatible with PixEagle 3.1

---

## Version 3.1 (2025-10-09) - SmartTracker Enhanced

### 🚀 New Features

- **Multi-Tracker System** - Added ByteTrack, BoT-SORT, and PixEagle custom appearance-matching modes
- **Ultralytics BoT-SORT Integration** - Uses Ultralytics BoT-SORT defaults without native ReID; the former native-ReID claim was inaccurate and has been retired
- **Custom Lightweight ReID** - Offline re-identification for embedded systems and air-gapped drones
- **Configurable Feature Extraction** - HOG and histogram parameters now fully configurable
- **Performance Profiling** - Built-in profiling system for appearance model metrics
- **Explicit Capability Handling** - Runtime behavior now reflects supported tracker capabilities instead of inferring native ReID from an Ultralytics version

### 🔧 Improvements

- **Enhanced Frame Validation** - Robust error handling with minimum ROI size checks
- **Tracker-Agnostic Architecture** - TrackingStateManager works with any Ultralytics tracker
- **Better Error Messages** - Clear logging and troubleshooting information
- **Configuration Consolidation** - All tracker settings in config_default.yaml following PixEagle patterns

### 📖 Documentation

- **New: Complete SmartTracker Guide** - Comprehensive documentation for users and developers
- **Updated README** - Clear SmartTracker introduction with quick start examples
- **Performance Benchmarks** - FPS and accuracy comparisons for all tracker modes
- **Decision Guide** - Help users choose the right tracker for their scenario

### 🐛 Bug Fixes

- Fixed invalid model arguments error (only persist/verbose passed to model.track)
- Fixed attribute error in get_output() method (tracker_type vs tracker_type_str)
- Removed unused separate tracker YAML files
- Cleaned up gitignore entries

### 🔄 Breaking Changes

None - Fully backward compatible with PixEagle 3.0

---

## Version 3.0 (2025-01-XX) - Smart Tracker Introduction

- Initial SmartTracker implementation with detection model integration
- GPU/CPU support with automatic fallback
- Web dashboard revamp
- Schema-aware architecture
- Service management system

---

## Version 2.0 (2024-XX-XX)

- Classic tracker improvements (CSRT, KCF)
- MAVLink integration enhancements
- Follow mode implementations

---

## Version 1.0 (Initial Release)

- Basic tracking and following functionality
- PX4 integration
- Web dashboard
