# QGC slice 3b addendum — terminal Smart loss status

Date: 2026-09-24. This addendum supersedes only the terminal Smart-loss status
behavior from the [model checkpoint](2026-09-24-qgc-native-models.md). Earlier
source manifests and archives remain unchanged.

During real-model replay, exhausted Smart tracking correctly cleared its target
and stopped publishing usable measurements, but the native status then showed
`idle`. It lost the distinction between an operator who had never selected a
target and a target whose recovery window had expired.

`SmartTracker` now retains the tracking manager's terminal loss reason across
subsequent idle frames. The native state reports `lost`, a `target_lost_<reason>`
code and `tracking_active:false`. Cancel, a new accepted selection, mode exit or
model transition clears that reason. A missed click does not clear it. The
actual detection algorithm, thresholds, loss window, prediction, reacquisition,
target geometry and follower usability are unchanged.

Three regressions run the real SmartTracker and TrackingStateManager with fake
inference, exhaust the configured recovery window, observe persistent loss, and
exercise Cancel/new displayed-frame selection/mode exit. Predicted/tentative
output remains unavailable for following and reports `acquiring` as before.

Evidence uses new `smart-loss-*` files under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-3b-2026-09-22/backend/`.
The previous `source-manifest.json` and `backend-model-sources.tar.gz` are preserved.
The combined model/target/Smart/route/security/config gate passed **260 tests**
(`smart-loss-focused.log/xml`). The final missed-click preservation assertion
also passed in all **35 native target cases** (`smart-loss-miss-final.log/xml`);
these overlap the combined run. Scoped fatal lint, generated-candidate check,
compilation and `git diff --check` passed. Exact hashes and commands are recorded
in `smart-loss-source-manifest.json`.
The broad pinned-base gimbal fixture hygiene blocker from the model checkpoint
remains; no whole-CI, real camera, gimbal or aircraft claim is added.

Read-only retention investigation found real test10/VisDrone9m measurements on
150/150 sequential frames with one target ID. That is six seconds of source
footage, not a timing guarantee or general tracker-quality qualification.
Other test clips had frequent loss. The paired native runtime/QGC check remains
the authority for operator handoff readiness; this correction explains loss
without making tracking more permissive.
