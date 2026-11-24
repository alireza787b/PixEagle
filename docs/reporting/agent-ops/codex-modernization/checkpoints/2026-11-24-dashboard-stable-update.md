# Dashboard stable-update checkpoint

## Phase

Beginner-facing stable-release maintenance for Linux PixEagle installations.

## Delivered

- Added a read-only release page reachable from About and Settings.
- Added official stable release discovery with a 24-hour cache, explicit manual
  refresh, tag and peeled-commit verification, and offline last-success state.
- Added a typed, authenticated, idempotent update action. The worker runs outside
  the Dashboard process and records durable progress, restart readiness, recovery,
  and configuration migration review.
- Preserved private YAML and environment files, reviewed local source edits with a
  named stash, and made rollback conditional on matching source/config identities.
- Added candidate configuration validation, effective-config attestation, a
  backend authentication probe, and an exact served-Dashboard verification before
  reporting success.
- Added a responsive operator guide and screenshot at
  `docs/setup/dashboard-updates.md` and `docs/setup/images/software-update.png`.

## Validation

- `535 passed, 1 skipped` in the backend/API/config/integration qualification
  selection. The skipped test is the explicit opt-in user-systemd test.
- `20 passed, 1 skipped` in the updater tests with the user-systemd test opt-in.
- `586 passed` Dashboard tests.
- Dashboard ESLint and production build passed.
- Schema check and generated API tool inventory check passed.
- Ruff passed on all newly added Python files. Shell syntax and `git diff --check`
  passed.
- A disposable Git transaction installed a pinned release, preserved active and
  local configuration, retained a reviewed source stash, and restored the exact
  previous revision.
- A real Ubuntu transient user-systemd worker survived its caller and stopped at
  configuration review without changing the checkout.
- Playwright checked the update review at desktop and 360-pixel widths and found
  no horizontal overflow.

## Boundaries

No Raspberry Pi, aircraft, QGC package, public release, or production service was
changed in this slice. The managed systemd start/stop path is covered by the
existing host contracts and the updater's service-mode tests. A live installation
should be updated only after reviewing the guide and keeping the device idle.

## Next step

Run a controlled operator acceptance on one Linux installation, then decide
whether to publish the PixEagle commit. Keep the private QGC fork and field
configuration outside this updater change.
