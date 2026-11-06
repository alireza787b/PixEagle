# Native fixed-wing envelope and command outcome, for external navigation modes.
# Read-only: no value in this message changes controller configuration.

uint32 MESSAGE_VERSION = 0

uint64 timestamp # [us] Publication time since system start
uint64 timestamp_sample # [us] Local-position observation used by the controller
uint64 parameter_revision # [us] Time of latest native parameter resolution
uint64 nav_state_timestamp # [us] Time the current navigation mode was activated
uint64 autopilot_uid # Same legacy hardware UID as MAVLink AUTOPILOT_VERSION
uint64 firmware_git_hash # Native firmware git version, for runtime provenance
uint8 nav_state # [enum VehicleStatus.NAVIGATION_STATE] Observed mode
float32 home_altitude_amsl # [m] Current estimator/home altitude reference; not terrain clearance
uint32 home_update_count # Changes when the native home reference changes
bool home_altitude_valid

float32 minimum_equivalent_airspeed # [m/s] Native load/flap/weight-dependent minimum, before course/wind adjustments
float32 trim_equivalent_airspeed # [m/s] Native trim including weight/altitude dependencies
float32 maximum_equivalent_airspeed # [m/s] Configured native maximum
float32 climb_rate_limit # [m/s] Native maximum climb rate at current density
float32 sink_rate_limit # [m/s] Native maximum sink rate
float32 vertical_acceleration_limit # [m/s^2] Native vertical acceleration configuration, not a guaranteed measured deceleration
float32 altitude_response_time # [s] Current native altitude response time constant, not a physical settling guarantee
float32 bank_limit # [rad] Native configured bank envelope

float32 requested_equivalent_airspeed # [m/s] External/native request, NaN if using native default
float32 effective_equivalent_airspeed # [m/s] Actual bounded/slewed native reference, NaN while inactive
float32 observed_equivalent_airspeed # [m/s] Qualified observation, NaN in native sensorless control
float32 underspeed_ratio # [-] Native underspeed response, NaN while inactive
bool controller_active
bool airspeed_control_enabled # Fresh qualified input and native airspeed control enabled
bool owner_bound_mode_changes_supported # SET_NAV_STATE accepts expected mode/activation-time guard
