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
- Next: Core-first Raspberry Pi 5 walkthrough. Full/model/GStreamer/service/PX4
  are later opt-in gates. QGC remains deferred.

