# 2026-07-03 Phase 4 VPS Browser Test Readiness Estimate

## Scope

This checkpoint answers the current handoff question: what remains before the
first browser test on the VPS. It is a planning and readiness checkpoint only.
No service was started, no remote port was exposed, no credential was generated,
and no PX4, SITL, HIL, field, QGC playback, or real-aircraft success is claimed.

Repository state reviewed before this estimate:

- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Starting commit: `d9452afb` (`PXE-0008 retire tracker schema capabilities aliases`)
- Worktree state before edits: clean
- Current docs reviewed: `README.md`, `docs/README.md`,
  `docs/setup/setup-profiles.md`,
  `docs/setup/production-remote-reverse-proxy.md`,
  `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`,
  `docs/reporting/agent-ops/codex-modernization/issue-register.md`, and the
  2026-06-25 setup/bootstrap clean-walkthrough preflight.

## Current Readiness

The codebase is close enough to prepare a controlled VPS/browser smoke, but not
yet ready to call production remote access complete.

Already in place:

- Dashboard build/test gates and Phase 0 backend/schema/API inventory gates
  were green at the previous code checkpoint.
- First-party dashboard tracker diagnostics now use typed `/api/v1` tracker
  contracts without public legacy tracker diagnostic aliases.
- Setup profiles exist for:
  - local development (`local_dev`);
  - QGC field video over GStreamer UDP/RTP (`field_qgc_video`);
  - guarded QGC direct HTTPS/WSS media (`qgc_direct_media`);
  - beginner lab/private-overlay browser dashboard (`demo_lan_browser`);
  - production browser access behind an operator-managed HTTPS/WSS reverse
    proxy (`production_remote`).
- Browser-session auth, CSRF policy, exact Host/Origin checks, session
  revocation for media streams, and local production-remote browser evidence
  harnesses are implemented and documented.
- Init/bootstrap cleanup has already addressed the known local preflight
  issues around macOS scope, `venv` fallback, missing `make`, manual dashboard
  dotenv conversion, dependency split, foreign port ownership, missing `nc`,
  and summary precision.

Still not proven on the current VPS:

- A clean temporary checkout following public docs end to end.
- Actual startup on this VPS after choosing the local-only tunnel posture or
  applying the selected setup profile.
- Browser login/session/media-health smoke from the user's browser.
- Public TLS/reverse proxy/firewall evidence for production remote access.
- Target-host adversarial checks for wrong Host, wrong Origin, missing CSRF,
  expired session, unauthenticated media, and viewer/action separation.

## First Test Lanes

### Lane A: Controlled VPS Browser Smoke

Recommended first user test.

Use when the browser reaches the VPS through an SSH tunnel, private overlay
network, trusted private address, or other operator-approved lab boundary. This
is the fastest safe path because it avoids public internet exposure and does
not require a production certificate before the first UI review.

Candidate access patterns:

- SSH tunnel to local-only dashboard/backend ports.
- Private overlay or trusted private network plus `demo_lan_browser`, using
  the VPS private/overlay address as `LAN_HOST`.
- Local browser on the VPS over loopback if a desktop browser path exists.

Minimum proof before giving the user a URL:

- Clean temp-directory walkthrough succeeds using public docs.
- Access mode is recorded explicitly:
  - SSH tunnel or same-host loopback uses local-only/local-compat access unless
    a credentialed profile is deliberately selected.
  - Private overlay or trusted LAN browser access uses `demo_lan_browser`, and
    profile generation succeeds without leaking generated passwords into
    reports.
- `make run` or the documented dev launcher starts backend/dashboard with the
  intended binds.
- Browser loads the dashboard.
- For `demo_lan_browser`, login succeeds with generated browser-session
  credentials and logout or expired session denies API/media.
- For SSH/local-only access, local-only API/media behavior is verified without
  exposing backend port `5077` beyond the tunnel or loopback boundary.
- Basic typed reads work: `/api/v1/runtime/status`,
  `/api/v1/tracking/catalog`, `/api/v1/streams/media-health`, and the dashboard
  widgets that consume them.
- Report contains exact commands, commit, access posture/profile, bind
  addresses, sanitized logs, screenshots when available, and failures.

Estimate before Lane A is ready for user test:

- Best case: 2 focused slices.
- Conservative case: 3 focused slices if the VPS needs package/browser
  dependency cleanup, port conflict resolution, or Playwright/browser
  installation.

The next slice should be PXE-0074 clean temp-directory walkthrough plus a
controlled browser-readiness dry run. The following slice can start the actual
controlled smoke and provide the URL/credential handoff if the first slice does
not reveal blockers.

### Lane B: Public HTTPS/WSS VPS Browser Test

Use when the browser reaches PixEagle through a public domain or any untrusted
network path. This is the production-shaped path and must use
`production_remote` or an equivalent reviewed boundary.

Minimum proof before public browser handoff:

- `production_remote` profile generated with owner-only credential files.
- HTTPS/WSS reverse proxy configured for the exact public host/path.
- Dashboard `3040` and backend `5077` remain loopback-only.
- Firewall exposes only the reviewed TLS listener to the intended client CIDR.
- Browser-trusted certificate or reviewed trust anchor is installed.
- Credential handoff is captured outside the repository and then the plaintext
  handoff file is deleted.
- Adversarial auth/media checks pass on the target host.
- Security audit records show expected allowed/denied events without secrets.

Estimate after Lane A:

- Best case: 2 additional focused slices if a domain, TLS certificate, reverse
  proxy, and firewall policy are already ready.
- Conservative case: 3 to 5 additional focused slices if we must create or
  adjust the proxy/TLS/firewall/service evidence and rerun adversarial checks.

### Lane C: Tester/Funder Handoff

Use only after the browser path is proven and stale docs/configs/scripts are
cleared by the final walkthrough.

Minimum proof:

- PXE-0074 final clean temp-directory walkthrough completed from public docs.
- PXE-0068/PXE-0064 target deployment evidence accepted for the chosen access
  lane.
- Stale-doc and route/schema/dashboard gates remain green.
- No secrets are present in retained reports or uploaded evidence.
- Any PX4/SITL claim has separate logs, exact commands, versions, configs, and
  artifacts. Browser readiness alone does not prove follower, PX4, SITL, or
  aircraft behavior.

Estimate after Lane A:

- Browser/operator handoff without PX4/SITL claims: 4 to 7 focused slices.
- Any PX4/SITL-backed handoff adds the relevant validation-ladder slices,
  especially official Gazebo visual proof or SIH/PX4 scenario evidence.

## Remaining Work Before First Browser Test

Must do before giving the user a test URL:

1. Run a clean temp-directory walkthrough from public docs on this VPS or a
   disposable directory.
2. Choose the access lane explicitly:
   - SSH/private overlay/lab HTTP for first controlled review; or
   - public HTTPS/WSS production remote if the first test must be public.
3. Generate profile and credentials with redaction discipline when the selected
   lane uses `demo_lan_browser` or `production_remote`; record local-only
   tunnel posture when no credential-generating profile is used.
4. Start PixEagle with the selected profile and verify binds/ports.
5. Run focused backend/dashboard smoke checks.
6. Capture a checkpoint report with evidence paths, sanitized outputs, and
   clear claim boundaries.
7. Hand off the URL and credentials outside the repository.

Not required for the first browser UI test:

- PX4, MAVSDK Server, MAVLink2REST, MavlinkAnywhere, Gazebo, X-Plane, QGC PR
  playback, real camera feed, tracker/follower runtime success, or aircraft.
- These remain important for product readiness, but they should not block the
  first controlled dashboard/browser review unless the user wants to test
  flight-adjacent behavior in the same session.

## Risks And Watch Items

- VPS may lack Node/browser/Playwright dependencies for automated browser proof.
- Existing local `configs/config.yaml` or running services could mask clean
  checkout behavior if the walkthrough is not isolated.
- Port `3040` or `5077` may be occupied by non-PixEagle processes; the launcher
  should refuse to kill foreign listeners and report the conflict.
- Public HTTPS requires domain/certificate/firewall decisions that are outside
  the repository and must be evidenced, not assumed.
- `demo_lan_browser` is intentionally HTTP lab/private-overlay convenience. It
  is acceptable for a controlled first review but not for production remote
  access on an untrusted network.

## Recommended Next Slice

Proceed with PXE-0074 controlled browser-readiness walkthrough:

1. Clone or copy the current branch to a clean temporary directory on the VPS.
2. Follow the public README/setup docs exactly through core init, setup-profile
   dry runs, schema check, route-inventory gate, and dashboard build.
3. Apply the selected first-test posture or profile, preferably controlled
   SSH/local-only tunnel or private overlay/lab access unless the user
   explicitly chooses public HTTPS now.
4. Start services, verify bind addresses, and run a browser smoke.
5. Produce a checkpoint report and copy it to `/home/alireza` before any user
   handoff.

If this slice passes without setup blockers, the user can likely receive the
first controlled VPS/browser test link in the next slice after that. If it
finds setup or host blockers, fix those before exposing the dashboard.

## Validation

This is a docs/reporting checkpoint. Validation scope is documentation hygiene
and independent estimate review only.

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q`
  passed.
- `git diff --check` passed.
- Independent read-only review found no commit-blocking issues. It found one
  low-severity clarity issue around SSH-tunneled local-only access versus
  generated browser-session profile proof; this checkpoint now separates those
  proof paths.
