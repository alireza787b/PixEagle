# 2026-07-04 WebRTC, Bootstrap, And Runtime Logging Plan

## Context

After the public quick-demo retest, the user asked three follow-up questions:

- why manual WebRTC is disabled on the public HTTP/IP demo even though WebRTC
  appeared to work before;
- what the bootstrap/init sequence asks a beginner or developer to select;
- whether PixEagle should adopt a unified logging feature similar to
  `mavsdk_drone_show`.

Two independent read-only reviewers inspected PixEagle and the local
`/home/alireza/mavsdk_drone_show` reference repository. No files were edited by
the reviewers.

## WebRTC Policy

The current public demo is plain HTTP on a public IP address:

- dashboard: `http://204.168.181.45:3040`;
- backend/API/media: `http://204.168.181.45:5077`.

WebRTC needs two different things to work:

- signaling, which is the WebSocket exchange of SDP/ICE messages;
- an ICE media path, which may be direct UDP, server-reflexive candidates
  through STUN, or relay through TURN.

The old behavior treated browser `RTCPeerConnection` support and signaling as
enough. That can work on localhost, same-host testing, or some LAN/NAT cases,
and host-local validation did connect. It is not proof that a remote browser on
the public internet can receive media. Public remote WebRTC also needs reviewed
TLS/WSS or an equivalent trust boundary, ICE/TURN/firewall evidence, and
operator-visible media-state diagnostics.

For the beginner quick-demo path, WebSocket JPEG is the right default:

- it uses one authenticated TCP/WebSocket path through the backend;
- it avoids opening random UDP firewall ranges;
- it behaves predictably on phones/tablets/PCs behind NAT;
- it matches the temporary public HTTP warning that credentials cross the
  network without TLS.

PixEagle can support remote WebRTC later, but not as the default public HTTP
demo. The correct future path is a production/lab profile with HTTPS/WSS,
configured TURN/STUN, bounded firewall policy, explicit tests, and media-health
evidence. A deliberately named advanced lab override may be considered later,
but it should not be hidden behind Auto or the beginner quick-demo flow.

## Bootstrap / Setup Selection Story

Current beginner path:

1. The user starts from `README.md` or `docs/INSTALLATION.md`.
2. They run either `curl ... install.sh | bash` or `git clone && make init`.
3. `install.sh` clones or updates the repo, then runs `scripts/init.sh`.
4. `scripts/init.sh` runs a 9-step setup:
   - system checks;
   - install profile selection;
   - apt package prerequisites;
   - Python virtualenv;
   - Python dependencies;
   - Node/nvm;
   - dashboard dependencies;
   - runtime config/dashboard env;
   - MAVSDK Server and MAVLink2REST binary setup.
5. The normal runtime path is `make run`.
6. The browser-only demo path is `make quick-browser-demo LAN_HOST=<ip>`.

Current optional choices:

- Install profile:
  - Core: no AI/torch, lighter setup;
  - Full: AI/torch/Ultralytics path.
- PyTorch:
  - Full profile offers automated platform-aware PyTorch setup;
  - default is yes on Jetson/NVIDIA, no elsewhere.
- OpenCV/GStreamer:
  - pip OpenCV/OpenCV contrib installs automatically;
  - if an existing custom OpenCV with GStreamer is detected, init asks before
    overwriting it;
  - custom OpenCV+GStreamer build remains a manual step.
- dlib:
  - optional manual install through `scripts/setup/install-dlib.sh`.
- MAVSDK Server and MAVLink2REST:
  - init prompts to download manifest-pinned binaries and verifies checksums.
- Service setup:
  - skipped by normal `make init`;
  - opt in with `PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init`;
  - prompts default to no.
- Quick demo:
  - `make quick-browser-demo` applies `demo_lan_browser`, creates browser
    credentials, may open UFW, and starts backend/dashboard only;
  - public HTTP requires explicit `ALLOW_PUBLIC_HTTP_DEMO=1`;
  - dry-run/config-only paths exist through environment variables.

Setup gaps to fix under PXE-0078:

- `requirements.txt` is still monolithic even though init has Core/Full logic.
- The optional dlib comment in `requirements.txt` points to an old script path.
- The setup selection matrix is scattered across README, install docs, Makefile,
  and shell scripts.
- Quick demo should print a concise preflight/change/cleanup summary before
  starting.
- `install.sh` update behavior and `make sync` update behavior use different
  mental models and need either alignment or explicit explanation.
- `make run` fallback behavior for missing sidecar binaries should be
  consistent and clearly explained.

## Runtime Logging Assessment

PixEagle currently has:

- security/audit JSONL at `logs/security_audit.jsonl`;
- tmux pane output for backend and dashboard during `scripts/run.sh`;
- SITL and production-remote evidence logs in `reports/`;
- service logs through systemd only when service mode is installed.

PixEagle does not yet have:

- one durable runtime session ID per launch;
- component-scoped runtime JSONL logs;
- retention/cleanup policy for runtime logs;
- typed `/api/v1/logs/*` contracts;
- dashboard Logs page;
- frontend error report ingestion;
- downloadable demo evidence bundle.

The live public demo illustrates the gap. Backend warnings can be inspected
through tmux and security/audit lines through `logs/security_audit.jsonl`, but
there is no clean API/UI path for “show last 200 warnings/errors for this
PixEagle run.”

## MDS Logging Lessons

Borrow from `mavsdk_drone_show`:

- JSONL session format;
- safe session path resolution;
- count/size retention cleanup;
- component registry;
- console formatter plus JSONL file formatter;
- live watcher/SSE design;
- Logs page with operator/developer filters and export.

Do not copy directly:

- unversioned `/api/logs/*`; PixEagle should use `/api/v1/logs/*`;
- drone-fleet proxy semantics and drone-id centric UI;
- ULog erase/download flows until PixEagle has separate disarmed checks,
  confirmation, scopes, and PX4 evidence policy;
- background log pulling;
- mixing security audit with runtime logs.

## Proposed PXE-0079 Architecture

1. Runtime session foundation:
   - add `src/classes/runtime_logging/`;
   - initialize before `FlowController()` in `src/main.py`;
   - write `logs/runtime/sessions/<run_id>/manifest.json` and component JSONL.
2. Launcher capture:
   - `scripts/run.sh` creates/exports `PIXEAGLE_RUN_ID`;
   - tmux panes pipe MainApp, Dashboard, MAVSDK Server, and MAVLink2REST output
     to bounded component logs.
3. Typed API:
   - add `/api/v1/logs/status`;
   - add `/api/v1/logs/sources`;
   - add `/api/v1/logs/sessions`;
   - add `/api/v1/logs/sessions/{session_id}`;
   - add `/api/v1/logs/stream`;
   - add `/api/v1/logs/export`;
   - add frontend error/report route.
4. Dashboard:
   - add Logs page;
   - Operations mode defaults to warnings/errors and key lifecycle events;
   - Developer mode allows filters by component, level, source, session;
   - export current demo evidence bundle.
5. Safety/security:
   - redact secrets, cookies, CSRF, bearer tokens, generated passwords, and raw
     media;
   - keep security audit separate and fail-closed;
   - logs support evidence but do not prove PX4/SITL/HIL/field behavior.

## Planned Next Slices

1. PXE-0078: setup/bootstrap UX consolidation.
2. PXE-0079a: runtime logging foundation and launcher session capture.
3. PXE-0079b: typed logs API and route/security inventory.
4. PXE-0079c: dashboard Logs page and frontend error reporting.
5. PXE-0079d: evidence bundle export.
6. PXE-0074 continuation: clean setup/update walkthrough after setup docs and
   logging foundation are aligned.

## Claim Boundary

This audit is planning and local code review. No PX4/SITL/HIL/QGC/field or
real-aircraft behavior is claimed.
