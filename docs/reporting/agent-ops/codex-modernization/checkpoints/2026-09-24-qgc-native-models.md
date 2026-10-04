# PXE-0177: Native installed Smart model selection

Date: 2026-09-24. QGC slice: 3b. Branch: `feature/qgc-native-integration`.
Base revision: `989d9662173b364de03b307f4208e9d0ca96451f` plus local integration
changes. This checkpoint preserves previous slice-0–3 reports and snapshots.

Status: **backend model contract gate passed; paired Full AI runtime and QGC
operator qualification remain separate evidence**. No following, physical
camera/gimbal, PX4, SITL, deployment, Windows or Android claim is made here.

## Changes

Added authenticated, bounded installed-model inventory and class-label reads,
and a guarded model-selection action under `/api/v1`. The API distinguishes
configured and active Smart models, reports effective device/fallback without
private checkpoint paths, and uses the existing dashboard trust/validation,
configuration persistence and live-model rollback executor. It accepts model IDs
from the current inventory only; it does not add model downloads or activate
Smart mode implicitly. Full request/response, permission, retry and error details
are in [native model operations](../../../../apis/native-model-operations.md).

Follower and tracker/model barriers serialize native and dashboard changes on
the same owner loop. Native context and installed-model generation are checked
again after checkpoint validation. Short source checks avoid holding frame
publication and aircraft-observation locks during model loading. Native
target-state reads now wait off the API loop so a model load cannot block other
HTTP routes through that read. Dashboard standby choices invalidate the shared
target revision just like native choices and live model replacement.

Files: `api_v1_native_models.py`, model contracts/routes/paths/security metadata,
integration capability, `api_legacy_model_routes.py`, target-state read dispatch,
route/candidate inventory, native-model tests, and API/reporting docs. No dashboard
source, default config, schema, physical control, or main-checkout edits belong
to this sub-slice. Other existing integration worktree changes are preserved.

## Validation and provenance

Evidence directory (retained slice start date):
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-3b-2026-09-22/backend/`.
Evidence timestamps are 2026-09-24; the directory name is not the execution date.

- `focused.log/xml`: **249 passed**, two dependency deprecation warnings.
  Includes 33 native-model tests, 28 existing dashboard-model tests, 32 native
  target tests, native association tests, route/candidate/security inventories,
  and the required parameter reload gate.
- `final-gates.log/xml`: **372 passed, 1 pre-existing failure**, four dependency
  warnings. This adds the CI Phase-0 hygiene/docs/binary/production-browser
  harness/config checks and auth runtime tests. These results overlap the focused
  gate and must not be added as unique test counts.
- The sole failure is `test_no_placeholder_test_files_or_audit_stubs`: the static
  guard rejects `sent.append(frame) or True` in three existing gimbal transport
  test doubles. `git show HEAD:tests/unit/trackers/test_gimbal_control.py` confirms
  the same expressions at base lines 137, 167 and 293. No gimbal fixture changes
  were made here and no green whole-CI claim is made.
- `schema.log`: **43 sections / 606 parameters**, no drift.
- `fatal-lint.log`: pinned `flake8==7.3.0`, CI fatal selection
  `E9,F63,F7,F82`, passed for the changed model/contract/dispatch/tests/tool files.
- Generated non-callable API/MCP inventory, Python compilation and
  `git diff --check` passed. Inventory now contains 146 declared route pairs,
  144 HTTP routes, 54 typed candidates, zero callable/promoted tools.
- `source-manifest.json` records exact source hashes, package versions, commands,
  evidence hashes and source-archive checksum. It contains no credentials or
  private user configuration.

Core validation environment: Python 3.12.3, pytest 9.1.1, FastAPI 0.141.1,
Pydantic 2.13.5, Starlette 1.6.0, HTTPX 0.28.1. Real Full AI package/model/device
provenance belongs to the separate runtime evidence, not this mocked/API gate.
The dashboard was not changed or rerun in this sub-slice; earlier exact-revision
dashboard CI limitations remain documented at the baseline checkpoint.

## Remaining plan

Use the existing local Full AI installation in an isolated recorded-video
snapshot. Verify trusted model metadata, Smart enable/disable, model replacement,
class matching, selection, retarget, loss/recovery, Cancel and Classic return in
the paired QGC build. Exercise each locally available Classic tracker and record
actual model/runtime/device results. These runtime checks may expose additional
issues; they are not inferred from the contract tests above.

After that operator checkpoint, physical external camera tracking needs the
operator's camera connection and explicit run instructions. Native following and
gimbal movement controls remain slice 4; cross-platform release qualification
remains slice 5. The original clean main checkout and completed dashboard gimbal
work are preserved.
