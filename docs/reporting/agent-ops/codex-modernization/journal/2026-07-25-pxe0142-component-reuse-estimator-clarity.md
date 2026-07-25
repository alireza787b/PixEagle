# PXE-0142: Verified Component Reuse And Estimator Clarity

Date: 2026-07-25
Status: implementation and local validation complete; target acceptance pending

## Decisions

- Setup reuse is contract-driven, not inferred from a PixEagle version string
  or package presence. Each maintained component verifies the installed
  version and the capabilities PixEagle currently requires.
- `PIXEAGLE_REBUILD_COMPONENTS` is the single advanced override for an
  intentional rebuild. Normal guided users are not asked component-by-component
  repair questions.
- Local config and dashboard environment are preserved by default. Explicit
  reset affects both together and is transactional; schema evolution remains
  owned by Config Sync and its provenance/audit records.
- Predictor output is diagnostic during measurement gaps. It may guide
  reacquisition and the operator overlay, but it is never fresh follower input.
- The Classic segmentor is Selection Assist. SmartTracker accepts `detect` and
  `obb`; `segment` support is deferred under PXE-0143.

## Evidence

Focused setup/config, API/runtime, estimator/tracker/state, full backend,
dashboard, schema, generated-contract, Bash, ShellCheck, Python compile, and
diff gates passed. The detailed counts and remaining evidence boundary are in
the phase checkpoint.

## Remaining Gate

Run the maintained update/reset path on Ubuntu, then install and validate the
exact candidate on Raspberry Pi with a representative camera. These target
tests must not infer PX4, QGC, gimbal, field, or aircraft success.
