# PXE-0074: v7 Stable Local/Demo Baseline

After the beta.1 through beta.32 acceptance cycle, the maintained installation,
configuration, dashboard, typed API, streaming, Classic/Smart control,
command-preview, lifecycle, and evidence contracts are promoted to `v7.0.0`.

The promotion is deliberately scoped. Stable describes the tested local/demo
software baseline and its compatibility contracts. It is not a claim that
PixEagle is certified avionics or that Raspberry Pi performance, PX4/Pixhawk
response, follower behavior, camera/gimbal integration, QGC receipt,
SIH/SITL/HIL execution, field safety, or aircraft operation has passed.

The exact software candidate passed `3,611` maintained non-hardware backend
tests with `47` expected platform/dlib skips and one deselected external marker,
Phase 0 `492`, dashboard `57` suites / `379` tests, the production build, schema
`39/518`, generated API provenance, Python compile, shell syntax, Markdown link,
and diff checks.

The next phase is evidence collection on Raspberry Pi and representative
PX4/Pixhawk, follower, camera/gimbal, and simulation configurations. Reports
must include exact versions, configuration, commands, and sanitized logs.
