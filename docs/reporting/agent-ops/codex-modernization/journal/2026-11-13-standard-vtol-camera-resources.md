# Standard VTOL camera resource preparation

Added the explicit `standard-vtol-mono-camera-courtyard-v1` scenario: unchanged
stock airframe 4004 and aircraft resources, one pinned fixed-camera wrapper,
and an offline static training world. The camera contributes its existing
0.05 kg payload; no controller, firmware, defaults or admission policy changed.
The schema extension retains strict old scenarios and the exact stock builder.

Validation and source pins are recorded under
`reports/sitl/follower-consolidation-20261111/software-gates-training-standard-vtol-camera-r1/`.
The selected suite passed 793 checks, including 153 camera-scenario cases;
schema, critical lint and diff checks passed. The normal builder validator
and actual packaged-resource replay also passed using read-only image inspection.
This is resource preparation, with no simulator/build/render/flight action.
The [domain notes](../../../../../native/gazebo-build.md#standard-vtol-camera-courtyard-resource-preparation-only)
record poses, resource closure, payload impact and remaining calibration,
native Start-fence and live-admission prerequisites. Next: independent source
review, then an explicitly authorized disarmed rendering/identity check.
