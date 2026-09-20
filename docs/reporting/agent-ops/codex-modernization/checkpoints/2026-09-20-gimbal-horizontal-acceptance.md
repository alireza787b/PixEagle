# PXE-0172: Partial horizontal camera acceptance

Session: 2026-09-20, 03:01:45–03:08:38 UTC. Branch:
`feat/optional-gimbal-control-bench`, baseline
`463fbbc5acbc107d32cffc6c85cc3670923016ee` with uncommitted integration changes.
Standalone camera only; following remained off. No aircraft, SITL or HIL test.
The operator paused hardware testing before this session was completed.

## Results and limits

- The live browser held Pan right and Pan left for approximately 650 ms each.
  Each hold issued three Fine pulses (5°/s, 150 ms). Release requested Stop;
  no additional movement request followed release. In-flight responses could
  complete afterward, as expected for bounded pulses.
- Recorded image features moved approximately −13.98 px horizontally during
  Pan right and +10.80 px during Pan left, consistent with the intended view
  directions. These relative measurements include possible base movement and
  do not establish a mount transform or encoder calibration.
- Six individual pan/tilt/roll probes returned successful command-path results
  and issued Stop. Tilt image shifts reversed between directions; one positive
  roll probe produced about −0.288° image rotation. Base/pose changes and other
  recorded movement prevent treating this as complete axis qualification.
- Before the final negative roll pulse, telemetry already read approximately
  yaw 96.59°, pitch −50.31°, roll −8.83°. The later close view and large pose
  change therefore cannot be attributed to that final pulse alone. Three
  additional tilt pulses appear in the wire record; their origin is not
  established by these probe records.
- Camera image rotation read back `ROT02`. PixEagle's isolated bench display
  used zero additional rotation. Rotation readback is not mounting validation.
- The Classic rectangle browser script timed out finding the Protocol control
  **before drawing or sending a target selection**. Its cleanup successfully
  canceled tracking and requested Stop. The locator was subsequently changed,
  but the revised script was not run. No rectangle tracking success is claimed.

The last connected cleanup status reported tracking disabled and following off,
with a successful Stop response. At 03:08:38 UTC, saved status reported camera
unavailable, tracking unknown and following off. That disconnected snapshot does
not establish a current physical motor state. Hardware testing remained paused.

## Evidence and provenance

[Evidence index](../evidence/2026-09-20-gimbal-horizontal-acceptance/README.md)
contains typed requests/results, bounded wire history, capture event records,
image-motion measurements and hashes for private frames. Room images remain
under ignored `reports/` and are not copied into documentation.

The software tested precedes the subsequent remote-layout redesign; see the
[movement-controls source and validation record](2026-09-20-gimbal-movement-controls.md).
Two archived harness files include post-run edits: `axis_pulse.py` gained a
horizontal pose guard after the probes, and `browser_box.cjs` contains the
unexecuted locator fix. Event records are authoritative for actual execution.

This documentation slice changes only this checkpoint and its evidence folder.
JSON/JSONL parsing, copied artifact hashes and document whitespace were checked;
no new hardware or application tests were performed while assembling it.

## Remaining acceptance

After the operator resumes, inspect the current scene and mount before any
commands. Remaining checks include Classic click/rectangle, retarget and Cancel;
Smart candidate identity; the remaining movement presets, axes, zoom and Home;
and the intended base-pitched-up 90° installation. Both installation forms need
measured axis behavior before any shared mounting transform or follower remap
can be qualified. Do not reuse the archived rectangle coordinates blindly.
