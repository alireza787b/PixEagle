# Camera-v28 acceptance and publication/deployment sequence

## Checkpoint

The operator accepted the final vertical-mounted Ethernet camera workflow on
2026-10-04. The backend profile uses camera-owned tracking, manual camera
controls, Vector coordinated-turn following, bounded recovery, altitude safety
and a command-blocked startup with isolated PX4 SIH. This is bench acceptance,
not real-flight or Raspberry Pi qualification.

Saved private evidence under
`~/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/camera-final-v28/` contains:

- 796 successful Offboard publication records, no failed publication records;
  794 contain Vector intents and two contain no startup intent.
- 10 successful target actions and 81 successful camera actions; validation
  entries are counted separately from successful executions.
- Native follow Start/Stop successes and continuity ACTIVE/COASTING/REACQUIRING.
- The authenticated integration connection request after QGC sign-in.

The log does not demonstrate an active Chase follow session. Physical
camera/process/network failure motor behavior and optimum guidance gains remain
unqualified. Preserve the operator acceptance separately from these trace claims.

## Work remaining

1. Close physical camera failure/load checks, including actual motor Stop
   behavior, coordinated with the operator; retain software lease/dispatch gates.
2. Finish portable dependency provisioning, source/configuration provenance,
   regression and release-issue resolution. Preserve unrelated edits and the
   clean original PixEagle main worktree.
3. Prepare reviewed PixEagle main and customized QGC fork candidates separately.
   Backend/Dashboard/schema/defaults/compatibility/rollback evidence gates the
   PixEagle candidate. Customized QGC stays unreleased; Windows/Android and
   installer qualification are additional QGC gates, not evidence for backend CI.
4. Inventory and back up the actual Pi/router/PX4/camera platform before approved
   deployment. Verify authenticated network access, dual-interface routes,
   service supervision, hardware acceleration and recovery.
5. Run the onboard ground checkpoint with circuit breaker enabled, Dashboard
   Follower Test preview, zero PixEagle aircraft-control dispatch and sustained
   temperature/memory/frame-age/network measurements. Flight is later scope.

The detailed cross-repository plan is kept in the QGC integration worktree at
`custom-pixeagle/NEXT-CHECKPOINTS-2026-10-04.md`.

## Defaults versus robot profile

Public factory defaults remain video-file/CSRT/PixEagle engine, no gimbal,
GStreamer off, yaw-only `mc_velocity_position`, altitude safety enabled and
circuit breaker on. Installation values remain in the existing canonical
PixEagle configuration, editable through Dashboard/Config Sync.

The user's explicitly commissioned robot profile uses Pi Ethernet
`192.168.0.226/24`, camera `192.168.0.108/24`, Wi-Fi Internet access, qualified
GStreamer RTSP input, camera engine/controls, **VERTICAL** mounting and Vector
coordinated-turn guidance. Altitude command generation is disabled for that
profile; safety/freshness/abort protections remain enabled during commissioning.
The requested 2 m/s starting speed is a tuning objective requiring aligned
limits and separate SIH/ground evidence, not a change to public defaults or
flight authorization. Preserve internal service ports and require the reviewed
authenticated remote deployment/restart policy. No credentials are published.

## Validation and provenance

This checkpoint changes documentation only. The backend code remains at the
v28 snapshot derived from `a379190` with its captured file hashes. Profile
read-only validation and startup passed; QGC client discovery regression and
build passed before the handoff. Exact camera acceptance is tied to the QGC
binary checksum in its handoff rather than subsequent documentation-only HEADs.
No backend main merge, source push, service installation or artifact publication
was performed by this checkpoint.
