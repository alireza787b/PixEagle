# Phase 5 VPS Basic AI Readiness

Date: 2026-07-17

Issue: PXE-0074

Source baseline: `21c32662979854738a495fe1d7629c2e6e43b4e1`

Implementation commit: `6c65c35e6399aaa6c6498c9e193a95115cd7c993`

Clean-handoff candidate: `566953605fb9b17d9a81be36cd529189f6bfaff1`

Status: automated, authenticated VPS, and exact clean-checkout gates complete;
maintainer browser and physical Raspberry Pi acceptance pending

## Scope

This slice installed the maintained Full CPU dependency profile and one
separately digest-verified YOLO model on the existing x86_64 public lab VPS. It
then exercised SmartTracker, the model inventory, authenticated media, and the
dashboard without starting Following or connecting PX4.

The slice also converted concrete installation findings into narrow setup and
documentation fixes. It did not redesign the installer, add an implicit model
download, enable public-HTTP WebRTC, or claim target-board or flight readiness.

## Installation Evidence

The live runtime was stopped before dependency mutation so the installers could
obtain the exclusive virtual-environment lock. The maintained transactional
setup paths then completed with:

- profile: `linux_cpu`
- torch: `2.6.0+cpu`
- torchvision: `0.21.0+cpu`
- torchaudio: `2.6.0+cpu`
- ultralytics: `8.4.95`
- lap: `0.5.13`
- OpenCV provider preserved as `opencv-contrib-python-headless 4.13.0.92`
- NCNN, dlib, and custom OpenCV/GStreamer intentionally omitted

Commands:

```bash
PIP_NO_CACHE_DIR=1 bash scripts/setup/setup-pytorch.sh --mode auto --non-interactive \
  --report-json /home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/pytorch-vps-2026-07-17.json
PIP_NO_CACHE_DIR=1 bash scripts/setup/install-ai-deps.sh \
  --report-json /home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/ai-dependencies-vps-2026-07-17.json
.venv/bin/python add_model.py \
  --model-name yolo26n.pt \
  --sha256 9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef \
  --trust-model
bash scripts/setup/check-ai-runtime.sh --require-smart-tracker \
  --report-json /home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/ai-readiness-with-yolo26n-vps-2026-07-17.json
```

The 5,544,453-byte `yolo26n.pt` artifact came from the official
[Ultralytics assets `v8.4.0` release](https://github.com/ultralytics/assets/releases/tag/v8.4.0).
Its observed SHA-256 exactly matched the publisher release digest:

`9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef`

The model store records `expected_sha256` provenance and keeps the model,
registry, and metadata owner-only. Model licensing remains a deployment review;
this technical bench does not choose or grant an Ultralytics deployment license.

## Live Runtime Evidence

The maintained launcher restarted Core services with run ID
`pixeagle_manual_657c6717-0f28-4234-bdc5-d49135fb6cfa`:

- dashboard: `http://204.168.181.45:3040/`
- backend: `http://204.168.181.45:5077`
- components: MainApp and Dashboard healthy
- public transport expectation: Auto/WebSocket; WebRTC remains unavailable for
  this public HTTP/IP profile
- sidecars intentionally absent: MAVSDK Server and MAVLink2REST

An authenticated public-Origin probe passed session, runtime, typed tracking,
following, model inventory, active-model, media-health, and MJPEG requests. The
active model was YOLO26N with task `detect`, 80 labels, backend `cpu_torch`, and
effective device `cpu`. The configured GPU attempt failed because this host has
a CPU-only PyTorch build, and the explicit CPU fallback succeeded. SmartTracker
had visible output, no target was selected, and Following remained off.

The focused browser path passed sign-in, Models navigation, YOLO26N runtime
details, Dashboard navigation, Smart AI mode, Following-off state, and desktop
horizontal-overflow checks with no browser console or page errors.

Owner-only local evidence:

- `/home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/pytorch-vps-2026-07-17.json`
- `/home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/ai-dependencies-vps-2026-07-17.json`
- `/home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/ai-readiness-with-yolo26n-vps-2026-07-17.json`
- `/home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/vps-models-desktop-2026-07-17.png`
- `/home/alireza/PIXEAGLE_SETUP_EVIDENCE_PRIVATE/vps-dashboard-desktop-2026-07-17.png`
- `logs/runtime/pixeagle_manual_657c6717-0f28-4234-bdc5-d49135fb6cfa/`

## Setup Lessons Applied

- `evidence_path.py` now reports rejected paths as one concise operator error
  instead of a Python traceback while preserving fail-closed behavior.
- Active PixEagle processes hold a shared venv lock; dependency mutation must
  stop the matching manual, standalone-service, or platform-managed runtime
  rather than deleting lock files. This VPS used the manual `make stop` path.
- Evidence publication validates every ancestor. The docs now use a dedicated
  owner-controlled directory instead of assuming an XDG state tree is private.
- The AI dependency transaction now avoids retaining pip download cache, matching
  the PyTorch installer and reducing persistent disk use on companion computers.
- Generic model-download guidance requires HTTPS/TLS, a private umask, a
  separately obtained publisher digest, guarded temporary cleanup, and the
  model manager's bounded atomic `--source-file` ingestion transaction. An
  existing different model is never overwritten.
- Dashboard guidance identifies `Tracker Mode -> Smart (AI)` as the activation
  path and keeps Following off for a model-only bench.
- The maintainer walkthrough imports the installed Core dependencies while
  operating on a temporary clean checkout. Active guidance now invokes it with
  `.venv/bin/python`; a failed bare `/usr/bin/python3` attempt is retained as
  evidence rather than hidden or mislabeled as a product failure.

The original ignored config and its owner-only pre-install backup remained
byte-identical with SHA-256
`71186c5fabb17611fc553da31b54ef21b235a42317bdadbb99d66eabf8576854`.
The existing browser user store and private handoff retained their prior hashes
and mode `0600`; no credential was rotated or added to repository evidence.

## Validation

- combined setup/model/documentation gate: `407 passed`, `1 skipped`
- adjacent model ingestion/provenance/API gate: `119 passed`
- final Ubuntu-compatible model/docs regression: `63 passed`
- mandatory API/parameters tests: `72 passed`
- schema check: `40` sections, `540` parameters, current
- Python compile, Bash syntax, and ShellCheck: passed
- `git diff --check`: passed
- live authenticated API/media probe: passed
- focused authenticated browser operator path: passed
- exact `56695360` clean-checkout handoff: `26/26` commands passed
- clean-checkout dashboard: `49/49` suites and `297/297` tests passed; production
  build passed
- source worktree: clean at harness start; temporary checkout: clean before and
  after the planned commands

The accepted clean-checkout manifest is
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-17-pxe0074-56695360-ai-handoff/manifest.json`.
The stopped-runtime updater was intentionally skipped because the public tester
runtime remained active; no lifecycle guard was weakened to force that check.

Two bounded independent reviews initially rejected the candidate for incomplete
manual/service/platform lifecycle guidance and a shell copy that could overwrite
an existing registered model before validation. The corrected candidate uses one
documented lifecycle matrix and the existing atomic model-manager transaction.
A final compatibility pass also removed a curl option unavailable on Ubuntu
22.04 while retaining fail-fast temporary cleanup. Both final reviewers returned
`GO` with no blocker or high-risk defect.

## Claim Boundary

This checkpoint proves a basic x86_64 Full CPU install, one trusted local model,
first inference, authenticated dashboard/model visibility, SmartTracker output,
and browser media on the named VPS run. It does not prove target selection
quality, loss/re-detection behavior, follower commands, MAVSDK/MAVLink2REST,
PX4, SIH, SITL, HIL, NCNN, dlib, custom OpenCV/GStreamer, QGC, public WebRTC,
Raspberry Pi execution, production TLS, field operation, or real-aircraft
behavior.

## Next Gate

1. Maintainer performs the bounded public VPS browser/model test using the
   unchanged private credential.
2. If accepted, refresh the owner-only Raspberry Pi handoff to the final pushed
   candidate and execute Core first on a clean 64-bit board.
3. Only after Core/browser/restart acceptance, install Full, register a separately
   trusted model, and capture target inference evidence.
4. Keep optional NCNN/GStreamer, PX4, QGC, production deployment, tag, and release
   in their separate gates.
