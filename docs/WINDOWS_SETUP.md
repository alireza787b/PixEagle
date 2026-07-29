# Native Windows x64 Core Local-Lab Preview

Native Windows is an opt-in preview, not a maintained PixEagle release target.
Use WSL 2 or a maintained Debian-family Linux host for normal installation,
companion-computer work, and any workflow beyond the local lab described here.

The preview is a candidate until both native Windows CI and a clean-host
operator walkthrough provide retained evidence. The commands below describe
the candidate implementation; they are not evidence of Windows, PX4, SITL,
HIL, or field readiness.

## Candidate Scope

| Area | Preview boundary |
|------|------------------|
| Host | Windows 11 x64 |
| Python | CPython 3.11 or 3.12 x64 |
| Dashboard | Node.js 24.x and npm 10 or 11 |
| PixEagle profile | Core only |
| Video | Bundled looping video |
| Tracking | Classic CSRT and KCF |
| Network | Dashboard and backend on loopback only |
| Media | HTTP JPEG, WebSocket JPEG, and WebRTC signaling/transport; native CI and operator evidence pending |
| Lifecycle | Per-checkout process receipt with exact PID/create-time identity, readiness checks, and owned stop/restart |

The Core backend remains available when model management is unavailable.
Model inventory reports that capability boundary instead of preventing the
dashboard from starting.

## Not Supported Or Validated

The preview does not support or validate:

- Full AI, model upload/management, Ultralytics, or SmartTracker;
- NCNN, dlib, or a custom GStreamer/OpenCV build;
- Windows services, boot auto-start, or background deployment management;
- Windows ARM64;
- USB, CSI, RTSP, gimbal, or other camera hardware;
- LAN or public exposure, TLS termination, firewall automation, or remote
  browsers;
- PX4, SIH/SITL, X-Plane, Offboard, HIL, vehicle response, field use, or
  aircraft operation.

The separate [Windows/X-Plane SITL disposition](WINDOWS_SITL_XPLANE.md)
records that simulation path. It is not part of this preview.

## Prerequisites

Install these x64 tools and reopen the terminal so they are on `PATH`:

1. Git for Windows.
2. CPython 3.11 or 3.12 from python.org. Enable the Python launcher or add
   Python to `PATH`.
3. Node.js 24.x. The dashboard accepts npm 10 or 11.
4. Windows PowerShell 5.1 or newer. PowerShell is required only for optional
   pinned sidecar acquisition.

The preview intentionally does not install system packages, drivers, CUDA,
PX4, a simulator, or a Windows service.

## Set Up

From `cmd.exe` in a PixEagle checkout:

```cmd
set PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1
scripts\init.bat
```

In PowerShell, set the same opt-in for the current process:

```powershell
$env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS = "1"
.\scripts\init.bat
```

Setup creates or reuses `.venv`, validates the Core dependency contract,
creates `dashboard\.env` only when needed, installs dashboard dependencies
with `npm ci`, builds the dashboard, and reconciles config metadata. Matching
validated Python dependencies and dashboard artifacts are reused.

The preview launcher fails with an actionable error if an existing config uses
a camera/network source, non-loopback bind, non-local auth mode, or disabled
streaming. Reset those settings to the documented local Core profile before
starting; the preview does not silently rewrite an operator config.

Do not delete or regenerate `dashboard\package-lock.json`. It is the checked-in
dependency contract used by `npm ci`.

Optional MAVSDK Server and MAVLink2REST downloads are offered separately and
default to No. To acquire both explicitly:

```cmd
scripts\init.bat --with-sidecars
```

The downloader uses `scripts\setup\binary-manifest.env`, verifies SHA-256 and
the x64 PE format before publication, writes
`bin\binary-provenance.jsonl`, and does not probe fallback release tags.
This proves acquisition provenance only. The preview does not start either
sidecar because upstream MAVSDK Server cannot bind its unauthenticated gRPC
endpoint to loopback. It does not prove MAVLink routing, PX4 discovery,
simulator behavior, or vehicle control. See the
[Binary Download Policy](setup/binary-download-policy.md).

If an exact receipt-owned preview runtime is active, setup refuses to mutate
dependencies. Stop it first, or explicitly let setup stop that owned runtime:

```cmd
scripts\init.bat --stop-runtime
```

Setup never terminates an unknown process to clear a port.

## Run And Manage

The default start is the local bundled-video Core lab. It does not start PX4
sidecars:

```cmd
scripts\run.bat
scripts\status.bat
scripts\stop.bat
```

Open `http://127.0.0.1:3040`. The backend remains on
`http://127.0.0.1:5077`.

Restart performs an owned stop followed by the same readiness-checked start:

```cmd
scripts\restart.bat
```

The pinned sidecar files are retained for a future PX4/SITL design and manual
expert investigation. Native sidecar process orchestration is outside this
preview.

To print the active component log paths:

```cmd
.venv\Scripts\python.exe scripts\windows\runtime.py logs
```

To verify the dashboard and decode one frame from each local media transport:

```cmd
.venv\Scripts\python.exe scripts\windows\smoke.py
```

Each lifecycle command validates the saved executable, process creation time,
and command identity before acting. A stale receipt is removed without
terminating an unrelated process. A required port owned by another process is
reported and left untouched.

## Media Evidence Boundary

The candidate starts the same loopback backend and dashboard used by the Core
runtime. Its intended local browser media surface includes HTTP JPEG,
WebSocket JPEG, and WebRTC signaling/media transport.

Do not interpret endpoint readiness as decoded-frame evidence. Acceptance
still requires native Windows CI and an operator run that records browser
receipt for each transport. WebRTC on another device, firewall traversal,
NAT/TURN, HTTPS/WSS, and public access are outside this preview.

## Acceptance Required

Native Windows remains a preview until all of these gates pass on the exact
candidate revision:

1. Windows 11 x64 Core setup with CPython 3.11 or 3.12 and Node 24.
2. Repeated setup proving safe reuse of matching dependency/build contracts.
3. Start, status, restart, stop, stale-receipt, and unrelated-port ownership
   tests.
4. Dashboard/backend readiness and decoded local HTTP JPEG, WebSocket JPEG,
   and WebRTC browser evidence.
5. A clean-host operator walkthrough with logs and exact versions.

Passing these gates would establish only the stated Core local-lab scope.
Every unsupported capability above needs its own design and evidence before it
can be advertised.
