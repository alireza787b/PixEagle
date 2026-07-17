# 2026-07-04 Phase 4 Demo LAN Browser VPS Handoff

## Phase / Slice

- Phase 4 controlled user VPS/browser handoff
- Issues: PXE-0068 partial; PXE-0074 in progress
- Scope: prepare the super-quick beginner HTTP/IP browser demo on the VPS using
  the documented `demo_lan_browser` profile over the private-overlay interface.

This is a minimal UI/API demo. It intentionally skips MAVSDK Server and
MAVLink2REST at runtime and does not claim tracker/follower closed-loop,
PX4/SITL/HIL, QGroundControl playback, field behavior, deployment hardening, or
real-aircraft success.

## Access Posture

- Dashboard URL for the controlled test: `http://100.82.207.49:3040`
- Backend/API URL for browser calls: `http://100.82.207.49:5077`
- Network boundary: `100.82.207.49` is the VPS private-overlay address on
  `wt0`, not the public `eth0` address.
- Profile: `demo_lan_browser`
- Auth mode: `browser_session`
- Runtime command: `bash scripts/run.sh --no-attach -m -k`
- Skips:
  - `-m`: no MAVLink2REST
  - `-k`: no MAVSDK Server

The generated demo password is not recorded in this checkpoint. It was captured
only in the owner-readable local handoff file:

```text
/home/alireza/PIXEAGLE_DEMO_BROWSER_HANDOFF_PRIVATE.txt
```

That file is outside the repository and mode `0600`.

## Files And Local State

Local runtime files created for the demo:

- `configs/config.yaml` - gitignored local profile config, mode `0600`
- `/home/alireza/.config/pixeagle/secrets/demo-browser-users.json` -
  owner-readable hashed browser-session user file, mode `0600`
- `/home/alireza/PIXEAGLE_DEMO_BROWSER_HANDOFF_PRIVATE.txt` - owner-readable
  plaintext handoff file for this demo only, mode `0600`

No plaintext password was committed or copied into reporting artifacts.

## Commands And Results

Host network discovery:

```bash
hostname -I
ip -brief address
ip route
```

Relevant addresses:

- public `eth0`: `204.168.181.45`
- private overlay `wt0`: `100.82.207.49`

The public address was not used for this HTTP demo.

Profile application:

```bash
install -d -m 0700 /home/alireza/.config/pixeagle/secrets
umask 077
make demo-lan-browser-profile \
  LAN_HOST=100.82.207.49 \
  SETUP_PROFILE_ARGS="--session-user-file /home/alireza/.config/pixeagle/secrets/demo-browser-users.json" \
  > /home/alireza/PIXEAGLE_DEMO_BROWSER_HANDOFF_PRIVATE.txt
chmod 600 /home/alireza/PIXEAGLE_DEMO_BROWSER_HANDOFF_PRIVATE.txt
```

Generated config summary, sanitized:

```text
API_EXPOSURE_MODE=trusted_lan_legacy
HTTP_STREAM_HOST=0.0.0.0
HTTP_STREAM_PORT=5077
API_AUTH_MODE=browser_session
API_ALLOWED_HOSTS=100.82.207.49
API_CORS_ALLOWED_ORIGINS=http://127.0.0.1:3040,http://localhost:3040,http://127.0.0.1:5077,http://localhost:5077,http://100.82.207.49:3040,http://100.82.207.49:5077
API_SESSION_COOKIE_SECURE=False
API_SESSION_USER_FILE=/home/alireza/.config/pixeagle/secrets/demo-browser-users.json
```

First startup attempt found a real launcher/runtime-environment blocker:

- `scripts/run.sh` hardcoded `venv` and failed because this workspace had only
  `.venv`.
- `scripts/components/main.sh` also assumed `venv`.
- The active `.venv` had `opencv-python-headless`, not OpenCV contrib, so CSRT
  startup failed with `module 'cv2' has no attribute 'TrackerCSRT_Params'`.

Fixes applied before final startup:

- `scripts/run.sh` now resolves `.venv/bin/python` first, then
  `venv/bin/python`, matching the current Makefile fallback behavior.
- `scripts/components/main.sh` resolves the same interpreter and validates the
  explicit interpreter path.
- Added a setup-profile regression guard for runtime launcher `.venv`/`venv`
  fallback behavior.
- Repaired the local active `.venv` for this VPS demo by replacing
  `opencv-python-headless` with `opencv-contrib-python-headless>=4.10.0,<5`.

OpenCV repair verification:

```text
cv2 version: 4.13.0
TrackerCSRT_Params: True
TrackerCSRT_create: True
TrackerKCF_create: True
```

Final startup:

```bash
bash scripts/run.sh --no-attach -m -k
```

Result:

- backend ready on `0.0.0.0:5077`
- dashboard ready on `0.0.0.0:3040`
- tmux session `pixeagle` running with `MainApp` and `Dashboard`

Expected Core-profile warnings in the MainApp pane:

- dlib not installed
- PyTorch/Ultralytics/lap not installed, so AI/SmartTracker is disabled
- MAVLink2REST unavailable because it was intentionally skipped
- no accepted video/tracker/follower behavior is claimed

## Smoke Evidence

Dashboard static response:

```bash
curl -fsSI -m 5 http://100.82.207.49:3040/
```

Result: `HTTP/1.1 200 OK`.

Unauthenticated protected API response:

```bash
curl -m 5 -H 'Origin: http://100.82.207.49:3040' \
  http://100.82.207.49:5077/api/v1/streams/media-health
```

Result: `401 authentication_required`, as expected.

Authenticated API smoke, using the generated private handoff file without
printing the password:

```text
login_status 200
login_authenticated True
login_role operator
session_status 200
session_authenticated True
session_auth_mode browser_session
runtime_status_code 200
runtime_mode idle
media_status_code 200
media_status idle
media_exposure_mode trusted_lan_legacy
media_bind_host 0.0.0.0
```

Headless browser smoke:

```text
dashboard_status 200
page_title PixEagle Dashboard
current_url http://100.82.207.49:3040/dashboard
auth_gate_visible false
```

## Validation

Run before finalizing this checkpoint:

```bash
bash -n scripts/run.sh scripts/components/main.sh
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_setup_profiles.py::test_runtime_launchers_support_dotvenv_and_venv_fallbacks \
  tests/test_setup_profiles.py::test_run_script_binds_dashboard_to_lan_for_browser_session_profile -q
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_setup_profiles.py::test_demo_lan_browser_profile_accepts_lan_and_private_overlay_addresses \
  tests/test_setup_profiles.py::test_run_script_binds_dashboard_to_lan_for_browser_session_profile -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider \
  tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short
bash scripts/check_schema.sh
git diff --check
```

Results:

- shell syntax passed
- focused setup-profile/runtime launcher tests passed: 11 tests
- docs local-link gate passed: 1 test
- minimum backend/API route inventory plus parameters gate passed: 50 tests
- schema check passed and schema is current
- whitespace diff check passed
- reporting credential leak scan passed for the updated modernization docs

## Current Running State

At checkpoint time, the `pixeagle` tmux session is intentionally left running
for user testing.

Expected user test path:

1. Connect from a device that can reach the same private overlay.
2. Open `http://100.82.207.49:3040`.
3. Use the username/password in
   `/home/alireza/PIXEAGLE_DEMO_BROWSER_HANDOFF_PRIVATE.txt`.
4. Confirm dashboard login and basic page navigation.

Stop command after testing:

```bash
make stop
```

## Claim Boundary

This checkpoint proves only the quick HTTP/IP browser login and typed API smoke
over the private overlay on this VPS.

It does not prove:

- public internet HTTP access;
- production HTTPS/WSS remote access;
- durable service installation;
- firewall hardening;
- MAVSDK Server runtime behavior;
- MAVLink2REST runtime behavior;
- MavlinkAnywhere routing;
- tracker/follower closed-loop behavior;
- PX4/SITL/HIL;
- QGroundControl media playback;
- field behavior;
- real-aircraft behavior.

## Next Slice

After the user confirms browser access, update the report with user-observed
result and either:

- continue with production remote HTTPS/WSS evidence if public access is needed;
- continue dashboard/API UX cleanup and remaining typed API migration if the
  quick demo is accepted;
- or stop the tmux session and rotate/delete the demo handoff credentials if
  the demo is no longer needed.
