# PXE-0113: Interrupted Setup Recovery

## 2026-07-20

- The maintainer confirmed the beta.11 one-line path now retained interactive
  input and advanced through setup. SSH then disconnected during a long build,
  exposing a separate recovery and operator-language gap rather than a repeat
  of the beta.11 terminal bug.
- Audited fresh setup, current-source repair, fast-forward update/repair,
  generated-output cleanup, config reset, and clean replacement boundaries.
  Kept destructive full reset out of the beginner flow; clean comparison uses
  a new install directory and explicit validation/cutover.
- Added `make repair` and explicit terminal descriptions of detected
  fresh/existing state, reuse, reconciliation, and preserved operator data.
  The one-line installer still performs guarded update plus repair for an
  existing clean checkout.
- Consolidated setup and runtime dashboard dependency decisions into one
  lockfile authority. Hash equality is only a hint: reuse also requires an
  offline full-tree `npm ls --all`. Missing, stale, or interrupted state uses
  strict `npm ci`; the prior mutable `npm install` fallback was removed.
- Documented interruption behavior. Host package managers remain responsible
  for their own recovery diagnostics. Python mutations, nvm publication,
  binary downloads, and OpenCV replacement retain their existing transaction
  boundaries. An interrupted optional source build restarts from private
  staging rather than trusting partial compiler output.
- Local validation before candidate publication: installer/setup matrix
  `304 passed, 1 skipped`; API/docs/version matrix `101 passed`; dashboard
  `53 suites / 348 tests`; optimized production build; schema `40 sections /
  535 parameters`; Bash syntax, bounded ShellCheck, and diff hygiene passed.
  A real two-pass dashboard reconciliation performed one `npm ci`, recorded
  the verified state, then reused it on the second pass.

## Next

Commit the candidate, run the exact clean-checkout handoff, publish beta.12,
refresh the credential-preserving public browser bench, and have the maintainer
rerun only after the previous installer has exited. Keep Raspberry Pi, Full AI,
dlib/GStreamer target builds, PX4/simulation, QGC, production, and field proof
as separate acceptance lanes.
