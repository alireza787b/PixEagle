# SIH guidance visualizer checkpoint — 2026-10-24

## Phase

Reusable read-only SIH guidance visualization and evidence alignment.

## Delivered

- Versioned YAML scenarios for vertical Vector, horizontal rearward-crossing
  Vector, and ordinary 2D camera chase.
- Evidence reader for PX4 pose, target truth, tracker-command, Offboard publish,
  and follower-state JSONL records.
- Self-contained HTML playback that opens in an isometric 3D NED scene, with
  prominent `TARGET NOW` and `PX4 NOW` markers, independently selectable
  dashed history paths, adjustable history opacity, current line of sight,
  attitude-aware command intent, state badges, timeline, view toggles, and a
  validation summary.
- CSV, JSON, and static PNG exports.
- GET-only live MAVLink2REST pose polling with bearer-token support.
- Deterministic horizontal and vertical catch-up fixtures showing requested
  speed above target speed and observed range closure without hardware access.
- Validation flags for stale/gapped evidence, limits, altitude-disabled down
  commands, requested/effective speed, yaw sign changes, unsupported states,
  and yaw-first translation.

## Validation

- `123` focused SIH/visualization/docs tests passed.
- Python compilation passed for the new reader and CLI.
- Generated HTML JavaScript passed `node --check`.
- Synthetic output smoke test produced `index.html`, `summary.json`,
  `trace.json`, `trace.csv`, and `summary.png`.

## Evidence boundary

The synthetic report proves alignment and rendering behavior. It does not claim
PX4 response, camera tracking, HIL, or field performance. A live report is
accepted only when it includes fresh PX4 pose records and the corresponding
validated command/publication artifacts.

## Next checkpoint

Run the visualizer against a command-blocked SIH evidence directory for both
horizontal and vertical mounts, then review target motion, actual PX4 pose,
command vectors, state transitions, gaps, and constraint flags before any
aircraft-connected test.
