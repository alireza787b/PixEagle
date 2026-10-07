# Pi/Pixhawk bench audit and 7.3.0 source closeout

The operator connected a motorless Pixhawk to the existing Pi camera bench and
authorized configuration inspection and cleanup. No arming, Offboard start,
setpoint, aircraft movement or camera movement was requested by this audit.

## Live evidence

- The Pi ran clean backend `main` at `b5ac7b1`, with the PixEagle service active
  and enabled and no systemd restarts in the inspected boot.
- Authenticated backend reads succeeded. MAVLink2REST telemetry was fresh;
  the vehicle reported disarmed. MAVSDK and MAVLink2REST exposed the same
  nonzero aircraft UID, and native association reported verified.
- Camera/GStreamer, camera-owned tracking, manual camera control, vertical
  installation and `gm_velocity_vector` remain an explicit private profile.
  Expensive OpenCV/GStreamer and installed model dependencies were preserved.
- Flight-command blocking was off at audit start. The existing authenticated,
  generation-guarded circuit-breaker action enabled it while following was
  inactive; both runtime and saved state then confirmed active. No aircraft
  command was sent.
- An obsolete MAVLink Anywhere dashboard unit had hundreds of restart attempts
  because its executable and configuration directory were missing. Its unit
  and enabled state were backed up before disabling that broken dashboard.
  The working MAVLink router, PixEagle dashboard and owned MAVSDK/telemetry
  processes remained active. This is a board-specific cleanup, not a new
  installer default or a removal of the router.

Private network addresses, SSH credentials, account secrets and raw board
logs are excluded from this public checkpoint. Board backup is under the
operator's private `~/.local/state/pixeagle/bench-audit-20261007` directory.

## Backend correction and source version

The periodic system log used an obsolete `px4_interface.connected` property,
so it incorrectly displayed disconnected even when the authoritative API
reported connected. It now uses `get_connection_status()`. A regression test
checks both canonical states while a conflicting legacy property is present.
This corrects observation only; it does not change command admission.

Backend and dashboard version metadata move together to 7.3.0, with matching
setup metadata and release notes. Existing factory defaults and private
installation overrides remain unchanged. The QGC integration remains a
private qualification artifact and has its own source/version provenance.

## Validation and boundaries

107 status/route/config/documentation tests and 211 Offboard safety regression
tests passed. Schema validation, Python syntax and setup shell syntax checks
passed. The PR retains hosted backend, dashboard and Windows-preview gates.
Merge, tagging and release provenance are recorded by GitHub after those gates.

These results establish read-only connection/identity evidence for this bench,
not real flight, closed-loop guidance quality or complete onboard ground
qualification. The final operator check must still cover vehicle power/link
cycling, authenticated video/tracking recovery and explicit Stop behavior.
