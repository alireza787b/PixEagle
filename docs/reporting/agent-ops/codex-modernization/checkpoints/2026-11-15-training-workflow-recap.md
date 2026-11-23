# Simulator workflow recap — 15 November 2026

## Decision

The operator accepts the latest simulated **guidance and application workflow**.
The camera's rendered rotations/stabilization still look wrong in transition/FW;
that visual fidelity is an open issue, not an accepted physical camera replica.
The phase is closed only at that bounded workflow scope. It is not an all-mode,
all-airframe, hardware or release qualification.

Use the [training guide and matrix](../../../../followers/05-development/ubuntu-training-platform.md)
for the current entry point. It replaces the older planning text without
rewriting failed run evidence. Protocol/provider adaptation and mounting remain
in their existing domain guides; no duplicate flight-control framework is added.

## Latest operator evidence

Run: `reports/sitl/follower-consolidation-20261111/training-attached-gimbal-operator-r2`.
Backend source `52b05f36258e9b5a82a4da7a812b61a00403f823`;
QGC `ef52e369e2318d2d0a47cbbb611cb6edb77ec388`;
QGC binary SHA-256 `82b0a04d8a73412c09589910f4339a7c471768a3a86c56f438daf07a44c42288`.
Firmware ELF `5f42a1abb96894bdc0a429db06edced09dda7a8116c53301297bcbcab3181c37`.
The normal native runtime bundle is `native-release-repair-20261114-r1`.

The archived `acceptance-review/summary.json` records:

- 669 attempted publications, all successful: 358 MC body-velocity and 311 native
  FW navigation submissions. Five non-attempted trace records are not failures
  and are not counted as successful publications.
- No native error reply or backend traceback. All audited follow, camera and
  target actions have success outcomes; validation records are counted separately.
- Same-source retargeting uses the existing bounded recovery/restore path.
  Final following state is inactive; operator Stop has `confirmed_hold`.
- 6,518 retained camera observations at review time, no pose gaps or actuation
  errors; camera/body separation stays at most 1.372 m. This supports physical
  attachment, not image-roll/stabilization fidelity.

The stack was closed after observing inactive following; logs/receipts and
screenshots were retained. Unrelated services were untouched. The earlier
headless `training-attached-gimbal-integration-r6/review` separately contains
415 confirmed FW guidance samples, 46 active-status polls, three confirmed
operator Stops and actual PX4 response plots. None of those results qualify the
real FL-30's travel, timing or torque.

## Repeatable launcher

`tools/launch_training.py` is a terminal front end, using `scripts/banner.txt`,
a private machine-path recipe and the existing `run_gazebo_training.py` owner.
It adds no publication, aircraft control, authentication or cleanup path.
Beginner entries are native MC, native FW (Cessna with forward camera) and standard
quadplane. The two tailsitter combinations remain explicit advanced profiles,
hidden from the beginner menu/list. Agents can list them with `--headless --list`
and use `--headless --profile ...`. An expert can explicitly request their GUI.

Standalone native-FW qualification is not established by a quadplane/tailsitter
run. The new `rc-cessna-mono-camera-courtyard-v1` descriptor pins the existing
4003 airframe and complete stock Cessna resources, plus one fixed-camera wrapper.
It reuses the verified firmware and native adapter without rebuilding either.
The declared physical mount generates calibration through the same camera helper.
The runner admits declared conventional FW through its existing native owner,
while pure MC remains on MAVSDK even when a shared recipe includes adapter paths.
No follower, axis transform or native-control algorithm is copied. The menu never arms or takes off. Every run uses a fresh directory;
ambiguous duplicate arguments or ownership overrides reject before launch.
Beginner recipes explicitly disable target-directed altitude guidance. The
canonical qualification runner preserves its previous altitude-on default;
advanced recipes choose explicitly. Public and private hardware files are unchanged.

A Desktop launcher and local dependency recipe were prepared on the owner's
Ubuntu workstation. No machine-specific paths or credentials are added to the
public sample. Current images in `docs/assets/training` are unmodified actual
captures/plots; the visibly imperfect QGC roll is intentionally documented.

## Gates and remaining work

Menu/launcher, Phase 0, schema and changed-domain checks are renewed in this
slice. The previous [attached-gimbal checkpoint](2026-11-14-tailsitter-stop-and-gimbal-staging.md)
retains its larger unit, video, timing and kinematics evidence. No guidance,
QGC, firmware or adapter controller change belongs to this recap slice.

Before an all-airframe release claim: qualify standalone native-FW GUI behavior;
repeat fixed-nose final Stop/restart; resolve the separate failed FW altitude-hold
bound; qualify target packaging/platform binaries; and perform the cooled real
camera protocol/axis/selection/Stop/reconnect/timing bench. Pure MC external-gimbal
current full-GUI qualification is distinct from VTOL's MC phase/component cases.
Remaining direct-rate/other follower gates stay in the SIH inventory.

Do not flash firmware, enable experimental policies, merge/tag/publish or claim
hardware flight acceptance from this checkpoint. The customized QGC remains
unpublished; no public QGC PR or release is created.

## Cleanup

The owner authorized obsolete generated-build cleanup. Thirteen old compile-output
directories (about 6.0 GiB) were removed after their build/test metadata were
archived and verified. Old Docker build cache reclaimed another 743.9 MB.
`reports/sitl/follower-consolidation-20261111/cleanup-20261115` retains the archive,
manifest and deletion receipt. Approximately 11 GB became available. Current
firmware/runtime images, QGC/Qt, SD handover packages and accepted/failed flight
evidence were retained. No broad image/container or log purge was performed.

## Standalone FW ground checkpoint

`training-native-fw-preflight-r1` observed autostart 4003, `MAV_TYPE=1`, native
adapter/socket readiness, verified independent telemetry association, a current
960×720 selectable camera frame and inactive/disarmed following. Camera pixels
show the forward runway unobstructed by the airframe. No arm, takeoff, target or
following action was issued. The preflight stack was closed before the fresh
operator run. This is ground readiness, not airborne pursuit acceptance.

Focused menu/launcher/resource tests: **264 passed**. Phase 0 API/parameter tests:
**74 passed**. Schema check passes using the prepared virtual environment; the
initial system-Python attempt lacked `ruamel` and made no schema change. Critical
Python lint and whitespace checks pass. Dashboard, QGC, firmware and native
adapter binaries are unchanged in this slice.
