# Follower initialization follows the declared input contract

Live Start converted `tracker.normalized_center` even for gimbal observations,
which intentionally have no image coordinates. Preview substituted the configured
center when an initial image measurement was missing. Both paths now use one
resolver driven by `required_tracker_data`: image consumers require the selected
finite image pair, and angle-only consumers receive `None`. Direct factory and
wrapper calls share the same validation. Existing target/source readiness,
circuit-breaker, telemetry and command ownership checks remain in place.

Regression coverage includes both gimbal profiles and target modes through live
and preview Start, real follower construction, every declared image profile,
missing/malformed/nonfinite pairs, typed measurements differing from legacy
tracker fields, and rejection before mode acquisition. These are software tests;
no simulator, flight or hardware action was performed.

Validation: 3,928 core-App, follower, factory and API route-inventory checks
passed, including parameter-reload checks; 35 documentation/test-hygiene checks,
schema synchronization, critical Python lint and diff hygiene passed. The review
packet is `reports/sitl/follower-consolidation-20261111/software-gates-s7-follower-image-initialization-r1/`.

The VTOL admission gate remains closed. Before promoting it, pending Start must
be tested and fenced across a complete intervening phase transition: the current
API source/aircraft guard does not bind request-time phase history. Native
preparation pins its subsequently observed initial phase, which does not by
itself prove that earlier request remained current. That separate issue is not
changed by this initialization fix.
