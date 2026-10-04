# Final recorded-video/SIH gate — 2026-10-04

This checkpoint records the last camera-free qualification run before physical
camera and onboard Pi work. It does not claim visual closed-loop convergence,
camera motor behavior, flight safety, or real-aircraft qualification.

## Longer-video SIH result

Fresh profile:

`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/recorded-sih-final-v22`

The profile used bundled `test11.mp4`, local CSRT, bounded target recovery,
`mc_velocity_chase`, altitude safety and the circuit breaker initially enabled.
The immutable command-blocked startup probe observed a simulated PX4 identity.
The authenticated probe then acquired a current frame, took the simulator off,
started following after the guarded circuit-breaker transition, and stopped.

Results:

- 169/169 Offboard publications succeeded.
- Independently observed simulated yaw changed by −163.93°.
- Stop completed with `confirmed_hold`.
- Cleanup restored the circuit breaker, stopped tracking/following and landed the
  simulator.

The result and correlated traces are in the profile's `logs/` directory,
including `recorded-sih-publish-result.json`, `tracker-command.jsonl` and the
publisher trace. The recorded image is independent of SIH pose, so the run
proves command delivery and simulated response only.

## Smart model result and boundary

Fresh automated profile:

`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/recorded-smart-final-v26`

The Full-AI interpreter loaded `visdrone9m.pt` and the Smart runtime produced
live detections from the longer `test11.mp4` on this CPU-only host. A native
probe selected a target from the exact delivered JPEG (`match: exact`),
recorded the selected bounding box, and stopped tracking successfully. The raw
probe log is retained under the profile's `logs/` directory.

An unused command-blocked v27 profile is prepared for the operator session:

`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/recorded-smart-final-v27`

The host's CUDA-unavailable fallback is recorded; no model, tracker threshold,
or stale-frame guard was changed to force a pass. Existing prior Smart
selection evidence remains valid for the earlier profile and is not relabeled
as this run.

## QGC regression and package evidence

The renewed custom QGC Unit/Integration run passed **414/414 tests** with the
standard Flaky/Network exclusions. The log is retained outside the repository
at `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/qgc-final-path-corrected.log`.

The Linux Release DEB was generated with CPack after supplying the pinned
`libxcb-cursor0` library as a private dependency-search path and explicitly
declaring `libxcb-cursor0` in the package dependencies. The host package is
not installed, so local installation/launch remains unverified.

## Remaining gates

The camera-free software/SIH gate is ready for operator review. Physical camera
loss/Stop behavior, constrained radio/Pi load, Windows/Android artifacts, the
Linux package dependency retry, and the command-blocked Pi/router/PX4 ground
test remain open. No credentials are included in this checkpoint.
