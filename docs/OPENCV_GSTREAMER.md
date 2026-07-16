# OpenCV With GStreamer

Most PixEagle users do not need a custom OpenCV build. Core tracking, OSD, and
dashboard HTTP/WebSocket/WebRTC media use the normal OpenCV provider.

Build OpenCV with GStreamer only when the selected workflow requires one of
these schema-backed features:

| Feature | Configuration | Custom OpenCV required |
|---------|---------------|------------------------|
| GStreamer camera/input pipeline | `VideoSource.USE_GSTREAMER: true` | Yes |
| H.264/RTP/UDP output for stock QGroundControl or another receiver | `GStreamer.ENABLE_GSTREAMER_STREAM: true` | Yes |
| Dashboard HTTP, WebSocket, or WebRTC video | Streaming transport settings | No |
| Direct HTTP/WebSocket support in an experimental QGC build | Streaming transport settings | No |

The UDP output remains useful for stock QGroundControl and generic GStreamer
receivers. Experimental QGC HTTP/WebSocket support does not obsolete it.

## Maintained Build Path

The maintained builder supports the PixEagle Debian-family Linux x86_64/ARM64
bootstrap target:

```bash
bash scripts/setup/build-opencv.sh \
  --report-json "${XDG_STATE_HOME:-$HOME/.local/state}/pixeagle/setup-evidence/opencv-gstreamer.json"
make check-gstreamer-runtime
```

The builder fetches each exact version tag into a new owner-only bare repository,
requires that the tag peel to the pinned OpenCV and opencv_contrib commits,
matches both exports against checked-in archive and canonical-tree SHA-256
digests, validates each archive before extraction, and builds outside both source
trees. Git hooks, inherited Git configuration, persistent checkouts, and
caller-selected work roots are excluded from this path. The same PixEagle
virtual environment used by setup is changed only after compilation and staged
installation succeed.

The tag, archive, exported source trees, CMake inputs, downloads, install
manifest, and loaded runtime are fingerprinted in the requested owner-only JSON
report. This is stronger source provenance, not a signed source release or a
byte-reproducible build claim: Debian packages, GStreamer/FFmpeg libraries,
NumPy, compiler, linker, and host toolchain remain outside the hash lock. The
private `/var/tmp/pixeagle-opencv-build.*` work root is removed after bounded
evidence is collected; interrupted roots are never reused as build input.

The report destination is owner/type/write checked before dependency changes or
the long build. If cleanup or evidence publication nevertheless fails after the
verified OpenCV replacement is committed, the command reports
`installed_cleanup_failed` or `installed_evidence_failed` and states that the
new runtime was retained; it does not imply a rollback that did not happen.

The default is a headless companion build. A development host that truly needs
OpenCV GTK/OpenGL windows may opt in:

```bash
OPENCV_GUI=1 bash scripts/setup/build-opencv.sh
```

The build requires at least 10 GB free and 6 GB combined RAM/swap. It does not
change host swap by default. A lab-only temporary build swap can be explicitly
enabled for one invocation:

```bash
OPENCV_ALLOW_TEMP_SWAP=1 bash scripts/setup/build-opencv.sh
```

Provision production swap through normal host management instead.

## Interaction With Core And AI Setup

The Core profile's `opencv-contrib-python-headless` requirement is the explicit
non-GStreamer companion fallback. On a fresh managed environment, select it with:

```bash
PIXEAGLE_INSTALL_PROFILE=core make init
```

`make init` and `scripts/setup/install-ai-deps.sh` use the same provider probe.
One managed contrib wheel is valid: the Core profile selects the headless wheel,
while an intentionally customized desktop environment may use
`opencv-contrib-python`. A source provider is preserved only when it is inside
the selected venv and has contrib trackers, FFmpeg, and GStreamer. Multiple
owners, base-only wheels, and unmanaged non-GStreamer overlays fail closed. The
exact source-provider fingerprint must remain unchanged across setup.

For a managed wheel, the provider probe verifies every non-bytecode file in the
sole wheel RECORD, including native `.libs`, and rejects RECORD mismatches,
stale or foreign OpenCV metadata owners, unowned `cv2` overlays, symlinks, and
paths outside the selected venv. For a source provider it fingerprints the
complete `cv2` tree and source-installed OpenCV library/include/CMake/pkg-config/
tool layout, including the content reached by native-library symlinks.

In-place source-to-wheel replacement is intentionally unsupported because pip
cannot prove it removed every native source-install target. Create a fresh venv
for the Core wheel instead. A failed source build never triggers an automatic
wheel fallback.

NCNN is unrelated to OpenCV GStreamer and remains opt-in. See
[SmartTracker Model Setup](MODEL_SETUP.md).

## Verification

Use the selected environment, not a global Python:

```bash
bash scripts/setup/check-ai-runtime.sh
make check-gstreamer-runtime
```

The first report identifies the imported OpenCV path/version, contrib tracker
APIs, FFmpeg, and GStreamer build flag. The second also verifies the GStreamer
plugins required by the QGC UDP path. These local checks do not prove that a
remote QGC/VLC/GStreamer receiver obtained usable video; record a receiver-side
test separately.

Keep the generated `setup-evidence/opencv-gstreamer.json` with target-host setup evidence. Its
fingerprints identify what loaded on that host; they are not a substitute for a
receiver test, complete package lock, or reproducible-build attestation.

## Third-Party Licensing Review

OpenCV, GStreamer core and plugin sets, FFmpeg, codecs, hardware drivers, and
their binary packages have separate upstream licensing and notice terms. The
operator or distributor is responsible for reviewing the exact components and
media/codecs selected for the intended deployment. Start with the
[OpenCV license](https://opencv.org/license/) and
[GStreamer licensing guidance](https://gstreamer.freedesktop.org/documentation/frequently-asked-questions/licensing.html),
then inspect the target distribution's package notices. PixEagle does not make
a legal determination for a deployment.

Native Windows and macOS source builds are not maintained by this guide. Do not
use an unreviewed third-party build recipe as PixEagle production evidence.
