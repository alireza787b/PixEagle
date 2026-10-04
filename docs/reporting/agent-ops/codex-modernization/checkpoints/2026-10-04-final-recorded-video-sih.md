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

Fresh profile:

`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/recorded-smart-final-v24`

The Full-AI interpreter loaded `visdrone9m.pt` and the Smart runtime produced
live detections from `test9.mp4` on this CPU-only host. Attempts to submit a
selection when the detection snapshot and displayed frame had diverged were
rejected by the native `frame_context_invalid`/`no_detections` guards. This is
expected safety behavior and is not recorded as a successful Smart selection.
The fresh QGC operator session is the acceptance path for clicking a visible
detection on the actual displayed frame. Its logs remain in the profile.

An unused command-blocked v25 profile is prepared for that session:

`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/recorded-smart-final-v25`

The host's CUDA-unavailable fallback is recorded; no model, tracker threshold,
or stale-frame guard was changed to force a pass. Existing prior Smart
selection evidence remains valid for the earlier profile and is not relabeled
as this run.

## Remaining gates

The camera-free software/SIH gate is ready for operator review. Physical camera
loss/Stop behavior, constrained radio/Pi load, Windows/Android artifacts, the
Linux package dependency retry, and the command-blocked Pi/router/PX4 ground
test remain open. No credentials are included in this checkpoint.
