# Native Windows Status

Native Windows is an experimental contributor path. It is not a maintained
PixEagle installation, service-lifecycle, media, AI, or release-validation
target. Use WSL 2 or a maintained Debian-family Linux host for normal setup.

The retained PowerShell and batch files fail closed unless the operator sets:

```powershell
$env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS = "1"
```

That flag acknowledges missing parity; it does not make the host production
ready. In particular, the Linux ownership-aware tmux supervisor, systemd
service contract, `/proc` process identity checks, `flock` serialization,
GStreamer builder, and target-board evidence do not apply natively on Windows.

The retained experimental binary downloader still uses
`scripts/setup/binary-manifest.env`, verifies SHA-256 before publication, and
does not probe fallback release tags. See the
[Binary Download Policy](setup/binary-download-policy.md); this provenance
check does not establish native-Windows runtime support.

Contributors working on native support must provide all of the following before
this status can change:

1. isolated dependency installation and rollback evidence;
2. exact process ownership, stop, restart, and port-conflict tests;
3. dashboard/backend and supported media transport tests;
4. binary provenance and checksum validation;
5. CI on the supported Windows versions;
6. a clean-checkout setup walkthrough and an explicit capability matrix.

The separate [Windows/X-Plane SITL disposition](WINDOWS_SITL_XPLANE.md) records
the current manual simulation boundary. Neither document is evidence of native
Windows, SITL, HIL, or field readiness.
