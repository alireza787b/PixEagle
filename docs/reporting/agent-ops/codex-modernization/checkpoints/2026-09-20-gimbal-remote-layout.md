# PXE-0172: Compact gimbal controller layout

Date: 2026-09-20. Branch: `feat/optional-gimbal-control-bench`.
Scope: optional dashboard presentation. Hardware testing remains paused.

## Result

A bounded UI/frontend agent review recommended a directional pad, separate roll
and zoom groups, and explicit Stop/Cancel actions. Implemented pan/tilt arrows
with Center camera in the middle, paired roll icons and a vertical zoom rocker.
Controls retain provider capability gating and fixed directional positions.
Classic/Smart uses compact segmented buttons; Movement retains its existing
presets and Adjust dialog. Persistent tracker/hold instruction paragraphs were
removed. Errors and following-block explanations remain visible.

Movement icons have accessible action names, hover/focus tooltips, visible
keyboard focus and 44×44 minimum touch targets. Touch tooltips are disabled to
avoid interfering with hold gestures. The existing hold handlers remain on the
actual buttons, including the active-button exception during pending requests.
Stop and Cancel target stay separate and labeled. The Stop label is shortened
visually while its accessible name remains Stop camera. No camera protocol,
axis mapping, provider settings, hold timing, or default enablement changed.

## Files and verification

- `dashboard/src/components/GimbalControlPanel.js`: controller layout and names.
- `dashboard/src/components/GimbalControlPanel.test.js`: removed instructional
  copy expectations; existing capabilities, guards and operations still checked.
- `docs/trackers/02-reference/gimbal-tracker.md`: updated operator reference.
- This checkpoint, journal, issue register and evidence record the slice.

Dashboard: 62 suites / 471 tests passed, including 42 panel/hold checks.
Production build and `git diff --check` passed. No Python/config changes in this
slice, so the preceding backend/schema validation was not rerun.

Production Chrome checks cover widths 320, 390, 768 and 1280: directional layout,
44-pixel controls, no mobile horizontal overflow, mouse/touch/keyboard hold and
release, single taps and custom settings. All action endpoints are intercepted;
status uses a saved fixture. Zero camera commands are forwarded by these checks.
Screenshots contain only the panel/dialog, not the camera's room view. This is
browser evidence, not native OS or physical-camera qualification.

[Evidence and reproduction](../evidence/2026-09-20-gimbal-remote-layout/README.md).

## Remaining camera work

The [partial horizontal session](2026-09-20-gimbal-horizontal-acceptance.md)
records limited physical pan/hold evidence before the operator paused testing.
Next, resume in normal horizontal mounting with a steady base and clear distant
target: confirm the final UI controls, Classic click/rectangle, retarget and
Cancel. Then separately test the intended base-pitched-up 90° installation.
Vertical mounting/follower mapping and AI candidate identity remain unqualified;
no automatic axis swap has been introduced. No flight tests or PR publication
were performed in this slice.
