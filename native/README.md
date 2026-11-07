# Native PX4 guidance — development checkpoint

This is the companion adapter for the experimental FW/VTOL extension to
`gm_velocity_vector`. It is **not installed or enabled by ordinary PixEagle
setup yet**. Existing multicopter following continues through MAVSDK.

PX4 owns coordinated turns, energy management, attitude/rate control and VTOL
transition. The adapter publishes navigation objectives, not a second TECS or
attitude controller. A single native owner handles the entire VTOL session;
there must not be simultaneous MAVSDK and DDS command publishers.

| Boundary | Contract |
| --- | --- |
| Backend → adapter | Private, same-UID Unix socket; versioned JSON; one session and expiring command lease |
| FW → PX4 | Course in NED, equivalent airspeed, and either AMSL altitude or upward-positive height rate |
| VTOL MC → PX4 | NED velocity and yaw rate |
| Transition → PX4 | Both native FW and MC setpoints for the already observed transition; no transition request |
| PX4 → backend | Observed phase, full physical-body quaternion, velocity, relative/home altitude, qualified airspeed and native envelope |
| Handoff → PX4 | Compare the observed mode and activation timestamp before changing mode; reject delayed cleanup after takeover |

`dependencies.lock.json` pins the firmware baseline, ROS interface, message
definitions, DDS Agent and logging dependency. The reviewable firmware patch
is in `px4/patches/`. It adds native envelope/home-reference observations and
conditional mode changes. It does not enable unrestricted speed or alter
normal controller gains, limits, global parameters or underspeed protection.

Native FW-frame heading and forward-axis observations come from PX4 after its
own tailsitter attitude conversion. Physical attitude remains unchanged for
camera rays and MC heading-frame commands. A stale/incompatible FW frame cannot
be replaced by MC yaw. No camera mount is changed during a VTOL transition.

## Reproduce the software build

At phase changes the adapter invalidates the old pursuit objective. It can
publish phase-appropriate holding setpoints under the same unexpired lease
until the backend binds the new generation. This does not renew the lease,
extend target recovery, or survive takeover/rescue.

From the PixEagle root, with Docker available:

```bash
python3 tools/build_native_guidance.py \
  --output-dir reports/native-guidance/build \
  --px4-source /path/to/patched-pinned-PX4
```

The source checkout must be the pinned revision with the complete extension
applied. Use a separate simulator checkout; never modify archived evidence or
flash hardware as part of this build. The tool verifies archive checksums and
message compatibility. `--prepare-only` checks sources without building Docker.

The image builds the adapter and runs native contract and sanitizer tests. It
does not start an aircraft, install a service or acquire control. ARM64
packaging and normal setup/service integration remain qualification gates.

## Read-only observations

Start the adapter in the isolated SIH environment after the DDS Agent and PX4
are available. The socket's parent must be owned by the adapter user and not
writable by other users. Registration does not arm or select the native mode.

```bash
pixeagle-native-guidance --ros-args \
  -p socket_path:=/private/runtime/guidance.sock

PYTHONPATH=src python3 tools/native_guidance_probe.py \
  --socket /private/runtime/guidance.sock \
  --aircraft-uid VERIFIED_UID --connection-generation CONNECTION \
  --telemetry-generation 1 --duration-s 10 \
  --output reports/native-guidance/observations.jsonl
```

The probe sends only `hello`, `bind` and `observe`. It rejects a different
aircraft UID and never calls engage, intent, handoff, arm or transition.
Reordered or duplicate packets cannot refresh measurements. Source ages,
missing prerequisites and actual publication counts remain visible in
diagnostics. Missing pose stays unknown; commands are never integrated into a
fabricated aircraft trajectory.

PX4 sends changed VTOL status immediately and unchanged status at 1 Hz. Its
freshness budget includes that sample interval plus the configured native
`status_timeout_s` delivery allowance. Vehicle ownership and high-rate pose
retain their existing deadlines. `phase_source_health` exposes actual ages and
budgets; duplicate or reordered packets cannot refresh them. MC/transition
envelope observations use the native unloaded minimum-speed reference, while
settled FW retains the performance model's bank/load-dependent minimum. An
upright tailsitter's singular FW bank angle cannot become an MC speed limit.

Snapshot `sequence` represents aggregate progress from accepted source packets,
including phase status. It is not a position timestamp. Phase can change before
the next pose sample; the oldest measurement-receipt time remains unchanged and
still determines measurement freshness. Polling cannot advance either clock or
sequence. Original PX4 pose timestamps remain in the pose trace.

## Qualification status

Linux x86-64 compilation, contracts, sanitizers, live SIH DDS observations and
an initial airborne FW controller probe have passed. The controller probe
confirmed native course response, continuous publication and observed loiter.
This is **not full follower or VTOL qualification**.

The normal-envelope FW component matrix now has actual moving-target response
for horizontal/vertical mounts with altitude guidance off/on. Its four runs
confirmed Hold, no publication after Stop, and bounded observed altitude
response. The interactive report is retained at
`reports/sitl/native-vector-fw-matrix-20261107/index.html`; it does not qualify
the HTTP/App startup path, VTOL transitions or real aircraft. An idle adapter
FMU-request timeout after those sessions is retained for supervisor qualification.

Normal-envelope `sihsim_xvert` component cycles also passed for both mounts:
MC → transition → FW → transition → MC, one owner, preserved MC request,
785 successful submissions per case, observed Hold and no publication after
Stop. Maximum altitude deviations were 1.244/1.407 m against an unchanged 2 m
gate. The simulator's `VT_ARSP_TRANS` was explicitly raised from 7 to its native
minimum of 10 m/s; this is not an aircraft-profile change. The comparison,
failed attempts and interactive replays are in
`reports/sitl/native-vector-vtol-matrix-20261107/`.

The shared continuity registry binds FW recovery to `PX4_NATIVE`, supplied by
the native session binding rather than inferred from the public execution-mode
label. MAVSDK FW recovery remains unsupported. The development SIH loss runner
uses the same supervisor and publisher; it cannot bypass ownership or renew
the eight-second deadline.

Six actual-PX4 FW loss cases passed for both mounts, with altitude guidance
off/on. Reacquisition retained 0.5 s confirmation and restoration; genuine loss
expired after 8.007 s without an MC travel limit. A paused companion process
caused native Hold after 347 ms; delayed cleanup preserved pilot RTL with no
later publication. Replays, raw traces and the pre-enablement refusal are in
`reports/sitl/native-vector-recovery-20261107/`. These are component checks,
not complete application or real-aircraft qualification.

Still required: actual-PX4 application/session qualification, standard VTOL,
abort/rescue, target-loss/retarget and takeover cases, native
unrestricted-speed policy and expiry tests, ARM64 packaging, reusable 3D
evidence for the remaining airframes and operator acceptance. The unrestricted capability remains false.
Public defaults and the private platform's tested MC profile are unchanged.
The application now binds the registered Vector follower, one native command
transport and the existing continuity supervisor. An observed FW/VTOL selects
the native owner throughout the session; pure MC retains MAVSDK. No ordinary
setup/service provisioning installs the development adapter yet. Startup uses
the canonical `/run/pixeagle/guidance.sock`; isolated protocol probes retain
their explicit socket argument.
Stop joins the existing publisher before native handoff and never calls MAVSDK
Offboard Stop for that owner. Failed handoff retains unresolved cleanup state.
Immediate operator Stop still revokes the socket without waiting for I/O. After
the publisher joins, read-only observations can confirm the resulting Hold or
preserved pilot mode using the same aircraft UID, adapter runtime and a newer
mode epoch. An old Hold cannot satisfy confirmation. No second mode command or
Follow replay is sent; unavailable confirmation leaves cleanup unresolved.
Obsolete MAVLink Offboard-exit notifications cannot revoke a newer native mode;
native observations remain authoritative for takeover/rescue/expiry.
See the [active checkpoint](../docs/reporting/agent-ops/codex-modernization/checkpoints/2026-11-06-gimbal-vector-airframes.md)
for precise gates and evidence locations.
