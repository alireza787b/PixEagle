// dashboard/src/utils/followerConfigSchemaUtils.js
/**
 * Follower Config Schema Utilities
 *
 * Schema-driven definitions for follower operational config properties.
 * Used by FollowerConfigEditor for validation and property suggestions.
 * Mirrors safetySchemaUtils.js pattern for consistency.
 */

import { KNOWN_FOLLOWERS } from './safetySchemaUtils';

/**
 * All valid follower config properties with metadata.
 * Matches FollowerConfigManager.GENERAL_PARAMS + _FALLBACKS on the backend.
 */
export const FOLLOWER_CONFIG_PROPERTIES = [
  // Timing
  {
    name: 'CONTROL_UPDATE_RATE',
    type: 'number',
    unit: 'Hz',
    description: 'Control loop update frequency',
    category: 'timing',
    min: 1,
    max: 100,
    step: 1,
    default: 20.0
  },

  // Smoothing
  {
    name: 'COMMAND_SMOOTHING_ENABLED',
    type: 'boolean',
    unit: '',
    description: 'Enable velocity command smoothing (EMA)',
    category: 'smoothing',
    default: true
  },
  {
    name: 'SMOOTHING_FACTOR',
    type: 'number',
    unit: '',
    description: 'EMA smoothing factor (0=no smooth, 1=max smooth)',
    category: 'smoothing',
    min: 0,
    max: 1,
    step: 0.01,
    default: 0.8
  },

  // Target Loss
  {
    name: 'TARGET_LOSS_TIMEOUT',
    type: 'number',
    unit: 's',
    description: 'Seconds before declaring target lost',
    category: 'target_loss',
    min: 0.5,
    max: 30,
    step: 0.5,
    default: 3.0
  },
  {
    name: 'TARGET_LOSS_COORDINATE_THRESHOLD',
    type: 'number',
    unit: '',
    description: 'Coordinate threshold for target loss detection',
    category: 'target_loss',
    min: 0,
    max: 10,
    step: 0.1,
    default: 1.5
  },

  // Guidance
  {
    name: 'LATERAL_GUIDANCE_MODE',
    type: 'enum',
    unit: '',
    description: 'Lateral guidance strategy',
    category: 'guidance',
    options: ['coordinated_turn', 'sideslip', 'direct'],
    default: 'coordinated_turn'
  },
  {
    name: 'ENABLE_AUTO_MODE_SWITCHING',
    type: 'boolean',
    unit: '',
    description: 'Auto-switch between guidance modes based on speed',
    category: 'guidance',
    default: false
  },
  {
    name: 'GUIDANCE_MODE_SWITCH_VELOCITY',
    type: 'number',
    unit: 'm/s',
    description: 'Speed threshold for guidance mode switching',
    category: 'guidance',
    min: 0,
    max: 20,
    step: 0.5,
    default: 3.0
  },
  {
    name: 'MODE_SWITCH_HYSTERESIS',
    type: 'number',
    unit: 'm/s',
    description: 'Hysteresis band for mode switching',
    category: 'guidance',
    min: 0,
    max: 5,
    step: 0.1,
    default: 0.5
  },
  {
    name: 'MIN_MODE_SWITCH_INTERVAL',
    type: 'number',
    unit: 's',
    description: 'Minimum time between mode switches',
    category: 'guidance',
    min: 0.1,
    max: 30,
    step: 0.1,
    default: 2.0
  },

  // Altitude
  {
    name: 'ENABLE_ALTITUDE_CONTROL',
    type: 'boolean',
    unit: '',
    description: 'Enable altitude control loop',
    category: 'altitude',
    default: false
  },
  {
    name: 'ALTITUDE_CHECK_INTERVAL',
    type: 'number',
    unit: 's',
    description: 'Interval between altitude checks',
    category: 'altitude',
    min: 0.05,
    max: 5,
    step: 0.05,
    default: 0.1
  }
];

/**
 * YAW_SMOOTHING sub-properties (separate array to avoid name collisions with ENABLED)
 */
export const YAW_SMOOTHING_PROPERTIES = [
  {
    name: 'ENABLED',
    type: 'boolean',
    unit: '',
    description: 'Master enable for yaw smoothing pipeline',
    category: 'yaw_smoothing',
    default: true
  },
  {
    name: 'DEADZONE_DEG_S',
    type: 'number',
    unit: 'deg/s',
    description: 'Ignore yaw rates below this threshold',
    category: 'yaw_smoothing',
    min: 0,
    max: 10,
    step: 0.1,
    default: 0.5
  },
  {
    name: 'MAX_RATE_CHANGE_DEG_S2',
    type: 'number',
    unit: 'deg/s\u00B2',
    description: 'Maximum yaw acceleration',
    category: 'yaw_smoothing',
    min: 1,
    max: 360,
    step: 1,
    default: 90.0
  },
  {
    name: 'SMOOTHING_ALPHA',
    type: 'number',
    unit: '',
    description: 'EMA coefficient (0=max smoothing, 1=no smoothing)',
    category: 'yaw_smoothing',
    min: 0,
    max: 1,
    step: 0.01,
    default: 0.7
  },
  {
    name: 'ENABLE_SPEED_SCALING',
    type: 'boolean',
    unit: '',
    description: 'Scale yaw authority based on forward speed',
    category: 'yaw_smoothing',
    default: true
  },
  {
    name: 'MIN_SPEED_THRESHOLD',
    type: 'number',
    unit: 'm/s',
    description: 'Below this speed, reduce yaw authority',
    category: 'yaw_smoothing',
    min: 0,
    max: 10,
    step: 0.1,
    default: 0.5
  },
  {
    name: 'MAX_SPEED_THRESHOLD',
    type: 'number',
    unit: 'm/s',
    description: 'Above this speed, full yaw authority',
    category: 'yaw_smoothing',
    min: 0,
    max: 30,
    step: 0.5,
    default: 5.0
  },
  {
    name: 'LOW_SPEED_YAW_FACTOR',
    type: 'number',
    unit: '',
    description: 'Yaw rate reduction factor at low speed',
    category: 'yaw_smoothing',
    min: 0,
    max: 1,
    step: 0.01,
    default: 0.5
  }
];

/**
 * Default values for all 12 General flat properties
 */
export const GENERAL_DEFAULTS = {
  CONTROL_UPDATE_RATE: 20.0,
  COMMAND_SMOOTHING_ENABLED: true,
  SMOOTHING_FACTOR: 0.8,
  TARGET_LOSS_TIMEOUT: 3.0,
  TARGET_LOSS_COORDINATE_THRESHOLD: 1.5,
  LATERAL_GUIDANCE_MODE: 'coordinated_turn',
  ENABLE_AUTO_MODE_SWITCHING: false,
  GUIDANCE_MODE_SWITCH_VELOCITY: 3.0,
  MODE_SWITCH_HYSTERESIS: 0.5,
  MIN_MODE_SWITCH_INTERVAL: 2.0,
  ENABLE_ALTITUDE_CONTROL: false,
  ALTITUDE_CHECK_INTERVAL: 0.1
};

/**
 * Default values for YAW_SMOOTHING sub-properties
 */
export const YAW_SMOOTHING_DEFAULTS = {
  ENABLED: true,
  DEADZONE_DEG_S: 0.5,
  MAX_RATE_CHANGE_DEG_S2: 90.0,
  SMOOTHING_ALPHA: 0.7,
  ENABLE_SPEED_SCALING: true,
  MIN_SPEED_THRESHOLD: 0.5,
  MAX_SPEED_THRESHOLD: 5.0,
  LOW_SPEED_YAW_FACTOR: 0.5
};

/**
 * Registry of nested sub-sections within the Follower config.
 * Each entry describes a config key whose value is a nested object
 * with its own property schema and defaults.
 * The FollowerConfigEditor renders these generically as collapsible accordions.
 * To add a new nested sub-section, add an entry here — no editor code changes needed.
 */
export const NESTED_SUBSECTIONS = {
  YAW_SMOOTHING: {
    label: 'Yaw Smoothing Pipeline',
    category: 'yaw_smoothing',
    properties: YAW_SMOOTHING_PROPERTIES,
    defaults: YAW_SMOOTHING_DEFAULTS,
    statusKey: 'ENABLED',
  }
};

/**
 * Get property metadata for a nested sub-section by key and property name
 */
export function getSubsectionPropertyByName(subsectionKey, propName) {
  const subsection = NESTED_SUBSECTIONS[subsectionKey];
  if (!subsection) return undefined;
  return subsection.properties.find(p => p.name === propName);
}

/**
 * Known follower modes — reused from safetySchemaUtils.js
 */
export { KNOWN_FOLLOWERS, FOLLOWER_TYPES } from './safetySchemaUtils';

/**
 * Get property metadata by name
 */
export function getPropertyByName(name) {
  return FOLLOWER_CONFIG_PROPERTIES.find(p => p.name === name);
}

/**
 * Get all properties for a category
 */
export function getPropertiesByCategory(category) {
  return FOLLOWER_CONFIG_PROPERTIES.filter(p => p.category === category);
}

/**
 * Get properties not yet set in a given object
 */
export function getAddableProperties(currentProperties) {
  const setKeys = Object.keys(currentProperties || {});
  return FOLLOWER_CONFIG_PROPERTIES.filter(p => !setKeys.includes(p.name));
}

/**
 * Get YAW_SMOOTHING property metadata by name
 */
export function getYawSmoothingPropertyByName(name) {
  return YAW_SMOOTHING_PROPERTIES.find(p => p.name === name);
}

/**
 * Get YAW_SMOOTHING properties not yet set
 */
export function getAddableYawSmoothingProperties(currentProperties) {
  const setKeys = Object.keys(currentProperties || {});
  return YAW_SMOOTHING_PROPERTIES.filter(p => !setKeys.includes(p.name));
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
  timing: {
    label: 'Control Timing',
    icon: 'Speed',
    color: 'primary'
  },
  smoothing: {
    label: 'Command Smoothing',
    icon: 'Tune',
    color: 'info'
  },
  target_loss: {
    label: 'Target Loss Detection',
    icon: 'GpsOff',
    color: 'error'
  },
  guidance: {
    label: 'Guidance Modes',
    icon: 'Navigation',
    color: 'warning'
  },
  altitude: {
    label: 'Altitude Control',
    icon: 'Height',
    color: 'success'
  },
  yaw_smoothing: {
    label: 'Yaw Smoothing Pipeline',
    icon: 'RotateRight',
    color: 'secondary'
  }
};

const followerConfigSchemaUtils = {
  FOLLOWER_CONFIG_PROPERTIES,
  YAW_SMOOTHING_PROPERTIES,
  GENERAL_DEFAULTS,
  YAW_SMOOTHING_DEFAULTS,
  NESTED_SUBSECTIONS,
  PROPERTY_CATEGORIES,
  getPropertyByName,
  getPropertiesByCategory,
  getAddableProperties,
  getYawSmoothingPropertyByName,
  getAddableYawSmoothingProperties,
  getSubsectionPropertyByName,
  getFollowerByName,
  getFollowersByType
};

export default followerConfigSchemaUtils;
