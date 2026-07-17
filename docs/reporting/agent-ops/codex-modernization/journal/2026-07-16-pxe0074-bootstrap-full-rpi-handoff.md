# 2026-07-16 PXE-0074 Bootstrap/Full/RPi Handoff Journal

- Recovered the interrupted Full setup run and confirmed its transaction had
  rolled back to Core cleanly.
- Reproduced the first-run failure: Ultralytics emitted settings text on stdout,
  contaminating the installer's JSON command substitution.
- Moved the verifier result to private fd 3 and proved the real first-run Full
  install, OpenCV preservation, dependency policy, and model-required boundary.
- Fixed launcher ownership checks to load the configured telemetry port and use
  one canonical decimal port validator for backend, telemetry, and MAVSDK.
- Kept read-only AI installer help available during a running PixEagle session.
- Made clean-walkthrough log references portable and published final candidate
  reports.
- Passed 272 focused setup/runtime tests, 72 mandatory API/parameters tests,
  schema/syntax/ShellCheck checks, bounded independent `GO`, and the exact
  `6df1cb4e` clean walkthrough with 26/26 commands plus 49 dashboard suites and
  296 tests.
- Official ARM64 artifact indexes contain the selected CPython 3.12 PyTorch
  stack, but Raspberry Pi execution remains an explicit operator gate.
- Refreshed the final pushed `a25b104b` source through the clean-clone harness.
  The updater correctly refused while the accepted public demo was active; the
  bounded no-update rerun passed 23/23 commands, including schema and 72 minimum
  backend/API tests, without interrupting the tester bench. A dashboard-inclusive
  exact rerun then passed 26/26 commands, 49 suites, 297 tests, and the production
  build with clean initial/final source state.
- Created the previously missing owner-only Raspberry Pi 5 handoff at mode
  `0600`. It pins Core-first browser/restart evidence and keeps Full AI plus a
  separately trusted model as later gates.
- The local handoff audit fixed masked installer exit status, removed an
  interactive log-attach instruction from bounded evidence capture, and aligned
  model registration examples with the schema-backed default while preserving
  an explicit custom-path workflow. A new independent refresh verdict is not
  claimed because the delegated reviewer quota was unavailable.
- Next: Core-first Raspberry Pi 5 walkthrough. Full/model/GStreamer/service/PX4
  are later opt-in gates. QGC remains deferred.
