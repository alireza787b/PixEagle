# Optional atomic external-mode ownership request. This never arms or requests a VTOL transition.
uint32 MESSAGE_VERSION = 0
uint8 CONTRACT_VERSION = 2
uint8 OPERATION_ACQUIRE = 1
uint8 OPERATION_RELEASE = 2

uint64 timestamp # Publication metadata; not the ownership deadline clock
uint8 contract_version
uint8 operation
uint64[2] incarnation # Firmware Commander instance, copied from OwnedModeStatus
uint64[2] token # Opaque acquisition token, bound to the companion's runtime/session
uint64 source_revision # Original acquisition source intention revision
uint8 source_vehicle_type # Original settled VehicleStatus vehicle type
uint64 source_phase_instance # Original VTOL module lifetime, zero only for non-VTOL
uint64 source_phase_revision # Original persistent transition/phase history
uint64 source_nav_state_timestamp # Original acquisition source mode epoch, raw PX4 time
uint8 source_nav_state
uint8 mode_id # Registered external mode to acquire/release
uint64 registration_id # Original request ID of that current external-mode registration
uint64 acquired_nav_state_timestamp # Zero only when acquisition acknowledgement is unavailable
uint64 source_clock_us # Actual raw PX4 clock publication, never a query-created sample
uint64 expires_at_us # Absolute raw PX4 deadline, frozen for this operation
uint32 target_system
uint8 target_component

uint8 ORB_QUEUE_LENGTH = 4
