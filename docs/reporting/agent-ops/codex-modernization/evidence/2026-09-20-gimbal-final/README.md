# Final software handoff evidence

Branch includes upstream `f30dce2`. Manifest records changed source and artifacts.
Logs: 659 backend tests, 471 dashboard tests, successful production build/schema.
Browser events: five passing widths, no forwarded camera actions. Screenshots
show only controls, without room video. Passive vertical capture log and startup
API snapshots are evidence of observation only, not a controlled tracking test.
Room frames remain private under `reports/gimbal-bench/20260920T032242Z-user-manual-observe`.

Reproduce dashboard checks from `dashboard/`:

```sh
CI=true npm test -- --watchAll=false --runInBand
npm run build
```

From repo root, `bash scripts/check_schema.sh` and `git diff --check`.
Backend test paths/command are recorded in `validation-commands.txt`.
Browser harness must be copied to `reports/gimbal-sidebar-final/browser_check.cjs`
for its relative Playwright import; run with Node from repo root, production
UI on port 3040 and isolated backend on 5077. It reads a saved status fixture
from the previous movement evidence and intercepts every action endpoint.
