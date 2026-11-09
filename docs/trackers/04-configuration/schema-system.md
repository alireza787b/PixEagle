# Tracker schema system

Tracker declarations live in `configs/tracker_schemas.yaml`. Follower
requirements live in `configs/follower_commands.yaml`; the shared
`follower_catalog.py` evaluator derives eligibility from them. Maintain these
different responsibilities without a second compatibility matrix.

## Measurement declarations

Every data type declares its observation representation and field requirements:

```yaml
tracker_data_types:
  POSITION_2D:
    representation: image_position
    name: "2D Position Tracking"
    category: position
    required_fields: [position_2d]
    optional_fields: [confidence, bbox, normalized_bbox, velocity]
    validation:
      position_2d:
        type: tuple
        length: 2
        element_type: float
        range: [-2.0, 2.0]
```

The current representations are `image_position`, `angular_bearing`,
`provider_angles` and `external`. A field's name alone cannot change its
measurement meaning. For example, synthesized coordinates attached to provider
angles are not image measurements.

Required fields are guarantees; optional fields are not. A tracker may explicitly
promise a selected-target field from its primary schema:

```yaml
tracker_types:
  SmartTracker:
    data_type: MULTI_TARGET
    following_required_fields: [position_2d]
```

This promise concerns command-usable selected-target output. Every actual sample
is still validated. Do not infer guarantees from the union of
`supported_schemas`, or turn a bounding box into a position without a declared
adapter. Generic MULTI_TARGET and BBOX_CONFIDENCE schemas do not guarantee a
selected image position.

## Follower requirements and eligibility

A follower profile declares `required_tracker_data`, operator family/visibility,
command fields and supported native phase contracts. It does not list tracker
class names. The evaluator compares representation first, then required fields.

Selection requires declared guarantees. Runtime input checks actual presence,
shape and finite values. Thus a real optional image position may be usable in a
runtime sample without making that generic schema statically suitable for
selection. Provider angles and unclassified external fields remain incompatible
with image followers.

Input compatibility does not grant following authority. Target evidence,
freshness, aircraft identity/kind, live admission and command ownership remain
separate checks. See the [schema and extension guide](../../developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md)
for the typed catalog and compatibility projections.

## Installation geometry

Gimbal installation belongs to canonical `GimbalTracker` configuration and
`gimbal_geometry.py`, not tracker-schema mount descriptions. The old descriptive
mount maps and test-only default were removed. Do not recreate them here or add
implicit pixel-to-angle conversions. Use the
[gimbal geometry guide](../../followers/04-configuration/gimbal-guidance.md).

## Extension workflow

1. Reuse a data type only when its actual representation and required fields fit.
2. For a new type, update `TrackerDataType` and its schema together.
3. Register the implementation in the existing tracker factory and declare its
   primary `data_type`, UI metadata and any selected-target guarantee.
4. Test active, missing, stale, malformed and source-replaced output through the
   shared evaluator and real tracker tests.
5. Update the relevant reference and qualified evidence; schema registration
   alone does not establish aircraft response.
