# 2026-10-02 — v12 findings and v13 follower closeout

Implemented the approved selection-transaction, shutdown, timing/filtering and
measurement-freshness repair. Invalid camera selections are prepared/refused
before target generation or ownership mutation. Session-owned shielded teardown
retains the first cause even if a requesting client disconnects. Final selection
commit also refuses application shutdown.

Both gimbal followers now use bounded monotonic timing, validated body-line-of-
sight filtering and final command slew, with altitude restrictions applied
after smoothing. Actual submitted commands determine recovery distance.
Fresh defaults scope 8-second/4-metre bounded recovery to the two gimbal
followers; saved policies retain explicit Config Sync adoption. QGC retains
the accepted layout with consistent phases and aircraft-bound handoff history.

The combined gates and isolated synthetic-observation/PX4 response evidence are
recorded in the [checkpoint](../checkpoints/2026-10-02-qgc-4b4-v13-closeout.md).
Raw AI reviews remain separate from pending physical operator acceptance.
Private v13 preparation keeps aircraft commands blocked and starts no services.
No publication, main-branch update or real-aircraft qualification is claimed.
