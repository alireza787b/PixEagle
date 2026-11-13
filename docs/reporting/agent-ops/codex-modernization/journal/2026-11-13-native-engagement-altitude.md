# Native engagement-altitude hold candidate

The operator selected explicit engagement-altitude hold when target-altitude
guidance is disabled. This addresses the distinction exposed by the retained
vertical no-pitot loss-expiry capture: active MC height error exceeded 2 m while
the follower and native receiver were requesting zero vertical velocity. The
estimator-level cause remains unconfirmed; the original failed evidence and
the 2 m acceptance requirement are unchanged.

Private adapter protocol 4 carries one typed, finite AMSL reference and native
reference generation captured before acquisition. Startup and native MC
horizontal-velocity/vertical-position pursuit use that same reference. Retarget,
loss decay, restoration and schema staging preserve it. Explicit altitude-on
pursuit retains its vertical-rate contract. Freshness, identity and reference
resets are checked before publication; terminal neutral release does not retain
the pursuit anchor. PX4 supplies the altitude controller, with no additional
application PID, gain tuning or horizontal speed redistribution.

The paired Python/C++ candidate remains under component and simulator
qualification. [The native guide](../../../../../native/README.md) describes the
wire and transport boundaries. Ordinary MAVSDK MC still uses its existing
body-velocity path; it is not claimed to hold engagement altitude. Public VTOL
application admission, request-time phase/intention fencing, unrestricted FW
behavior, deployment and hardware acceptance remain open. No saved public or
private profile, firmware patch, board or service changed in this slice.

The requested [Ubuntu training platform](../../../../followers/05-development/ubuntu-training-platform.md)
has a staged plan around the normal application stack. Rendered camera images,
manual synthetic 2D observations and emulated gimbal angles remain distinct
input/evidence modes. It has not been implemented or demonstrated yet.
