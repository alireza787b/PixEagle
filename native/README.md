# Native PX4 guidance — development checkpoint

This is the shared companion adapter for experimental native FW guidance,
including `gm_velocity_vector` and calibrated-image `fw_navigation_chase`.
It is **not installed or enabled by ordinary PixEagle
setup yet**. Existing multicopter following continues through MAVSDK.

PX4 owns coordinated turns, energy management, attitude/rate control and VTOL
transition. The adapter publishes navigation objectives, not a second TECS or
attitude controller. There must not be simultaneous MAVSDK and DDS command
publishers. VTOL admission remains closed: the accepted
[consolidation plan](../docs/followers/05-development/follower-consolidation-plan.md)
ends following on transition and requires a fresh Start afterward. The existing
phase-retaining prototype and cycle reports below are historical component
evidence; transition-preserving authority release remains S7 work.

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

The current gated prototype invalidates the old pursuit objective on a phase
change. It can
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

## Explicit SIH firmware builds

Ordinary multicopter following still uses MAVSDK. Its setup and runtime do not
require ROS, the native guidance adapter or a DDS Agent. The separate
`--target sih` builder skips all ROS dependency preparation and compiles PX4
firmware only. The firmware itself retains its normal PX4 module configuration.

`dependencies.lock.json` owns the firmware revision and immutable SIH compiler
and runtime image pins; `px4/extension.json` owns the reviewed patch and applied
file checksums. Use a separate, standalone checkout at that revision, initialize
the SIH target's locked submodule paths recursively, and apply the checked-in
patch. The builder rejects extra source changes, missing required submodules,
any initialized submodule at another revision, linked worktrees and Git object
alternates. Unused platform/simulator submodules may remain absent. It never resets or repairs
an operator's checkout. The earlier development cache contains unrelated
submodule changes and is not automatically accepted as a source build.

For a new checkout, from the PixEagle repository root:

```bash
PIXEAGLE_PX4_SOURCE="$HOME/.cache/pixeagle-sih-source"
git clone https://github.com/PX4/PX4-Autopilot.git "$PIXEAGLE_PX4_SOURCE"
git -C "$PIXEAGLE_PX4_SOURCE" checkout --detach "$(python3 -c \
  'import json; print(json.load(open("native/dependencies.lock.json"))["reference_px4_commit"])')"
git -C "$PIXEAGLE_PX4_SOURCE" submodule update --init --recursive -- \
  src/drivers/gps/devices src/lib/events/libevents src/lib/heatshrink/heatshrink \
  src/modules/mavlink/mavlink src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client
git -C "$PIXEAGLE_PX4_SOURCE" apply \
  "$PWD/native/px4/patches/0001-guidance-observation-and-owned-mode-handoff.patch"
```

With both pinned Docker input images already available locally:

```bash
python3 tools/build_native_guidance.py --target sih \
  --px4-source /path/to/verified-patched-PX4 \
  --prepare-only --output-dir reports/native-guidance/sih-prepared

python3 tools/build_native_guidance.py --target sih \
  --px4-source /path/to/verified-patched-PX4 \
  --output-dir reports/native-guidance/sih-built
```

Use a new evidence directory for each command. Preparation verifies and copies
source inputs, excluding existing build outputs; it does not invoke Docker.
Preparation also obtains the locked Micro-CDR source if it is absent from the
cache and verifies its commit, tag and clean state. This is the PX4 client's
ordinary C serialization dependency, not a ROS runtime or DDS Agent. The build
routes its upstream Git fetch to that verified local source.
The build compiles with `DONT_RUN=1 make px4_sitl_sih -j2` in the pinned
toolchain and passes the locked submodule paths through PX4's existing
`PX4_GIT_SUBMODULES` CMake setting, with network access disabled. A missing toolchain dependency or
attempted external download fails the build; no manifest is accepted as a
replacement for a successful compilation. BuildKit can reuse matching layers,
but the cached development executable is never imported into the build context.

The builder extracts `bin/` and `etc/` from a stopped compiler container without
starting it, preserving command aliases. It packages a separate minimal runtime
image and emits `sih-build-manifest.json`, its matching `packaged/` artifacts,
source/submodule provenance and compiler/runtime build logs. The manifest binds
the recipe, firmware/extension pins, executable and ROMFS hashes to the immutable
image ID and image labels. It declares response and hardware qualification false.

The shared `tools.sih_isolated_host.host()` accepts an explicitly supplied
`args.sih_build_manifest` path. It verifies the bundle and locally available
image before creating run evidence, then launches that immutable ID. Run evidence
records the selected manifest checksum and firmware provenance. Callers must
forward this optional argument; no environment override or monkeypatch is needed.
An invalid supplied manifest fails closed. Without it, the existing pinned image
remains the explicitly labeled `compatibility_image` baseline.

This recipe and its deterministic mock build/manifest tests do not establish
that a fresh compiler build or its SIH response has passed. A real source build,
followed by the unchanged qualification gates against that built image, remains
required before adopting a new default. Legacy SIH profile/CI repository-digest
requirements are unchanged by this builder.

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

`observe.attitude_timing` optionally exports the accepted attitude's publication
and sample timestamps, separate monotonic publication/first-sample receipts, and
PX4 quaternion-reset counter. The existing wire `aircraft_state` is unchanged;
new Python clients attach validated timing locally, with missing/null timing
remaining `None`. PX4's XRCE serializer adjusts both source timestamps by its
session offset: their within-packet difference measures processing age, but they
are **DDS-adjusted microseconds, not raw boot time or host monotonic time**.
Repeating a sample cannot renew its first receipt. Timing export alone does not
qualify camera exposure alignment; calibrated-bearing guidance remains gated
until its clock/skew and latency uncertainty are bounded. No interpolation or
automatic transition continuation is enabled by this metadata.

## Qualification status

Linux x86-64 compilation, contracts, sanitizers, live SIH DDS observations and
an initial airborne FW controller probe have passed. The controller probe
confirmed native course response, continuous publication and observed loiter.
This is **not full follower or VTOL qualification**.

Calibrated image-input native FW components also pass four moving-target airplane
cases on clean PixEagle `3cb7a8355`: altitude hold, target-directed descent,
one-second loss/reacquisition and eight-second loss expiry. Every case confirms
Hold with no later publication. Exact source/config/firmware identity, parameters
and browser-checked replays are retained under
`reports/sitl/follower-consolidation-20261111/fw-navigation-image-*/`.
Pixels come from explicit synthetic optics and actual PX4 observations, not a
physical tracker. `fw_navigation_chase` stays live-gated; calibration alone does
not qualify physical capture/attitude timing. The
[consolidation checkpoint](../docs/reporting/agent-ops/codex-modernization/checkpoints/2026-11-09-follower-consolidation.md)
records current scope and remaining gates.

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

Two normal FlowController/HTTP sessions now passed on the SIH airplane with
a vertical-mount SIP/RTSP camera fixture: verified telemetry/identity, native
start, temporary EAS controls, target loss/reacquisition and confirmed Stop.
A recovery reduction constrains retained commands before the existing native
envelope resolver. Evidence and interactive replays are in
`reports/sitl/native-vector-application-20261107/`. This qualifies the tested
application path with fixtures, not real camera or VTOL application acceptance.

Still required: VTOL application/session qualification, standard VTOL,
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
