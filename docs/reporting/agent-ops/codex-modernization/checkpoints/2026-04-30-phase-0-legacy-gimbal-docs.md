# Phase 0 Checkpoint - Legacy And Gimbal Contract Cleanup

Date: 2026-04-30  
Status: completed for Phase 0 Slice 5

## Scope

This slice closed the remaining Phase 0 legacy cleanup around removed follower
aliases, stale gimbal-vector docs, active runtime docs, and the user's gimbal
modularity side note.

## Work Completed

- Removed the superseded `GIMBAL_VECTOR_BODY_IMPLEMENTATION_SUMMARY.md` developer
  doc from active docs.
- Renamed the gimbal follower smoke test to
  `tests/test_gm_velocity_vector_smoke.py` and kept it focused on
  `GMVelocityVectorFollower` plus the removed-alias guard.
- Replaced `deprecated_profile_aliases` with `removed_profile_aliases` in
  `configs/follower_commands.yaml` and the config consistency test.
- Removed stale config backup files that taught removed aliases and old flat
  gimbal keys.
- Corrected gimbal docs/code comments: current support is Topotek SIP-series
  UDP (`GAC`, `GIC`, `TRC`, `OFT`), not a generic gimbal API and not MAVLink
  Gimbal v2.
- Removed the flat gimbal config fallback from `GimbalTracker`; active config is
  `GimbalTracker.UDP_HOST`, `UDP_PORT`, `LISTEN_PORT`, `COORDINATE_SYSTEM`, and
  `DISABLE_ESTIMATOR`.
- Cleaned active docs from old backend/OSD ports, stale `run_pixeagle.sh`
  entrypoints, stale `http.port: 8000` snippets, and old flat gimbal keys.
- Extended docs guardrails so active runtime docs cannot reintroduce those stale
  ports, entrypoints, gimbal keys, or incorrect SIP/passive wording.
- Added PXE-0016 for the next phase: extract a typed `GimbalInputProvider`
  boundary and move the current Topotek implementation behind
  `SipUdpGimbalProvider`, leaving followers protocol-agnostic.

## Gimbal Decision

The current gimbal integration is a Topotek SIP-series UDP client. It sends
query commands and parses response/broadcast frames before `GimbalTracker`
normalizes the data into `TrackerOutput(data_type=GIMBAL_ANGLES,
angular=(yaw, pitch, roll), ...)`.

Best practice for PixEagle is not to make followers know any vendor protocol.
The next runtime phase should add a provider contract below `GimbalTracker`:

- `SipUdpGimbalProvider` for the current Topotek protocol.
- `MavlinkGimbalProvider` for MAVLink Gimbal Protocol v2 / MAVSDK Gimbal.
- Vendor adapters for commercial gimbals where needed.
- Simulator/fake providers for deterministic tests.

Primary references consulted:

- Topotek SIP-series protocol PDF: `https://www.topotek.cn/download/protocol/TopotekSIPseriesProtocol20221010.pdf`
- MAVLink Gimbal Protocol v2: `https://mavlink.io/en/services/gimbal_v2.html`
- PX4 gimbal configuration: `https://docs.px4.io/main/en/advanced/gimbal_control`
- MAVSDK Gimbal API: `https://mavsdk.mavlink.io/main/en/cpp/api_reference/classmavsdk_1_1_gimbal.html`

## Validation

Completed:

- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py tests/test_gm_velocity_vector_smoke.py tests/test_test_hygiene.py tests/unit/followers/test_config_consistency.py tests/unit/trackers/test_gimbal_tracker.py -ra --tb=short --strict-config -W error::pytest.PytestReturnNotNoneWarning`
  - Result: 61 passed.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh`
  - Result: schema up-to-date.
- `PYTHON=/tmp/pixeagle-audit-venv/bin/python make phase0-check`
  - Result: schema check passed and 22 tests passed.
- `PYTHONPATH=src /tmp/pixeagle-audit-venv/bin/python -m pytest tests/ -ra --tb=short --strict-config`
  - Result: 1618 passed, 40 skipped.
- `git diff --check`
  - Result: passed.

## Evidence Paths

- Current gimbal interface:
  `src/classes/gimbal_interface.py`
- Current gimbal tracker:
  `src/classes/trackers/gimbal_tracker.py`
- Gimbal tracker reference docs:
  `docs/trackers/02-reference/gimbal-tracker.md`
- Docs guard:
  `tests/test_docs_infrastructure_consistency.py`
- Follower config consistency:
  `tests/unit/followers/test_config_consistency.py`
- Issue register:
  `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- Journal:
  `docs/reporting/agent-ops/codex-modernization/journal/2026-04.md`

## Risks And Open Items

- PXE-0016 remains open for runtime gimbal provider extraction and MAVLink/vendor
  adapter support.
- PXE-0013 and PXE-0014 remain open for Offboard heartbeat/safety and typed
  MAVLink polling timeout/retry behavior.
- PXE-0009 and PXE-0010 remain open for dashboard dependency and ESLint cleanup.

## Plan Reconciliation

This slice aligns Phase 0 with the modernization plan's "no confusing legacy"
goal. The current gimbal path is now documented honestly, followers remain
protocol-agnostic, and the deeper multi-gimbal abstraction is tracked as a
runtime phase instead of being hidden inside docs debt.
