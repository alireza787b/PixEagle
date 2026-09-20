# Classic rectangle selection and mounting readiness evidence

This bundle separates current software validation from the earlier connected
camera session. `manifest.json` hashes the current touched source and artifacts.
The historical connected session ran the preceding Smart/restart source state,
whose hashes are in `../2026-09-19-gimbal-smart-restart/manifest.json`; it does
**not** qualify the new drag path or a vertical installation.

Current validation commands:

```sh
PYTHONPATH=src .venv/bin/pytest -q tests/unit/trackers/test_gimbal_control.py tests/unit/core_app/test_api_v1_gimbal_control.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_backend_restart_lifecycle.py
cd dashboard
CI=true npm test -- --watchAll=false --runInBand
npm run build
cd ..
bash scripts/check_schema.sh
.venv/bin/python -m py_compile src/classes/gimbal_control.py src/classes/api_v1_contracts.py src/classes/api_v1_actions.py
git diff --check
```

Logs are under `validation/`. `drag-runtime-restart.json` records the normal
typed restart action; `drag-runtime-ready.json` records returned camera status
and selection request schema. No target is selected by these checks.

`corrected-orientation-bench/` contains prior API/browser actions, exact helper
scripts, and wire records bounded to 2026-09-19 19:03:40–19:13:22 UTC. Its capture
events reference private local images through file names, dimensions, timestamps
and SHA-256. Images and manufacturer source/PDF files are deliberately not copied
into Git. Capture scripts use local bench paths and should be reviewed before
reuse; selection scripts command the standalone camera and are not passive.

Observed short Classic retention and successful cancellation are described in
the [checkpoint](../../checkpoints/2026-09-19-gimbal-drag-selection.md). Later
operator clicks include loss/reacquisition. AI candidate identity, physical
vertical mounting, drag retention and aircraft behavior remain unqualified.
