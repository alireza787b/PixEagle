# Phase 5 Checkpoint: v7 Stable Local/Demo Baseline

Date: 2026-07-26
Issue: PXE-0074
Status: stable software baseline ready; physical acceptance remains open

## Release Scope

`v7.0.0` is the first stable release of the maintained local/demo PixEagle
software contracts. It consolidates the v7 beta series and includes the final
Smart-model preflight and catalog-driven follower Settings correction from
PXE-0147.

Stable does not mean flight qualified. PX4/Pixhawk response, Raspberry Pi
performance, representative follower modes, camera/gimbal integration, QGC
receipt, SIH/SITL/HIL execution, field safety, aircraft operation, and
regulatory compliance require separate target evidence.

## Release Gates

- Maintained non-hardware backend: `3,611 passed`, `47` expected platform/dlib
  skips, `1` deselected external marker.
- Phase 0: `492 passed`.
- Focused PXE-0147 backend/schema/action suite: `298 passed`.
- Dashboard: `57` suites, `379` tests passed.
- Dashboard production build: passed.
- Generated schema: `39` sections, `518` parameters, current.
- Generated API tool-candidate provenance: current.
- Python compile, shell syntax, Markdown links, and `git diff --check`: passed.

## Known Non-Blocking Toolchain Notices

- Starlette reports the tracked `httpx` TestClient migration warning.
- React Router reports its existing v7 future-flag notices in one test.
- The production build reports Node's transitive `fs.F_OK` deprecation.

No notice above changed runtime behavior in this slice. They remain normal
dependency-maintenance work rather than reasons to misstate hardware evidence.

## Next Evidence

1. Install the exact tag on a Raspberry Pi using only the public README and
   installation guide; retain Core and then Full/model setup evidence.
2. Validate representative follower command intents, axis conventions,
   Offboard engagement/abort, and PX4/Pixhawk response with controlled
   simulation or bench progression.
3. Validate real camera/gimbal input and target-loss/reacquisition behavior.
4. Report bugs with exact tag/commit, host, config, commands, and sanitized
   runtime logs.
