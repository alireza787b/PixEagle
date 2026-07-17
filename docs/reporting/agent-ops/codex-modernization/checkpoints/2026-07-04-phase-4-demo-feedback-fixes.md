# 2026-07-04 Phase 4 Demo Feedback Fixes

## Phase / Slice

- Phase 4 public browser demo feedback closure
- Issue: PXE-0077
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Scope: close the user-observed defects after the public HTTP/IP demo retest.

## Summary

The second public-demo retest found four user-visible defects:

- tracker switching from the UI could fail with
  `ACTION_TRACKER_SWITCH_INVALID`;
- Tracker/Follower polling indicators flickered between success and yellow
  while a later poll was in flight;
- Settings showed `VideoSource.VIDEO_SOURCE_TYPE` as a free-form value instead
  of a selectable source-type list;
- manual WebRTC on the public HTTP/IP demo could sit in a waiting state instead
  of explaining that the path is not supported for this quick-demo exposure.

This slice fixed those defects and one related Settings safety blocker found by
independent frontend review: enum/boolean changes now respect Manual save mode
instead of persisting immediately.

## Changes

- `GET /api/v1/tracking/catalog` now keeps `ui_trackers[].name` as the canonical
  action token, for example `CSRTTracker`, while display text lives in
  `display_name`.
- Dashboard tracker selection now submits the canonical catalog key to
  `POST /api/v1/actions/tracker-switch`; unavailable trackers are disabled
  with operator-visible reasons.
- Tracker/Follower polling no longer resets the visible polling status to idle
  at the start of each refresh, so a healthy state does not flicker yellow while
  the next request is pending.
- `VideoSource.VIDEO_SOURCE_TYPE` now has generated schema options for:
  `VIDEO_FILE`, `USB_CAMERA`, `RTSP_OPENCV`, `RTSP_STREAM`, `UDP_STREAM`,
  `HTTP_STREAM`, `CSI_CAMERA`, and `CUSTOM_GSTREAMER`.
- The Settings section editor now respects Manual save mode for enum/custom
  enum, boolean, safety object, follower object, array, and object editors.
- Manual WebRTC on public non-local HTTP now stops before signaling and shows:
  `WebRTC direct video is disabled for public HTTP/IP demos. Use Auto/WebSocket
  for this quick demo, or serve PixEagle through HTTPS with a reviewed ICE/TURN
  path before enabling WebRTC.`
- API docs now clarify that tracker catalog `name` is the switch-action token
  and `display_name` is the UI label.

## Files Changed

- `src/classes/api_v1_snapshots.py`
- `scripts/generate_schema.py`
- `configs/config_schema.yaml`
- `tests/unit/test_generate_schema.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `dashboard/src/components/TrackerSelector.js`
- `dashboard/src/components/TrackerSelector.test.js`
- `dashboard/src/components/VideoStream.js`
- `dashboard/src/components/VideoStream.test.js`
- `dashboard/src/components/config/ParameterDetailDialog.js`
- `dashboard/src/components/config/SectionEditor.js`
- `dashboard/src/components/config/SectionEditor.test.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/pages/TrackerPage.js`
- `dashboard/src/pages/TrackerPage.test.js`
- `dashboard/src/pages/FollowerPage.js`
- `dashboard/src/pages/FollowerPage.test.js`
- `docs/core-app/03-api/README.md`

Evidence artifacts:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-demo-feedback-fixes/live-feed-webrtc-public-http-mobile.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-demo-feedback-fixes/settings-video-source-mobile.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-demo-feedback-fixes/tracker-status-mobile.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-04-demo-feedback-fixes/follower-status-mobile.png`

## Validation

Passed:

```bash
PYTHONPATH=src .venv/bin/pytest tests/unit/test_generate_schema.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/unit/test_generate_schema.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/test_docs_infrastructure_consistency.py -q
.venv/bin/python -m py_compile src/classes/api_v1_snapshots.py scripts/generate_schema.py
CI=true npm test -- --watchAll=false src/components/config/SectionEditor.test.js src/components/VideoStream.test.js src/pages/TrackerPage.test.js src/pages/FollowerPage.test.js src/hooks/useTrackerSchema.test.js src/components/TrackerSelector.test.js
npm run build
git diff --check
```

Observed results:

- backend/schema focused gate: 142 tests passed;
- schema check: generated schema up to date;
- broader backend/docs gate: 215 tests passed;
- focused dashboard gate: 6 suites passed, 47 tests passed;
- production dashboard build compiled successfully as `main.f93b865e.js`;
- whitespace diff check passed.

Live public demo smoke against `http://204.168.181.45:3040` and backend
`http://204.168.181.45:5077` passed:

- browser-session login succeeded without printing the password;
- typed tracker catalog emitted canonical names:
  `CSRTTracker`, `KCFKalmanTracker`, `GimbalTracker`, `DlibTracker`;
- dry-run tracker-switch validation accepted each emitted catalog name;
- live config schema exposed all eight `VideoSource.VIDEO_SOURCE_TYPE` options;
- Settings mobile opened the video-source dropdown with friendly source labels;
- Tracker and Follower pages showed operator status and had no mobile
  horizontal overflow;
- manual WebRTC on public HTTP showed the reviewed guidance and did not remain
  in a waiting state.

## Independent Review Closure

Backend/schema review found stale API docs, missing catalog-to-action
integration coverage, and missing direct schema-override coverage. All were
fixed before final validation.

Frontend review found the Manual save blocker, missing render-level WebRTC
guard coverage, and missing polling-status tests. All were fixed before final
validation.

## Claim Boundary

This slice proves only public-demo browser/API behavior listed above. It does
not prove PX4, SITL, HIL, MAVSDK Server, MAVLink2REST routing, MavlinkAnywhere
routing, QGC playback, field operation, deployment hardening, or real-aircraft
behavior.

The current public HTTP demo is still a temporary bench path. It sends browser
credentials over HTTP and must be stopped and rotated/deleted after this user
test session.

## Risks And Open Questions

- The temporary public HTTP credential remains intentionally stable for the
  current user session. It still needs cleanup once testing is complete.
- Public HTTP Auto streaming intentionally uses WebSocket JPEG. Production
  remote WebRTC still needs HTTPS/WSS plus reviewed ICE/TURN/firewall evidence.
- The dashboard still uses CRA/react-scripts; PXE-0021 remains open.
- Broader typed tracker configuration mutation design remains part of PXE-0008.

## Next Planned Slice

Recommended next order:

1. Have the user retest the public demo with the same current credential.
2. If accepted, stop the temporary public demo and rotate/delete the credential
   plus temporary public UFW rules.
3. Continue PXE-0074 clean setup/update walkthrough from a fresh path, including
   beginner quick-demo and senior-dev override/update lanes.
4. Continue production remote HTTPS/WSS target evidence under PXE-0064/PXE-0068
   when the target proxy/firewall/TLS plan is selected.
5. Continue PXE-0008 API cleanup or PXE-0021 dashboard toolchain migration
   based on maintainer priority.
