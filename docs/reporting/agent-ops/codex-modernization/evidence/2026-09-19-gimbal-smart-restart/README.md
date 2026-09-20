# Optional camera Smart selection / restart recovery evidence

2026-09-19. Offline tests and actual supervised process/API restart using the
bundled file video. No camera or aircraft traffic; no corrected-camera target
retention claim. See the [checkpoint](../../checkpoints/2026-09-19-gimbal-smart-restart.md).

- Backend: 216 focused + 183 lifecycle/system tests passed.
- Dashboard: 433 tests and production build passed.
- `restart-api-results.json` records the setting save, restart request, changed
  backend PID, loaded rotations [0,180], cleared pending configuration and
  unchanged user-config hash. `restart-runtime.log` records both processes.
- `launcher-config-check.log` verifies the actual camera bench's load/persistence
  isolation without starting runtime subsystems.
- `manifest.json` links artifacts and implementation source hashes to the dirty
  feature branch baseline. Passing tests do not prove hardware tracking quality.

Reproduce the offline process check from the repository: copy
`restartable_bench.py` to `reports/gimbal-manual-integration/`, copy
`offline_launcher.py` as `reports/gimbal-restart-offline/launcher.py`, copy
`check_restart.py` to that same offline directory, and copy
`offline-initial-config.yaml` as its `bench-config.yaml`. Then run:

```bash
.venv/bin/python reports/gimbal-restart-offline/check_restart.py
```

The check uses loopback 5079, file video and disabled external control. It saves
only its isolated test setting, shuts down its owned processes and does not
install a service. Port 5079 must be free. Reset the initial config before
repeating. Camera bench use requires the separately retained private
`reports/gimbal-manual-integration/bench-config.yaml`; this evidence does not
start that camera runtime.
