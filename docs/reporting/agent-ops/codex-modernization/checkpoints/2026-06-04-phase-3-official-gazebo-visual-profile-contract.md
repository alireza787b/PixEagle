# Phase 3 Checkpoint: Official Gazebo Visual Profile Contract

Date: 2026-06-04  
Phase/slice: Phase 3, PXE-0040 partial  
Status: done for checked-in official Gazebo visual profile contract; runtime
official Gazebo evidence remains open  
Claim boundary: profile, wrapper, CI, docs, and artifact validation contract
only. This is not a Docker/PX4/Gazebo runtime pass, tracker/follower visual
SITL pass, HIL, field, deployment, service-install, or real-aircraft
validation.

## Summary

PixEagle now has an opt-in L4 official PX4 Gazebo visual validation profile
that is side-effect-free by default and uses the proven UDP/GStreamer receiver
path for RTP/H.264 video on port `5600`.

The first implementation pass exposed review blockers: the plan named visual
artifacts but did not import or content-validate them, the scenario objectives
overstated what GET-only config probes prove, and the PX4 image/container
digest policy was too weak. Those blockers were fixed before closing this
sub-slice.

The profile contract now rejects weak visual evidence. A runtime run remains
incomplete unless it has:

- generated RTP/UDP receiver proof manifest with executed `passed` status;
- strict Gazebo RTP/H.264 receiver pipeline text;
- decoded Gazebo frame hashes with at least two valid distinct frames;
- parseable tracker/follower command trace JSONL with timing evidence;
- parseable Offboard publish trace JSONL with timing evidence;
- PX4 container metadata with container inspection and image repo digest;
- structured MavlinkAnywhere route/profile data, PixEagle config snapshots,
  PX4 params/logs/ULog/tlog manifests, and no field/HIL claims.

## Files Changed

- `tools/sitl_plans/gazebo_visual_validation.json`
  - Added official L4 Gazebo visual plan using
    `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01`,
    `HEADLESS=1`, `gz_x500_mono_cam`, host networking, MAVSDK/offboard UDP
    `14540`, GCS UDP `14550`, and Gazebo camera video UDP `5600`.
  - Added `require_container_metadata=true` and
    `require_image_repo_digest=true`.
  - Reworded visual scenarios so acceptance is tied to artifact-content checks,
    not GET-only config probes.
- `tools/run_sitl_validation_suite.py`
  - Added fixed Gazebo visual evidence paths and plan validation for required
    visual artifacts.
  - Added visual artifact import CLI options.
  - Added content checks for receiver proof, H.264 RTP pipeline ordering,
    frame hashes, trace JSONL, container inspection, repo digests, and optional
    expected digest matching.
  - Added content-check failures to the manifest result path so existing files
    cannot satisfy L4 evidence unless their contents are valid.
- `scripts/sitl/run_px4_gazebo_visual_profile.sh`
  - Added side-effect-free dry-run default, explicit `probe-only` and
    `execute-gazebo` modes, and visual artifact import options.
  - Runtime modes do not configure MavlinkAnywhere, start PixEagle, start
    MAVLink2REST, install services, mutate host routing, or touch hardware.
- `.github/workflows/px4-gazebo-visual-validation.yml`
  - Added opt-in workflow with `workflow_dispatch` plus scheduled dry-run only.
  - Added read-only permissions, claim-boundary output, optional image pull,
    visual artifact import inputs, artifact upload, and no `push` or
    `pull_request` trigger.
- `Makefile`
  - Added `sitl-gazebo-dry-run`, `sitl-gazebo-probe`, and
    `sitl-gazebo-execute-px4` targets.
- `tests/test_sitl_validation_contract.py`
  - Added Gazebo plan, wrapper, workflow, Make target, content-check positive
    and negative tests, and missing-visual-evidence plan rejection tests.
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `tools/sitl_plans/README.md`
  - Documented official PX4 Gazebo visual profile commands, import flags,
    artifact-content checks, claim boundaries, and current official PX4 source
    references checked on 2026-06-03.

## Validation

Passed:

```bash
bash -n scripts/sitl/run_px4_gazebo_visual_profile.sh scripts/sitl/run_px4_sih_profile.sh
```

```bash
/tmp/pixeagle-audit-venv/bin/python -m py_compile \
  tools/run_sitl_validation_suite.py \
  tests/test_sitl_validation_contract.py
```

```bash
python3 -m json.tool tools/sitl_plans/gazebo_visual_validation.json >/dev/null
```

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode dry-run --json
```

Result: side-effect-free dry-run passed, `would_start_processes=false`,
`scenario_count=3`, `manual_fault_actions=0`, `control_actions=0`, and plan
hash `51965e5de76e23cd8ff35d9d3c3f80803b6b310b4ac8416fd7e321e9338cb483`.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
pytest tests/test_sitl_validation_contract.py -q
```

Result: 45 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
pytest tests/test_docs_infrastructure_consistency.py \
  tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py -q
```

Result: 55 passed, 1 skipped.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON=/tmp/pixeagle-audit-venv/bin/python \
make sitl-gazebo-dry-run
```

Result: passed, same dry-run contract as above.

Broader focused suite:

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_sitl_validation_contract.py \
  tests/sitl/test_px4_validation_harness.py \
  tests/test_udp_video_receiver_proof.py \
  tests/unit/video/test_gstreamer_pipelines.py \
  tests/unit/video/test_video_handler.py \
  tests/unit/core_app/test_flow_controller_frame_freshness.py -q
```

Result: 181 passed, 1 skipped.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH bash scripts/check_schema.sh
```

Result: schema up to date.

```bash
git diff --check
```

Result: passed with only the existing CRLF normalization warning for
`src/tools/gstreamer_tests/gstreamdl_receiver_rtp.bat`, no whitespace errors.

Not run:

- Docker image pull or Docker/PX4/Gazebo container execution
- PixEagle/MavlinkAnywhere/MAVLink2REST runtime stack
- Gazebo video ingest from a real simulator run
- SITL scenario execution against a full stack
- GitHub Actions hosted workflow
- HIL, field, real aircraft, deployment, or service installation

## Review Gate

Independent read-only review found blockers and they were fixed:

- visual artifacts were declared but not imported or content-validated;
- L4 scenarios overclaimed what GET-only actions prove;
- PX4 Gazebo image/container digest evidence was not enforced;
- docs still framed the guide as Phase 2 only and duplicated weak Gazebo text;
- tests mostly asserted strings without validating evidence content.

One DevOps reviewer agent errored from usage limits and made no changes. The
two completed reviews were integrated before this checkpoint.

## Risks And Open Questions

- PXE-0040 remains open for runtime official Gazebo evidence. A later runtime
  probe found that `px4io/px4-sitl-gazebo:v1.17.0` is not a valid Docker Hub
  tag; the active profile now uses
  `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01` with exact repo
  digest
  `px4io/px4-sitl-gazebo@sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db`.
- Accepted runtime evidence must include Docker `RepoDigests` and match the
  plan's expected digest unless the profile is intentionally updated with a new
  reviewed tag/digest.
- Visual trace JSONL validation is intentionally format-tolerant for this
  contract slice. A later tracker trace export slice should define a stricter
  normalized schema with frame index, target metadata, command intent, Offboard
  publish status, and timestamps.
- Local Docker API access was previously observed as unavailable without
  operator/user-group changes, so runtime execution should be done on an
  operator-approved validation host or CI runner with Docker access. Rechecked
  on 2026-06-04: `docker --version` reported Docker `29.1.3`, but
  `docker ps --format '{{.ID}} {{.Image}} {{.Names}}'` failed with
  `permission denied while trying to connect to the docker API at
  unix:///var/run/docker.sock`.

## Next Planned Slice

Continue PXE-0040 with a real official Gazebo visual runtime proof on an
operator-approved host:

1. Pull and record
   `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01` image metadata and
   repo digest
   `sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db`.
2. Start only the harness-owned Gazebo container with `HEADLESS=1`.
3. Prepare MavlinkAnywhere, MAVLink2REST, and PixEagle manually or with
   separately approved sidecar scripts.
4. Capture Gazebo frame hashes, receiver pipeline, tracker command trace,
   Offboard publish trace, PX4 params/logs/ULog/tlog manifests, structured route
   evidence, config snapshots, and manifest.
5. Keep the run incomplete unless every artifact and content check passes.
