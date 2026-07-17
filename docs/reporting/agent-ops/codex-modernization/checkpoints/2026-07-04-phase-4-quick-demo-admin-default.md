# 2026-07-04 Phase 4 Quick Demo Admin Default

## Phase / Slice

- Phase 4 setup/bootstrap UX follow-up
- Issues: PXE-0078, PXE-0079
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

The quick browser demo now creates the first generated demo user as `admin` by
default. This matches the maintainer/public-demo workflow: the first bench user
should be able to inspect Settings and the new runtime Logs page immediately.
The production remote profile remains `operator` by default.

## Changes

- `demo_lan_browser` default `--demo-role` changed from `operator` to `admin`.
- `scripts/setup/quick-browser-demo.sh` now defaults `SESSION_ROLE`/`DEMO_ROLE`
  to `admin`, prints the chosen role before applying changes, and prints the
  less-privileged override path.
- README, installation, and setup-profile docs now state that quick-demo admin
  is the default and show `SESSION_ROLE=operator` or `SESSION_ROLE=viewer` for a
  downgraded demo user.
- Setup-profile tests now assert the admin default for:
  - generated hashed demo user files;
  - generated one-time demo credential handoff files;
  - quick-wrapper dry-run output.
- The active VPS demo credential file was updated from `operator` to `admin`
  without rotating or printing the password. The password hash was preserved and
  the backend/dashboard demo was restarted.

## Validation

Passed:

```bash
bash -n scripts/setup/quick-browser-demo.sh

PYTHONPATH=src .venv/bin/pytest \
  tests/test_setup_profiles.py::test_demo_lan_browser_profile_generates_hashed_session_credentials \
  tests/test_setup_profiles.py::test_demo_lan_browser_profile_can_write_private_credential_handoff \
  tests/test_setup_profiles.py::test_production_remote_profile_generates_loopback_reverse_proxy_config \
  tests/test_setup_profiles.py::test_make_quick_browser_demo_wrapper_supports_dry_run_handoff \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -q

bash scripts/check_schema.sh
git diff --check

PYTHONPATH=src .venv/bin/pytest \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_setup_profiles.py \
  -q
```

Observed results:

- focused setup/API/config gate: 54 tests passed;
- schema check reported up to date;
- broader docs/setup suite: 160 tests passed;
- public demo dashboard responded HTTP 200 after restart;
- unauthenticated `/api/v1/logs/status` still returned 401 as expected;
- stored live demo user metadata is now `role=admin`, enabled, with a password
  hash present.

## Evidence Boundary

No password was printed, rotated, or committed. The one-time handoff file is not
present on the VPS, so authenticated curl verification of `debug:read` was not
run without operator-provided credentials. The backend restart invalidated
process-local sessions; the browser should re-login with the same current
password and then show the Logs navigation because `admin` maps to `debug:read`.

This checkpoint does not claim production remote, WebRTC public remote, PX4,
SITL, HIL, QGC receiver, or field readiness.

## Next Planned Slice

- Continue PXE-0079 follow-ups: sidecar/dashboard stdout capture, frontend
  error ingestion, live log stream/export/evidence bundle, and setup walkthrough
  evidence.
- Continue PXE-0074/PXE-0068 clean setup/update walkthrough after the current
  public demo testing is complete.
