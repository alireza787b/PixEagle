# PXE-0141: Degraded Control-Plane Startup

An unavailable RTSP source previously blocked synchronous application
construction while several nested GStreamer and OpenCV probes ran. Launcher
readiness then removed the backend and dashboard, leaving the operator without
Settings, Logs, health, or a reconnect action.

The backend API now starts before one bounded video-source activation. Capture
reads are serialized separately from lifecycle transitions, allowing
reconnect/release to retire a capture blocked in backend I/O and discard any
late frame. Failed captures are released; manual reconnect runs off the API
event loop and cannot claim success from a stale cached frame. Typed
runtime/about status includes sanitized startup capability state.

Runtime ownership now requires the dashboard and backend control plane while
classifying MAVLink2REST and MAVSDK as degradable sidecars. Combined and
separate tmux layouts retain exited optional panes for exact diagnosis. Runtime
launch does not install missing dependencies or prompt for downloads. Invalid
core configuration, authentication, API bind/ownership, and flight-command
safety contracts remain hard failures.

Local tests and a process-level unavailable-source probe are the current
evidence boundary. Ubuntu RTSP-failure acceptance, Raspberry Pi, physical
camera/gimbal, PX4, and field behavior remain unproven.
