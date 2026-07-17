# Phase 3 Checkpoint: Official Gazebo Runtime Probe

Date: 2026-06-04  
Phase/slice: Phase 3, PXE-0040 runtime probe  
Status: incomplete runtime evidence; useful blocker identified and recorded  
Claim boundary: Docker/PX4/Gazebo container startup probe only. This is not a
PixEagle tracker/follower visual SITL pass, PX4 Offboard pass, HIL, field,
deployment, service-install, or real-aircraft validation.

## Summary

Docker access was restored through the `docker` group only for commands run via
`sg docker`. The active shell still did not include the `docker` group in
`id`, so ordinary `docker ps` failed, but `sg docker -c 'docker ps ...'`
worked.

The previously selected official image tag
`px4io/px4-sitl-gazebo:v1.17.0` does not exist on Docker Hub. The profile,
wrapper, workflow, docs, and tests were corrected to the pullable v1.17-family
tag:

```text
px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01
px4io/px4-sitl-gazebo@sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db
```

The official image can be pulled and inspected on this host. A guarded
`execute-gazebo` run verified the image/container digest metadata in one run,
but the run correctly remained incomplete because PixEagle, MAVLink2REST,
validated MavlinkAnywhere route/profile evidence, Gazebo frame hashes, and
tracker/Offboard traces were not running or attached.

A longer official container probe reproduced the current VPS/headless blocker:
PX4 starts the `gz_x500_mono_cam` airframe and launches Gazebo 8.11.0, but the
PX4 init script times out waiting for `/world/default/scene/info` and exits
with code `255`. Direct verbose `gz sim` inside the same image shows the world
and custom `GstCameraSystem` can load and that the camera stream is configured
for UDP host `127.0.0.1`, UDP port `5600`, but readiness is too slow/fragile for
the official all-in-one PX4 startup path on this host.

This is recorded as an official-image/headless-runner blocker, not as a
PixEagle tracker/follower failure. The tracker/follower visual path was not
executed because PX4/Gazebo did not reach a stable accepted runtime state.

## Files Changed

- `tools/sitl_plans/gazebo_visual_validation.json`
  - Replaced the nonexistent `v1.17.0` tag with
    `v1.17.0-alpha1-1551-g381149fb01`.
  - Pinned `expected_repo_digest` to
    `px4io/px4-sitl-gazebo@sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db`.
- `scripts/sitl/run_px4_gazebo_visual_profile.sh`
  - Updated the default PX4 Gazebo image tag.
- `.github/workflows/px4-gazebo-visual-validation.yml`
  - Updated workflow default image/tag.
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `tools/sitl_plans/README.md`
  - Updated official image guidance.
- `tools/run_sitl_validation_suite.py`
  - Added a helper so `execute` mode only auto-discovers/copies container
    artifacts after a harness-owned container ID is verified.
  - This prevents stale-name `docker exec`/`docker cp` attempts when the PX4
    container exits before ownership verification.
- `tests/test_sitl_validation_contract.py`
  - Updated expected image/digest values.
  - Added regression coverage for the execute-mode artifact auto-collection
    gate.

## Evidence

Docker access:

```bash
docker --version
```

Result: Docker `29.1.3`.

```bash
docker ps --format '{{.ID}} {{.Image}} {{.Names}}'
```

Result in the current shell: permission denied on `/var/run/docker.sock`.

```bash
sg docker -c 'id && docker ps --format "{{.ID}} {{.Image}} {{.Names}}"'
```

Result: command ran with `gid=110(docker)` and listed the existing unrelated
`freqtrade` container.

Image pull:

```bash
sg docker -c 'docker pull px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01'
```

Result: pulled successfully with digest
`sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db`.

Rejected tag:

```bash
sg docker -c 'docker pull px4io/px4-sitl-gazebo:v1.17.0'
```

Result: `manifest unknown`.

Guarded run with digest metadata:

```bash
sg docker -c 'PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_gazebo_visual_profile.sh \
  --mode execute-gazebo \
  --px4-image px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01 \
  --px4-model gz_x500_mono_cam \
  --artifact-root reports/sitl \
  --run-id 20260604T-pxe0040-official-gazebo-container-probe \
  --startup-wait-s 45 \
  --timeout-s 5 \
  --json'
```

Result: incomplete. Evidence directory:

```text
reports/sitl/20260604T-pxe0040-official-gazebo-container-probe-gazebo_visual_validation/
```

Key evidence:

- `px4/container_metadata.json`: image/container repo digest check passed.
- `logs/px4_sitl.log`: PX4 launched Gazebo and was waiting for world readiness
  when the harness stopped the verified container.
- Missing PixEagle/MAVLink2REST/video/trace artifacts correctly kept the run
  incomplete.

Longer startup probe:

```bash
sg docker -c 'PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_gazebo_visual_profile.sh \
  --mode execute-gazebo \
  --px4-image px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01 \
  --px4-model gz_x500_mono_cam \
  --artifact-root reports/sitl \
  --run-id 20260604T-pxe0040-official-gazebo-container-probe-120s \
  --startup-wait-s 120 \
  --timeout-s 5 \
  --json'
```

Result: incomplete. Evidence directory:

```text
reports/sitl/20260604T-pxe0040-official-gazebo-container-probe-120s-gazebo_visual_validation/
```

Key evidence:

- `logs/px4_sitl.log`: `ERROR [init] Timed out waiting for Gazebo world` and
  `ERROR [px4] Startup script returned with return value: 256`.
- `managed_processes.px4.returncode_after_startup_wait`: `255`.
- Container metadata was incomplete because the container had already exited.

Direct Gazebo diagnostic:

```bash
sg docker -c 'docker run --rm --network host --entrypoint /bin/sh \
px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01 -lc "... gz sim ..."'
```

Result: direct verbose Gazebo loaded the `default.sdf` world and reported:

- Gazebo Sim Server `8.11.0`;
- `GstCameraSystem configured for world [default]`;
- `UDP Host: 127.0.0.1`;
- `UDP Port: 5600`;
- later service publication for `/world/default/scene/info`.

## Validation

Passed:

```bash
python3 -m py_compile tools/run_sitl_validation_suite.py tests/test_sitl_validation_contract.py
```

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH PYTHONPATH=src \
pytest tests/test_sitl_validation_contract.py -q
```

Result: 47 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_gazebo_visual_profile.sh --mode dry-run --json
```

Result: passed; `would_start_processes=false`; plan hash
`d86fe1369e83ea0b8a38fc61bc0fe55cad890c3c87a3b3ec9610a56222dc3579`.

Not run:

- PixEagle runtime stack
- MAVLink2REST runtime stack
- MavlinkAnywhere route mutation or service installation
- Gazebo video frame ingest through PixEagle
- tracker/follower/Offboard command scenario against Gazebo
- GitHub Actions hosted workflow
- HIL, field, deployment, service installation, or real aircraft

## Risks And Decisions

- Do not mark PXE-0040 passed on this host. The accepted L4 evidence package is
  still open.
- The `gz_x500_mono_cam` model and UDP video plugin are present in the official
  image, so this is not evidence that the visual plan is conceptually wrong.
- The official all-in-one PX4/Gazebo entrypoint has a fixed 30-attempt world
  readiness loop. On this VPS/headless/container path, Gazebo sensor/render
  initialization is slow enough or fragile enough that PX4 times out before it
  can proceed.
- A future full L4 visual run should be done on native Ubuntu with GUI/GPU or a
  CI runner proven to run Gazebo Harmonic camera models headlessly, then attach
  PixEagle video/tracker/follower/PX4 artifacts to this same harness.
- For this VPS, continue with reliable L2/L3 validation:
  - official PX4 SIH for control-plane/Offboard cadence evidence;
  - generated RTP/H.264 UDP receiver proof;
  - deterministic synthetic video/tracker-in-loop traces;
  - later merge the proven layers under typed `/api/v1` action contracts.

## Next Planned Slice

Continue without over-forcing full Gazebo on this VPS:

1. Keep PXE-0040 open for native-GUI/better-runner visual Gazebo evidence.
2. Proceed locally with lightweight SIH plus synthetic visual/tracker evidence
   and PXE-0042 typed SITL control actions.
3. Update X-Plane/Windows guidance later as a manual L4/L5 evidence workflow or
   move it to historical docs.
