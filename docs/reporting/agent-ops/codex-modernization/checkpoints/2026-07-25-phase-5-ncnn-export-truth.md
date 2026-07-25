# Phase 5: Optional NCNN Export Truth

## Slice

- Issue: PXE-0146
- Date: 2026-07-25
- Scope: model upload status, optional NCNN export, CPU candidate selection

## Decision

NCNN is not a required companion to a `.pt` model. NVIDIA CUDA uses the
trusted `.pt` artifact directly. NCNN is an opt-in CPU/edge path for a target
where its measured latency, memory use, or deployment constraints justify the
additional `ncnn` and `pnnx` dependencies.

The upload checkbox remains off by default. A requested export is a separate
phase after registration. If that phase fails, the trusted `.pt` registration
is retained and the dashboard reports the partial result.

## Changes

- Added explicit `ncnn_export_requested` response state.
- Made the Models page show the export phase after upload reaches 100 percent.
- Changed inventory wording from ambiguous `Yes/No` to `Ready/Not exported`.
- Required verified NCNN provenance for persisted CPU standby selection.
- Retained ordered CPU candidates so missing, unverified, or runtime-broken
  NCNN falls back to the trusted `.pt` model.
- Added API, model-manager, and runtime fallback coverage.
- Documented the managed non-root delegated-service requirement for export;
  manual tmux and root-owned runtimes fail closed.

## Validation

- `PYTHONPATH=src .venv/bin/pytest -q tests/unit/core_app/test_model_manager_upload.py tests/unit/core_app/test_api_legacy_model_routes.py tests/unit/core_app/test_ultralytics_backend.py`
  - 121 passed
- `npm test -- --runInBand --watchAll=false src/pages/ModelsPage.test.js src/hooks/useModels.test.js`
  - 11 passed
- `bash scripts/setup/check-ai-runtime.sh --json`
  - local `ncnn`/`pnnx` absent as expected
  - trusted `.pt` first-inference probe succeeded through CPU fallback

## Evidence And Limits

No untrusted or user-uploaded checkpoint was executed and no target-host NCNN
export was run. The local report is not CUDA, Raspberry Pi, Jetson, or
production evidence. A target that needs NCNN must install the optional
dependencies, use the managed non-root service, select the upload export
checkbox, and retain the resulting runtime/latency/thermal evidence.

## Next Step

Run the normal `.pt`/CUDA or Core test first. Only run the optional NCNN
workflow on the intended CPU/edge target when its benchmark justifies it.
