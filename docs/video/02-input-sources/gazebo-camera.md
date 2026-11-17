# Gazebo training camera

`GAZEBO_CAMERA` reads actual rendered RGB images and their original Gazebo
sample timestamps from the isolated training launcher. Tracking and QGC receive
the same pixels through the ordinary PixEagle pipeline. It does not synthesize
targets, control the simulator or qualify a physical camera.

Use the [Ubuntu training workflow](../../followers/05-development/ubuntu-training-platform.md).
The launcher selects the pinned aircraft/world and fills `VideoSource.GAZEBO_CAMERA`:

| Field | Meaning |
| --- | --- |
| `socket_path` | Private local image-provider socket |
| `source_clock_id` | This launch's world/clock incarnation |
| `world`, `image_topic` | Exact declared camera source |
| `max_attitude_skew_s` | Maximum source-time mismatch permitted for a qualified bearing; initially 0.05 s |

Ordinary installations leave this object `null`. Setup requires no Gazebo
packages unless using the simulator. The provider runs in the pinned simulator
image; the backend uses its normal Python/OpenCV runtime.

Images carry source time separately from backend receipt. Bounded framing and a
latest-image slot prevent an accumulating queue. Disconnection, changed source,
reordered samples or invalid geometry cannot produce a fresh measurement.
Cached display images retain their original identity and time.

Camera calibration and camera-to-aircraft time association are separate gates.
Receiving an image does not authorize fixed-wing following. Never pair an
unrelated decoded RTP frame with a metadata FIFO or label host receipt as camera
exposure time. Public camera/tracker/follower and safety defaults stay unchanged.

For native FW image guidance, the matching adapter exposes the original PX4
attitude sample and the launcher's verified common-clock identity. The resolver
uses an actual retained sample within `max_attitude_skew_s`; it never substitutes
the latest DDS-adjusted quaternion. Diagnostics report `bounded_source_time` and
the measured mismatch. Missing, stale or cross-clock evidence remains unavailable.
Retargeting resets the image association without resetting flight recovery budgets.
