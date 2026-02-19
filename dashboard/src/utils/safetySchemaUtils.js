// dashboard/src/utils/safetySchemaUtils.js
/**
 * Safety Schema Utilities
 *
 * Schema-driven definitions for safety limit properties and known followers.
 * Used by SafetyLimitsEditor for validation and property suggestions.
 */

/**
 * All valid safety limit properties with metadata
 * Used for property suggestions and validation
 */
export const SAFETY_LIMIT_PROPERTIES = [
  // Altitude Limits
  {
    name: 'MIN_ALTITUDE',
    type: 'number',
    unit: 'm',
    description: 'Minimum safe altitude (AGL)',
    category: 'altitude',
    min: 0,
    max: 1000,
    step: 1,
    default: 3.0
  },
  {
    name: 'MAX_ALTITUDE',
    type: 'number',
    unit: 'm',
    description: 'Maximum safe altitude (AGL)',
    category: 'altitude',
    min: 0,
    max: 5000,
    step: 1,
    default: 120.0
  },
  {
    name: 'ALTITUDE_WARNING_BUFFER',
    type: 'number',
    unit: 'm',
    description: 'Warning buffer zone before limits',
    category: 'altitude',
    min: 0,
    max: 50,
    step: 0.5,
    default: 2.0
  },
  {
    name: 'ALTITUDE_SAFETY_ENABLED',
    type: 'boolean',
    unit: '',
    description: 'Enable altitude safety enforcement',
    category: 'altitude',
    default: true
  },

  // Velocity Limits
  {
    name: 'MAX_VELOCITY',
    type: 'number',
    unit: 'm/s',
    description: 'Maximum total velocity magnitude',
    category: 'velocity',
    min: 0,
    max: 30,
    step: 0.1,
    default: 1.0
  },
  {
    name: 'MAX_VELOCITY_FORWARD',
    type: 'number',
    unit: 'm/s',
    description: 'Maximum forward velocity',
    category: 'velocity',
    min: 0,
    max: 30,
    step: 0.1,
    default: 0.5
  },
  {
    name: 'MAX_VELOCITY_LATERAL',
    type: 'number',
    unit: 'm/s',
    description: 'Maximum lateral (sideways) velocity',
    category: 'velocity',
    min: 0,
    max: 20,
    step: 0.1,
    default: 0.5
  },
  {
    name: 'MAX_VELOCITY_VERTICAL',
    type: 'number',
    unit: 'm/s',
    description: 'Maximum vertical velocity',
    category: 'velocity',
    min: 0,
    max: 10,
    step: 0.1,
    default: 0.5
  },

  // Angular Rate Limits
  {
    name: 'MAX_YAW_RATE',
    type: 'number',
    unit: 'deg/s',
    description: 'Maximum yaw rotation rate',
    category: 'rates',
    min: 0,
    max: 180,
    step: 1,
    default: 45.0
  },
  {
    name: 'MAX_PITCH_RATE',
    type: 'number',
    unit: 'deg/s',
    description: 'Maximum pitch rotation rate',
    category: 'rates',
    min: 0,
    max: 180,
    step: 1,
    default: 45.0
  },
  {
    name: 'MAX_ROLL_RATE',
    type: 'number',
    unit: 'deg/s',
    description: 'Maximum roll rotation rate',
    category: 'rates',
    min: 0,
    max: 180,
    step: 1,
    default: 45.0
  }
];

/**
 * Known follower modes with metadata
 */
export const KNOWN_FOLLOWERS = [
  // Multicopter followers
  {
    name: 'MC_VELOCITY_CHASE',
    label: 'MC Velocity Chase',
    description: 'Chase mode with velocity control',
    type: 'multicopter'
  },
  {
    name: 'MC_VELOCITY_DISTANCE',
    label: 'MC Velocity Distance',
    description: 'Distance-maintaining velocity follower',
    type: 'multicopter'
  },
  {
    name: 'MC_VELOCITY_POSITION',
    label: 'MC Velocity Position',
    description: 'Position-based velocity follower',
    type: 'multicopter'
  },
  {
    name: 'MC_VELOCITY_GROUND',
    label: 'MC Velocity Ground',
    description: 'Ground-relative velocity follower',
    type: 'multicopter'
  },
  {
    name: 'MC_ATTITUDE_RATE',
    label: 'MC Attitude Rate',
    description: 'Attitude rate control follower',
    type: 'multicopter'
  },

  // Gimbal followers
  {
    name: 'GM_VELOCITY_CHASE',
    label: 'Gimbal Velocity Chase',
    description: 'PID-based gimbal velocity chase tracking',
    type: 'gimbal'
  },
  {
    name: 'GM_VELOCITY_VECTOR',
    label: 'Gimbal Velocity Vector',
    description: 'Velocity vector gimbal control',
    type: 'gimbal'
  },

  // Fixed-wing followers
  {
    name: 'FW_ATTITUDE_RATE',
    label: 'Fixed-Wing Attitude Rate',
    description: 'Fixed-wing attitude rate control',
    type: 'fixed_wing'
  }
];

/**
 * Get property metadata by name
 */
export function getPropertyByName(name) {
  return SAFETY_LIMIT_PROPERTIES.find(p => p.name === name);
}

/**
 * Get all properties for a category
 */
export function getPropertiesByCategory(category) {
  return SAFETY_LIMIT_PROPERTIES.filter(p => p.category === category);
}

/**
 * Get properties that are not yet set in an object
 */
export function getAddableProperties(currentProperties) {
  const setKeys = Object.keys(currentProperties || {});
  return SAFETY_LIMIT_PROPERTIES.filter(p => !setKeys.includes(p.name));
}

/**
 * Get follower metadata by name (case-insensitive)
 */
export function getFollowerByName(name) {
  const upperName = (name || '').toUpperCase();
  return KNOWN_FOLLOWERS.find(f => f.name.toUpperCase() === upperName);
}

/**
 * Get followers grouped by type
 */
export function getFollowersByType() {
  const groups = {};
  KNOWN_FOLLOWERS.forEach(f => {
    if (!groups[f.type]) {
      groups[f.type] = [];
    }
    groups[f.type].push(f);
  });
  return groups;
}

/**
 * Category metadata for grouping in UI
 */
export const PROPERTY_CATEGORIES = {
  altitude: {
    label: 'Altitude Limits',
    icon: 'Height',
    color: 'success'
  },
  velocity: {
    label: 'Velocity Limits',
    icon: 'Speed',
    color: 'primary'
  },
  rates: {
    label: 'Rate Limits',
    icon: 'RotateRight',
    color: 'warning'
  }
};

/**
 * Follower type metadata
 */
export const FOLLOWER_TYPES = {
  multicopter: {
    label: 'Multicopter',
    icon: 'FlightTakeoff',
    color: 'primary'
  },
  gimbal: {
    label: 'Gimbal',
    icon: 'CameraAlt',
    color: 'info'
  },
  fixed_wing: {
    label: 'Fixed-Wing',
    icon: 'Flight',
    color: 'warning'
  }
};

const safetySchemaUtils = {
  SAFETY_LIMIT_PROPERTIES,
  KNOWN_FOLLOWERS,
  PROPERTY_CATEGORIES,
  FOLLOWER_TYPES,
  getPropertyByName,
  getPropertiesByCategory,
  getAddableProperties,
  getFollowerByName,
  getFollowersByType
};

export default safetySchemaUtils;
