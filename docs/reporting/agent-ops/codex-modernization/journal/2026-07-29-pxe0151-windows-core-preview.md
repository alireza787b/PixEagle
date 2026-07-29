# PXE-0151: Native Windows x64 Core Preview

Date: 2026-07-29
Status: native authenticated CI passed; clean-host operator evidence pending

## Decision

Native Windows will not be described as equivalent to the maintained Linux
runtime. The bounded candidate is Windows 11 x64 with CPython 3.11/3.12,
Node 24, Core dependencies, bundled video, classic CSRT/KCF tracking, and an
authenticated loopback-only dashboard/backend. Guided setup asks for the
browser account and Enter keeps `admin/admin`; repair preserves a valid
existing account.

The candidate media surface includes HTTP JPEG, WebSocket JPEG, and WebRTC
signaling/transport. Native CI now proves that bounded surface; a clean-host
operator run remains required.

## Documented Contract

- `scripts\init.bat` owns idempotent Core setup, reuses only validated Python,
  npm, and dashboard-build contracts, applies the canonical loopback
  `browser_session` profile, and preserves the existing credential hash.
- Setup and runtime start use one PowerShell ACL authority to protect and
  verify the credential directory/file for the current Windows SID.
- `dashboard\package-lock.json` remains authoritative and setup uses `npm ci`;
  stale advice to delete the lockfile is retired.
- `scripts\run.bat`, `status.bat`, `stop.bat`, and `restart.bat` use one
  per-checkout process receipt and never kill an unknown port owner.
- Optional `--with-sidecars` acquisition is limited to manifest-pinned MAVSDK
  Server and MAVLink2REST binaries. The preview does not start them because
  MAVSDK Server cannot scope its unauthenticated gRPC listener to loopback.
- Model management remains explicitly unavailable while the POSIX artifact
  trust policy has no Windows equivalent. That capability must not prevent the
  Core control plane from starting.

## Excluded

AI/model management, NCNN/dlib, custom GStreamer, Windows services/auto-start,
ARM64, camera hardware, public exposure, PX4/SITL/X-Plane/Offboard/HIL, field,
and aircraft operation remain unsupported or unvalidated.

## Native Evidence

Authenticated candidate `c4b2c319` passed GitHub Actions run
[`30445705976`](https://github.com/alireza787b/PixEagle/actions/runs/30445705976)
on Windows Server 2022 with CPython 3.12 and Node 24. The user-facing
`install.ps1` path established the `admin/admin` default, verified owner-only
credential ACLs, and preserved the exact credential-file SHA-256 on repeated
setup. Native contracts passed `64` with `2` platform-applicability skips.
HTTP JPEG, WebSocket JPEG, and WebRTC each decoded a 640x480 frame before and
after an owned restart.

The pre-auth baseline at `090744f5` passed native run `30442509410`, including
decoded HTTP JPEG, WebSocket JPEG, and WebRTC before and after restart. The
authenticated candidate passes `465` local contracts with `9` expected native
skips, the focused Windows subset passes `36` with `5` native skips, required
API/parameter gates pass `73`, and schema/static/diff/CRLF gates pass. None of
those results substitutes for the remaining clean Windows 11 operator
walkthrough. CPython 3.11 also needs a separate run before receiving the same
evidence claim as 3.12.
