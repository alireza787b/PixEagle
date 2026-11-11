# Optional ownership receipt, published by Commander. A receipt is not command authority.
uint32 MESSAGE_VERSION = 0
uint8 CONTRACT_VERSION = 1
uint8 STATE_IDLE = 0
uint8 STATE_PENDING = 1
uint8 STATE_ACQUIRED = 2
uint8 STATE_RELEASING = 3
uint8 STATE_RELEASED = 4
uint8 STATE_CANCELLED = 5
uint8 STATE_REJECTED = 6
uint8 STATE_EXPIRED = 7
uint8 STATE_SUPERSEDED = 8

uint64 timestamp # Publication metadata, adjusted by DDS as usual
uint8 contract_version
bool available
uint64 autopilot_uid
uint32 system_id
uint8 component_id
uint64[2] incarnation
uint64 source_clock_us # Raw firmware clock at this actual publication; DDS does not adjust this field
uint64 intention_revision
uint64[8] registration_ids # Current registration request IDs for EXTERNAL1..EXTERNAL8, zero when absent
uint8 state
uint64[2] token
uint64 source_revision
uint64 source_nav_state_timestamp
uint8 source_nav_state
uint8 mode_id
uint64 registration_id # Original registration retained with this receipt
uint64 acquired_nav_state_timestamp # Original resulting activation; never replaced by a later epoch
bool owner_active
uint8 nav_state
uint64 nav_state_timestamp
bool armed
bool rescue_active

uint8 ORB_QUEUE_LENGTH = 4
