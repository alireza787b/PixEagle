# Companion Computer Setup

This guide covers the maintained Core-first setup contract for a Debian-family
Linux x86_64 or ARM64 companion computer. Raspberry Pi 5 with 64-bit Raspberry
Pi OS is the first ARM handoff target. Jetson images and accelerators require a
separate platform-matrix result; architecture detection alone is not evidence
that an image is supported.

## Deployment Boundary

A companion computer may run video capture, tracking, PixEagle, MAVSDK,
MAVLink2REST, and a routing service. Keep ownership explicit:

- PixEagle owns its application runtime and optional systemd service.
- MavlinkAnywhere or another reviewed router owns MAVLink routing.
- PX4 owns flight-mode and onboard failsafe behavior.
- The operator owns network exposure, credentials, abort authority, and
  hardware/field acceptance.

Do not combine those services in an ad hoc startup script. Do not treat a
successful browser demo as PX4, SITL, HIL, or field readiness.

## Raspberry Pi 5 First-Time Setup

Use 64-bit Raspberry Pi OS, enable SSH during imaging if remote administration
is required, boot the board, and update the base OS:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

After reconnecting, obtain the reviewed 40-hex PixEagle commit from the release
or tester handoff and use the source-pinned path:

```bash
export PIXEAGLE_COMMIT='<reviewed-40-hex-commit>'
installer="$(mktemp)"
curl --proto '=https' --tlsv1.2 --fail --show-error --location \
  "https://raw.githubusercontent.com/alireza787b/PixEagle/${PIXEAGLE_COMMIT}/install.sh" \
  --output "$installer"
PIXEAGLE_COMMIT="$PIXEAGLE_COMMIT" bash "$installer"
rm -f "$installer"
git -C "$HOME/PixEagle" rev-parse HEAD
```

The printed and queried `HEAD` must equal the handoff commit. The installer
stages and verifies a detached exact-commit checkout before making the final
directory visible. Do not substitute a tag, branch, or abbreviated hash.

For an isolated beginner lab only, the mutable-main convenience path remains:

```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

It is intentionally labeled lab/development by the installer and is not RPi
acceptance or deployment provenance.

Choose **Core** for the first pass. Core is the default on every architecture
and provides the dashboard, classic OpenCV trackers, MAVSDK/MAVLink2REST
integration, and setup diagnostics without the AI dependency footprint. Review
the final component summary before starting a workflow.

For a browser test on an isolated lab LAN:

```bash
make quick-browser-demo LAN_HOST=<companion-lan-ip>
```

The command asks for a username/password (Enter keeps the beginner admin/admin
login), prints the URL, and writes an owner-only credential handoff. Finish the
bench session with the exact cleanup command it prints. See
[Setup Profiles](../../setup/setup-profiles.md) before exposing any service
outside a trusted lab network.

## Optional Capabilities

Add only the capability required by the target workflow.

### SmartTracker AI

```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
```

Then add a trusted detect/OBB model and prove an actual bounded load. Follow
[SmartTracker Model Setup](../../MODEL_SETUP.md). Do not use global `pip`,
unreviewed Jetson wheels, or a model file from an untrusted source.

### GStreamer Input Or QGC UDP Output

```bash
bash scripts/setup/build-opencv.sh
make check-gstreamer-runtime
```

This is not required for dashboard HTTP/WebSocket/WebRTC media. Follow
[OpenCV With GStreamer](../../OPENCV_GSTREAMER.md) before enabling
`VideoSource.USE_GSTREAMER` or `GStreamer.ENABLE_GSTREAMER_STREAM`.

### dlib Tracker

```bash
bash scripts/setup/install-dlib.sh
```

## PX4 And MAVLink

Connect and route MAVLink using the reviewed infrastructure guide rather than
opening PixEagle application ports broadly:

- [Hardware connection](hardware-connection.md)
- [MavlinkAnywhere](mavlink-anywhere.md)
- [Port configuration](port-configuration.md)

For a serial interface, add the runtime user only to the device-owner group
used by the OS (commonly `dialout`) and reconnect the session:

```bash
sudo usermod -aG dialout "$USER"
```

Do not solve device access with world-writable permissions. Confirm the actual
device path and group with `ls -l /dev/serial/by-id/` or the platform-specific
camera/serial inventory before changing access.

## Camera Bring-Up

List V4L2 devices and inspect the selected node:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --all
```

Use the schema-backed Settings/config workflow to select a video source. For a
GStreamer/CSI pipeline, first prove the pipeline independently, build the
optional OpenCV provider, then enable the corresponding PixEagle source. Camera
names, indexes, formats, and Jetson/Raspberry Pi pipelines are host-specific;
do not copy a pipeline without validating it on the target image and sensor.

## Managed Service (Optional)

The beginner/lab path does not install boot auto-start. On a reviewed standalone
systemd deployment host:

```bash
sudo bash scripts/service/install.sh
sudo pixeagle-service enable
sudo pixeagle-service start
pixeagle-service status
```

The generated service is Linux/systemd-specific and reports success only after
the exact supervised runtime publishes readiness. Platform-managed user units
and the standalone system unit are mutually exclusive. See
[Service Management](../../SERVICE_MANAGEMENT.md).

## Host Configuration

Static addressing, Wi-Fi access points, VPNs, firewalls, power profiles,
thermal limits, swap, and overclocking belong to host operations. PixEagle does
not apply them automatically. Record any such change in deployment evidence and
validate temperature, throttling, storage endurance, network loss behavior, and
reboot recovery on the actual board.

Do not disable host services, overclock hardware, add broad firewall rules, or
change swap merely because a generic guide suggests it.

## Verification Order

1. `make init` completes with the intended profile summary.
2. `make run` or the managed service reaches exact runtime readiness.
3. A local/demo video source renders and tracker start/stop/loss behavior passes.
4. Optional AI/GStreamer checks pass only if those capabilities are selected.
5. MAVLink routing and telemetry are verified without Offboard control.
6. SIH/SITL scenarios validate control and failsafe behavior with evidence.
7. HIL/field work proceeds only under an approved test plan and operator abort
   path.

Useful diagnostics:

```bash
pixeagle-service status
pixeagle-service logs -n 200
bash scripts/setup/check-ai-runtime.sh
make check-gstreamer-runtime
```

Only run diagnostics for installed/selected capabilities. Keep exact commands,
versions, configuration redactions, and resulting artifacts with the handoff.
