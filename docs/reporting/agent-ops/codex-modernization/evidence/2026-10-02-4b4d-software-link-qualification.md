# 4b.4d camera-free software link and load evidence

Date: 2026-10-02. This is automated software evidence; it is not operator or physical-camera acceptance. No production source/configuration was changed for these tests. No existing containers, physical camera, or aircraft were used or stopped.

## Reproduce

```bash
cd /home/alireza/PixEagle-qgc-integration
.venv/bin/python tools/qualify_camera_link.py --output /tmp/pixeagle-camera-link-evidence
```

Use a fresh output directory. The harness starts only owned ephemeral loopback HTTP listeners, uses the documented synthetic-camera fixture account, and stops its own threads/listeners. The fake camera provider cannot create UDP/vendor/camera sockets. HTTP authentication, CSRF, action/idempotency guards, runtime arbitration and the independent manual executor are production implementations. No secrets are emitted.

The manifest records the exact pytest arguments, Python/package versions, source hashes before/after, observed timings and limitations. Changing a measured source during execution invalidates the run. The dirty integration tree is based on `989d9662173b364de03b307f4208e9d0ca96451f`; the manifest hashes identify tested edits that are not represented by that base revision alone.

## Results

Final run: **64 passed**, 19.26 seconds. Fatal Python lint passed for the two new files. Test-hygiene gate: **4 passed**. Two existing Starlette/httpx deprecation warnings were reported; no production failure was observed.

Evidence directory:
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-02/link-combined-final/`

| Scenario | Observed evidence |
|---|---|
| Real authenticated HTTP; 100 ms renewal with scheduled 20/60/40 ms sender delays | 14 updates accepted; maximum admission gap 147.8 ms; maximum HTTP round trip 16.7 ms |
| Same schedule with isolated dropped updates 5 and 9 | 12 accepted; maximum admission gap 219.6 ms; no unintended expiry |
| Burst loss/client ceases transmission | Stop dispatched 369.9 ms after last accepted renewal; late request refused with HTTP 409; zero motion after expiry |
| Reordered update 2 then 1; Stop 4 then delayed update 3 | Responses 202/409/202/409; no obsolete reversal or motion after Stop |
| Release during delayed tracking-disable takeover | Final state stopped; no motor-intent dispatch; delayed renewal refused |
| Second client attempts replacement during an active gesture | HTTP 409; original gesture retained; zero replacement motion |
| Real HTTP Stop with capture owner blocked | 0.69 ms from route receipt to mock Stop dispatch; HTTP round trip 44.9 ms |
| Real HTTP Stop with inference owner blocked | 0.82 ms from route receipt to mock Stop dispatch; HTTP round trip 45.2 ms |
| Existing authenticated ASGI blocked-owner expiry tests | 352.4 ms capture / 360.4 ms inference; unchanged 350 ms lease; both below 400 ms gate |
| Production FlowController flight thread and OffboardCommander; capture owner blocked | 12 fake-PX4 publications at 20 Hz; maximum publication gap 50.3 ms |
| Same flight path; inference owner blocked | 12 publications; maximum gap 50.4 ms |

The 100 ms Stop criterion is measured from entry into the camera action facade, separately from transport/middleware round trip. The HTTP-delay schedule affects request creation/transmission timing on the sender. It does not emulate an entire radio or shared video/control link. The blocked-owner tests use a waiting gate, not an actual AI workload or CPU starvation.

## Bounded media and stale provider evidence included in the same run

The harness reuses narrow existing cases rather than repeating whole suites:

- WebSocket render acknowledgement permits one outstanding frame and prevents sampling the next frame before acknowledgement.
- Capture-ring pressure from 19 frames preserves the explicitly delivered selection, then releases it when its client releases ownership.
- Slow JPEG encoding preserves the sampled selection's exact token; a source change during encoding cannot deliver the retired frame.
- Seven packet-receiver cases show interleaved tracking/angle packets, status-only packets, and wall-clock changes cannot rejuvenate stale angles or tracking observations.
- Reprocessing fresh video preserves the actual camera angle timestamp, monotonic receipt and sequence.
- Provisional retarget guidance rejects pre-selection/stale packets, prior providers, disconnected runtime, pending camera dispatch and manual takeover.
- Continuity watchdog and OffboardCommander unit tests retain loss/handoff, default-on-expired intent, connection-generation, bounded publication failure and intentional shutdown behavior.

These cases establish software ownership/freshness/backlog properties. Fake JPEG transport and fake PX4 send results are not physical-link or SIH vehicle-response evidence. The separate v13 SIH evidence remains the actual simulated-vehicle delivery/response record.

## Operating envelope and remaining 4b.4d work

For this host/run, 100 ms renewals with the tested delay pattern and isolated misses remained active; a burst gap exceeding the unchanged lease stopped the gesture rather than extending its lifetime. This is a deliberately small documented envelope, not a minimum supported bandwidth specification.

Still open:

1. A rate-limited shared media/control link, sustained bandwidth contention and longer random delay/drop/jitter runs.
2. Full QGC real transport input/ack/timeout behavior on that link, application suspension and reconnection.
3. Pi CPU/memory/thermal pressure with actual capture, local Smart inference and encoder load.
4. Physical Pi-to-camera UDP loss/disconnect, process death, device watchdog behavior and actual motor stopping. A successful UDP Stop transmission alone cannot close this gate.
5. Camera v13 operator retest and later onboard ground qualification.

No lease was extended, no gain changed, and no UI setting was added to mask a bad link. No additional UX review is implied by this software-only checkpoint.
