# PXE-0139: Gimbal Live-Switch Lifecycle

Real-camera testing proved RTSP playback and Classic tracking but exposed a
runtime Gimbal selection failure. The switch created `GimbalTracker` without
starting its provider listener, so the always-reporting loop received null
output and emitted one warning per video frame.

The repair centralizes external provider activation in AppController, requires
successful monitoring before a live switch is published, restores the previous
tracker after activation failure, and makes inactive Gimbal state structured.
The saved tracker-default Settings field is now a dropdown generated from the
canonical tracker catalog, with explicit startup/restart semantics separate
from the live Tracker-page selector.

Local tests are the current evidence boundary. The next bounded action is the
operator's real Topotek packet and angle-display check; no gimbal follower or
PX4 claim is made before that result.
