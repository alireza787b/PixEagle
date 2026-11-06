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

## Reproduce the software build

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

## Qualification status

Linux x86-64 compilation, contracts, sanitizers, live SIH DDS observations and
an initial airborne FW controller probe have passed. The controller probe
confirmed native course response, continuous publication and observed loiter.
This is **not full follower or VTOL qualification**.

Still required: application/session publisher integration, moving-target
following, both VTOL transition directions and abort/rescue cases, native
unrestricted-speed policy and expiry tests, ARM64 packaging, reusable 3D
evidence and operator acceptance. The unrestricted capability remains false.
Public defaults and the private platform's tested MC profile are unchanged.
The registered Vector follower now accepts the tested internal phase/session
binding and the shared publisher provides its phase-observation hook. Automatic
application startup and service provisioning do not enable them yet.
See the [active checkpoint](../docs/reporting/agent-ops/codex-modernization/checkpoints/2026-11-06-gimbal-vector-airframes.md)
for precise gates and evidence locations.
