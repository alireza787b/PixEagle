# Adding Control Types

Adding a control type changes the flight-command boundary. Treat it as a
cross-layer contract change, not a YAML-only extension.

## Required Changes

1. Define every command field in `configs/follower_commands.yaml`.
2. Add a control type with the exact MAVSDK method name.
3. Add one or more follower profiles whose `required_fields` form the complete
   atomic command snapshot.
4. Add the typed MAVSDK setpoint construction and dispatch implementation in
   `PX4InterfaceManager`.
5. Add safety mappings and canonical configuration for every flight-limited
   field.
6. Add runtime, evidence-contract, mock, SITL dry-run, and documentation tests.

Do not merge a schema declaration before its dispatch and safety paths exist.
The complete command schema is validated at startup and fails closed.

## Command Fields

The current schema supports finite numeric `float` fields:

```yaml
command_fields:
  my_new_field:
    type: float
    unit: "m/s"
    description: "Physical meaning and positive-axis convention"
    default: 0.0
    clamp: true
```

Runtime values may be Python `int` or `float`, excluding `bool`, and must be
finite. Numeric strings are rejected. Defaults and fixed limits follow the same
rule.

For a schema-local bounded value, use the implemented nested limit shape:

```yaml
command_fields:
  normalized_example:
    type: float
    unit: "normalized"
    description: "Normalized example command"
    default: 0.5
    limits:
      min: 0.0
      max: 1.0
    clamp: true
```

`limit_name` is not a supported command-schema property. Flight-control limits
must be added to the canonical safety configuration and
`classes.safety_types.FIELD_LIMIT_MAPPING`, with schema/default/config tests.

## Control Metadata

Declare the canonical control name and the exact MAVSDK setter implemented by
the dispatch adapter:

```yaml
control_types:
  my_control_type:
    mavsdk_method: "set_actual_mavsdk_method"
    description: "Concise command semantics"
    ui_display: "Operator Label"
```

The command-contract loader requires complete metadata and unique MAVSDK method
names. `SetpointHandler.get_mavsdk_method(control_type)` is the runtime/tooling
accessor; do not create another Python method-name catalog.

## Follower Profile

Every field sent by this control type is required on every publication:

```yaml
follower_profiles:
  mc_my_behavior:
    display_name: "MC My Behavior"
    description: "Operational behavior and vehicle assumptions"
    control_type: "my_control_type"
    required_fields:
      - field_a
      - field_b
      - field_c
    ui_category: "custom"
    required_tracker_data:
      - POSITION_2D
    optional_tracker_data: []
```

Optional command fields and partial snapshots are unsupported. A follower must
publish the exact `required_fields` set so an omitted value cannot retain an old
motion command. Optional tracker capabilities remain supported through
`optional_tracker_data`.

All tracker names must be members of `TrackerDataType`. Unknown names fail
schema loading rather than being logged and ignored.

## Dispatch Implementation

The PX4 adapter must:

- accept only the declared control type and exact field set
- reject missing, unexpected, boolean, string, NaN, and infinite values
- construct the matching MAVSDK setpoint type without zero/default substitution
- preserve documented units and frame/sign conventions
- return an explicit publication result
- remain behind connection-generation and command-readiness checks

Do not use `fields.get(name, 0.0)` at the final boundary. Missing fields are a
contract failure, not a zero command.

The YAML `mavsdk_method` value documents and exposes the implemented adapter;
it does not dynamically make an unsupported MAVSDK API safe or available.

## Factory Registration

Add the concrete follower implementation to `FollowerFactory._initialize_registry`
under the same active profile name. Removed names belong only in
`removed_profile_aliases` in `follower_commands.yaml`; the factory reads that
mapping through `SetpointHandler` and must not duplicate it.

## Validation

At minimum, add tests that prove:

- the complete YAML contract loads and the unsupported version fails
- field defaults/limits and runtime values are strictly typed and finite
- unknown tracker requirements and incomplete metadata fail closed
- runtime intents and strict SITL evidence use the same field/type validator
- the factory registry matches active profiles
- YAML dispatch metadata matches the actual MAVSDK adapter and mocks
- missing/extra fields never reach MAVSDK
- reset and rejected commands clear the last publishable intent
- successful and failed publication results are distinguishable in evidence

Run the focused follower and drone-interface suites, `bash scripts/check_schema.sh`,
and the SITL harness dry-runs. A real PX4/SITL claim additionally requires the
approved runtime evidence described in [Testing Without a Drone](testing-without-drone.md).

## Related Documentation

- [Follower Commands Schema](../05-configuration/follower-commands-schema.md)
- [SetpointHandler](../02-components/setpoint-handler.md)
- [Control Types](../03-protocols/control-types.md)
- [Safety Integration](../05-configuration/safety-integration.md)
