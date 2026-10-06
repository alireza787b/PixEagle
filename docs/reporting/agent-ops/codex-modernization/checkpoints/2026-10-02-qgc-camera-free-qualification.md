# QGC camera-free qualification and release preparation

Camera unavailable; continue independent software/SIH work. No physical camera,
aircraft, shared desktop or unrelated container was used. Production follower
gains/defaults were not changed in this pass. Integration work remains
uncommitted/unpublished and the clean main checkout is preserved.

## Evidence

- Reused four unchanged v13 Chase/Vector horizontal/vertical SIH cases:
  2,210 successful publications, actual simulated yaw/altitude response,
  retarget/loss restoration and confirmed budget-expiry Hold.
- Added all five normal multicopter profiles through production dispatch and
  actual quad SIH: 843 successful publications, zero failures and confirmed
  Stop. Normalized image inputs replace camera angles. Direction/response scope
  is recorded per case, not claimed as physical tracker or gain qualification.
- Actual airplane SIH was attempted for fixed-wing, but altitude readiness
  failed before Offboard; zero follower commands were sent. Four real-PID
  deterministic FW direction/bounds tests pass separately. Combined focused
  follower tests: 63 passes; launcher isolation/snapshot tests: three passes.
- Network/load software gate: 64 tests pass, including ten real authenticated
  HTTP cases, bounded JPEG retention and independent publisher tests. Stop
  dispatch 0.69/0.82 ms under blocked capture/inference; expiry 369.9 ms; 20 Hz
  publication maximum gaps 50.3/50.4 ms. No lease extension or production fix.
- Linux custom Release build and isolated boot pass. Generic native package
  identity fix and CMake CTest pass stock/custom staging and coexistence. Fetching
  Git tags resolves missing version metadata without changing pinned HEAD.
  Actual DEB dependency inspection is blocked by host `libxcb-cursor.so.0`;
  canonical setup requires `libxcb-cursor-dev`. No installer was published.

See paired [normal SIH report](https://github.com/alireza787b/qgroundcontrol/blob/0d8bdf06bc7c3d2b68465f9bce46c021640aa647/custom-pixeagle/validation/NORMAL-SIH-EVIDENCE.md),
[combined checkpoint](https://github.com/alireza787b/qgroundcontrol/blob/0d8bdf06bc7c3d2b68465f9bce46c021640aa647/custom-pixeagle/SLICE-4B-4D.md),
[release readiness](https://github.com/alireza787b/qgroundcontrol/blob/0d8bdf06bc7c3d2b68465f9bce46c021640aa647/custom-pixeagle/RELEASE-READINESS.md)
and [software link report](../evidence/2026-10-02-4b4d-software-link-qualification.md).
Those records link immutable drivers, source/config hashes, raw publications,
observed poses and failed attempts. Earlier full v13 gates remain recorded
separately; no whole-backend rerun is implied by adding test/docs-only files.

## Newly exposed normal-mode blockers

MC Attitude Rate obeyed rate limits but reached actual pitch 43.0455° against
configured 35°. Its limited dispatch success is not attitude-envelope acceptance.
Repair measured-angle protection with independent fixtures/SIH before flight use.
Body angular rates must not be mistaken for guaranteed Euler-heading changes.

Fixed-wing requires a qualified launch/readiness fixture and fresh typed
airspeed; current production fallback uses ground speed and cannot qualify
wind/stall safety. Keep these visible rather than altering gains or test aircraft
to obtain a passing result.

## Configuration and remaining gates

[Camera workflows](../../../../trackers/06-integration/camera-workflows.md) now
documents RTSP-only local tracking, local tracking with optional camera controls,
camera-owned tracking, and external-application ownership. Provider enablement
requires a process restart; tracking-engine changes use the existing canonical
apply-and-save transaction. Compatible follower selection stays explicit.
No duplicated QGC installation geometry or new configuration store was added.

Fresh v13 camera acceptance, physical horizontal mounting, shared bitrate/QGC
transport, Pi sustained load/thermal behavior and physical camera/process-loss
motor stopping remain open. Then complete Linux/Windows/Android release gates,
coherent reviewed commits/PRs, and actual Pi/router/PX4/camera inventory plus
command-blocked onboard ground acceptance. No real-flight approval is claimed.

## Follow-up boundary repair

The findings above describe the original matrix, not current unguarded behavior.
[Boundary repair](2026-10-02-follower-boundary-repair.md) records fresh defaults,
measured-attitude protection and actual receipt/progress freshness, once-owned
Stop, strict fixed-wing airspeed admission and the repaired startup-only fixture.
Combined gates now pass 3,358 Unit/195 Integration and nine focused QGC tests.
The short guarded MC SIH passes; prolonged pitch 35.171° remains a blocker.
A final Vector/Vertical regression passes 550 publications; sensorless fixed-wing
policy, physical stopping, platform and onboard gates remain open.
