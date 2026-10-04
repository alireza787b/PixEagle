# QGC slice 4a: native normal following checkpoint

Historical checkpoint. Normal following later received local acceptance;
current remaining qualification is recorded in the
[v13 closeout](2026-10-02-qgc-4b4-v13-closeout.md).

Date: updated 2026-09-27. PXE-0178 remains in progress. The user has not yet tested
this slice; no aircraft-following or camera hardware acceptance is claimed.

PixEagle owns the follower and MAVSDK/Offboard command path. The native
integration now has a read-only profile/readiness resource and dedicated
profile-select, Start and Stop actions. Profile choices come from the registered
follower implementations and selected tracker output; persisted, effective and
active modes are reported separately. Start requires a verified aircraft,
current target/source guard, compatible profile, PX4 execution and the existing
Offboard preflight. It also requires fresh armed and in-air observations bound
to the verified UID and connection generation. The backend rechecks these on its flight-owner loop before
entry, after Offboard acknowledgement and before activation. Stop binds to a
captured active follow session or pending Start ID and aircraft UID, independent
of video. Cancellation unwinds partial startup. A changed command UID or
connection generation prevents cleanup commands to a rebound connection.

The API and scope rules are in
[native-following-operations.md](../../../../apis/native-following-operations.md).
The paired QGC [slice-4a checkpoint](../../../../../../qgroundcontrol-pixeagle/custom-pixeagle/SLICE-4A.md)
records its custom UI and build evidence.

Validation: 641/641 focused backend tests; 174/174 route/config/candidate
tests; schema 43 sections/606 parameters; fatal flake8 and `git diff --check`
passed. The final focused test XML and log are under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4-2026-09-26/`.
The exact official PX4 SIH image
`px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`
ran as `sihsim_quadx` in a private namespace. Router commit
`2362c620f483cef1edd574fb962a373a288e4b9e`, Mavlink2REST 0.11.25 and
MAVSDK Server 3.12.0 connected the PixEagle command and observation paths.
The stack uncovered and fixed real symbolic HEARTBEAT `base_mode` parsing and
stale initial MAVSDK Offboard setpoint issues. Logs under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4-2026-09-26/sih-live-v1/logs/`
record Offboard entry, 20 Hz publications, Stop into Hold, target-loss Stop,
pending-Start cancellation, and an armed/takeoff/follow/land cycle. Tracked
ground Start was refused; airborne Start succeeded; landed Start was refused.

Next: run the prepared operator checkpoint and review its logs.
The external Topotek Ethernet RTSP/SIP camera/gimbal path follows this normal
mode. Real aircraft, HIL and field testing remain separate.
