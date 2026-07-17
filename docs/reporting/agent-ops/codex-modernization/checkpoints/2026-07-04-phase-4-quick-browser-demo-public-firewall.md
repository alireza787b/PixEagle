# 2026-07-04 Phase 4 Quick Browser Demo Public Firewall Follow-Up

## Phase / Slice

- Phase 4 setup/bootstrap UX and controlled browser demo handoff
- Issues: PXE-0068 partial; PXE-0074 in progress
- Scope: close the gap found during user testing of the temporary public-IP
  browser demo and make the beginner setup path report or handle the same class
  of dependency.

## Trigger

The browser demo worked from the VPS itself but the user reported that
`http://204.168.181.45:3040/` kept loading from their system. Local listener
checks showed dashboard and backend were bound to `0.0.0.0`, but UFW did not
yet allow the new demo ports from public clients.

## Runtime Fix Applied On VPS

- Added temporary UFW rules for the public demo:
  - `3040/tcp` dashboard
  - `5077/tcp` backend API/media
- External check-host probes then returned HTTP 200 for:
  - `http://204.168.181.45:3040/`
  - `http://204.168.181.45:5077/api/v1/auth/session`
- The current demo credential was not rotated after the user asked to keep the
  password stable for this session.

Security boundary: this VPS state is a temporary plain-HTTP public-IP demo.
Credentials cross the network without TLS. It is not production remote access,
not QGC receiver evidence, not PX4/SITL/HIL evidence, and not field or
real-aircraft evidence.

## Repo Changes

- Added `scripts/setup/quick-browser-demo.sh`.
  - Detects or accepts the PixEagle browser host.
  - Applies the `demo_lan_browser` profile.
  - Writes the generated password to a private handoff file instead of relying
    on terminal output.
  - Handles active UFW for private LAN/private-overlay demos when it can infer a
    trusted CIDR.
  - Requires explicit `ALLOW_PUBLIC_HTTP_DEMO=1` for public HTTP.
  - Starts the minimal browser demo by default with `scripts/run.sh --no-attach
    -m -k`, intentionally skipping MAVSDK Server and MAVLink2REST.
- Added `make quick-browser-demo`.
- Extended `scripts/setup/apply-setup-profile.py`.
  - `demo_lan_browser` can now write a `0600` credential handoff JSON.
  - Public HTTP demo use remains rejected by default.
  - `--allow-public-http-demo` is an explicit override for temporary VPS bench
    testing and emits a warning.
- Updated README and setup-profile docs so beginners have a clear quick path and
  the public-IP exception is not confused with production readiness.
- Added setup-profile regression coverage for handoff-file generation, default
  public-IP rejection, explicit public override, and quick-wrapper dry-run.

## Validation

```bash
bash -n scripts/setup/quick-browser-demo.sh scripts/run.sh scripts/components/main.sh
.venv/bin/python -m py_compile scripts/setup/apply-setup-profile.py
PYTHONPATH=src .venv/bin/pytest tests/test_setup_profiles.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q
bash scripts/check_schema.sh
```

Results:

- shell syntax/import checks passed
- setup-profile tests passed: 136 tests
- docs infrastructure consistency passed: 23 tests
- route inventory and parameter reload gate passed: 50 tests
- schema check passed and schema is current

## Remaining Work

- Stop and remove temporary public HTTP/UFW exposure after user testing.
- Rotate or delete demo credentials when the current public test session ends.
- Investigate WebRTC fallback observed by the user.
- Redesign and verify mobile/tablet/desktop Settings UI.
- Redesign and verify Tracker Data and Follower Data pages with operator-focused
  precision, grouping, and noise reduction.
- Continue PXE-0074 clean setup walkthrough lanes before tag/release.

