# Phase 4 Checkpoint: QGC Host Authority Versus Client-IP Clarification

Date: 2026-07-10 UTC
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

Clarify the PixEagle/QGC media security model after QGC successfully displayed
the actual PixEagle HTTP MJPEG and WebSocket JPEG feeds in the unsafe
anonymous-media bench mode.

This slice does not change runtime code. It resolves operator-facing ambiguity
between:

- request Host authority allowlisting;
- browser CORS origin allowlisting;
- selected GCS/source-IP firewall or reverse-proxy policy;
- PixEagle authentication and the explicit unsafe media-only exception.

## Changes

- Clarified `docs/CONFIGURATION.md` that `Streaming.API_ALLOWED_HOSTS` is not a
  selected GCS/client-IP list and does not bypass auth.
- Clarified `README.md` onboarding text for beginner browser demos and network
  requirements.
- Clarified `docs/apis/api-exposure-boundary.md` and
  `docs/apis/api-security-policy.md` that Host/CORS are exposure controls, not
  caller authorization.
- Clarified `docs/setup/setup-profiles.md` that `LAN_HOST`/`PUBLIC_HOST` are
  PixEagle URL/proxy authorities, not GCS source addresses.
- Updated `scripts/setup/apply-setup-profile.py` output so `qgc_direct_media`
  and `unsafe_demo_lan_media_only` summaries carry the same Host-authority
  warning.
- Clarified `docs/INSTALLATION.md` and
  `docs/drone-interface/04-infrastructure/port-configuration.md` that selected
  GCS devices should be scoped through firewall/VPN/proxy source-IP rules, and
  changed broad sample MAVLink firewall rules to source-scoped examples.
- Clarified `docs/video/04-streaming/remote-media-security.md` and
  `docs/video/04-streaming/qgc-http-websocket-source-plan.md` that anonymous
  PixEagle QGC media is only the explicit `unsafe_demo_lan_media_only` lane,
  while authenticated direct QGC media still needs Bearer/Origin/TLS support.
- Added docs-regression assertions to
  `tests/test_docs_infrastructure_consistency.py`.
- Added setup-profile output assertions to `tests/test_setup_profiles.py`.
- Added negative Host-vs-client-IP tests to
  `tests/unit/core_app/test_api_exposure_policy.py` and
  `tests/unit/core_app/test_api_auth_runtime.py`.

## Validation

Passed:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_docs_infrastructure_consistency.py tests/test_setup_profiles.py tests/unit/core_app/test_api_exposure_policy.py tests/unit/core_app/test_api_auth_runtime.py
python3 -m py_compile scripts/setup/apply-setup-profile.py
bash scripts/check_schema.sh
git diff --check
```

## Evidence

- QGC actual-feed playback evidence remains under prior PXE-0089 bench notes
  and tester confirmation.
- This checkpoint covers documentation correctness only.

## Risks And Boundaries

- No PixEagle runtime behavior was changed.
- No QGC branch changes were made in this slice.
- No production HTTPS/WSS proxy, firewall, QGC authenticated playback, PX4/SITL,
  HIL, field, or real-aircraft success is claimed.
- If a future product requirement asks PixEagle itself to allow anonymous media
  only from selected source CIDRs, that must be a separate guarded design with
  explicit source-CIDR config and proxy-header trust rules. It should not be
  hidden inside `API_ALLOWED_HOSTS`.

## Next

- Rebase the QGroundControl PR branch against current upstream `master`.
- Keep the QGC feature generic and draft until QGC code/tests/docs and target
  receiver evidence are clean.
- Update the QGC PR comment only after the branch state and validation evidence
  are current.
