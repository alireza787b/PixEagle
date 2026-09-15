# Phase 5 Raspberry Pi CSI GStreamer Reconciliation

Date: 2026-09-15
Issue: PXE-0171
Status: implementation and local validation complete; target retest pending

## Scope

- Install and verify the Raspberry Pi libcamera GStreamer source when the
  optional OpenCV/GStreamer capability is selected.
- Reuse a matching OpenCV provider instead of rebuilding it for a missing
  system plugin.
- Request a defined processed format from the Raspberry Pi camera stack before
  converting frames to OpenCV BGR.
- Report precise CSI prerequisites through runtime media health.
- Align camera diagnostics with current Raspberry Pi OS Lite tooling.

## Decisions

- Full AI and CSI/GStreamer remain separate capabilities.
- Detection is based on Raspberry Pi device/OS identity and actual
  `gst-inspect-1.0 libcamerasrc` availability, not a distro version number.
- `gstreamer1.0-libcamera` is installed only when the element is missing on a
  detected Raspberry Pi. Jetson remains owned by its matching JetPack stack.
- The default Pi pipeline requests `NV12`, matching the documented libcamera
  processed-video path. Direct BGR remains an operator-owned pipeline override.
- Sensor discovery, GStreamer element availability, OpenCV integration, and
  usable PixEagle frames are separate evidence gates.

## Validation

```text
focused setup/reuse/video tests
152 passed

Pi pipeline and config migration follow-up
161 passed, 1 skipped

installer/profile/provider suite
257 passed

Phase 0 API inventory and parameter reload
73 passed

infrastructure documentation contracts
31 passed

schema
43 sections / 603 parameters, current

bash -n, ShellCheck --severity=warning, Python compilation, git diff --check
passed
```

The local host's managed OpenCV wheel correctly reports `GStreamer: NO`, so it
cannot provide target-camera evidence. The tester's Compute Module CSI frame
remains the target acceptance gate.

## Boundaries

- No physical camera, Raspberry Pi, PX4, SITL/HIL, flight, or field success is
  claimed by local tests.
- This change does not alter camera tuning, tracking, following, or control
  publication.
