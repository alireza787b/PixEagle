// dashboard/src/utils/schemaAnalyzer.js
/**
 * Schema Analyzer Utility
 *
 * Analyzes config schema and values to detect patterns and generate
 * appropriate field configurations for specialized renderers.
 */

export const PatternType = {
  PID_TRIPLET: 'pid_triplet',           // Single {p, i, d} object
  AXIS_PID_GROUP: 'axis_pid_group',     // Multiple PID axes (like PID_GAINS)
  GAIN_SCHEDULE: 'gain_schedule',       // Altitude range PID scheduling
  SCALAR_ARRAY: 'scalar_array',         // Array of numbers [1, 2, 3]
  STRING_ARRAY: 'string_array',         // Array of strings ["a", "b"]
  BOOLEAN_ARRAY: 'boolean_array',       // Array of booleans
  OBJECT_ARRAY: 'object_array',         // Array of objects
  FLAT_OBJECT: 'flat_object',           // Simple key-value object
  NESTED_OBJECT: 'nested_object',       // Object with nested objects
  UNKNOWN: 'unknown'
};

/**
 * Check if an object is a PID triplet {p, i, d}
 */
export function isPIDTriplet(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return false;
  }
  const keys = Object.keys(obj).map(k => k.toLowerCase());
  // Must have exactly p, i, d keys (case insensitive)
  return keys.length === 3 &&
         keys.includes('p') &&
         keys.includes('i') &&
         keys.includes('d');
}

/**
 * Check if all values in an object are PID triplets
 */
export function isAxisPIDGroup(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return false;
  }
  const values = Object.values(obj);
  if (values.length === 0) return false;
  return values.every(v => isPIDTriplet(v));
}

/**
 * Check if an object is a gain schedule (altitude range -> PID axes)
 * Pattern: { "(0, 20)": { x: {p,i,d}, y: {p,i,d} }, "(20, 50)": {...} }
 */
export function isGainSchedule(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return false;
  }
  const keys = Object.keys(obj);
  if (keys.length === 0) return false;

  // Check if keys look like altitude ranges "(min, max)"
  const rangePattern = /^\s*\(\s*\d+\s*,\s*\d+\s*\)\s*$/;
  const hasRangeKeys = keys.some(k => rangePattern.test(k));

  if (!hasRangeKeys) return false;

  // Check if values are axis PID groups
  return Object.values(obj).every(v => isAxisPIDGroup(v));
}

/**
 * Determine array item type
 */
export function getArrayItemType(arr) {
  if (!Array.isArray(arr) || arr.length === 0) {
    return 'unknown';
  }

  const types = arr.map(item => {
    if (typeof item === 'number') return 'number';
    if (typeof item === 'string') return 'string';
    if (typeof item === 'boolean') return 'boolean';
    if (typeof item === 'object' && item !== null) return 'object';
    return 'unknown';
  });

  // Check if all same type
  const firstType = types[0];
  if (types.every(t => t === firstType)) {
    return firstType;
  }
  return 'mixed';
}

/**
 * Check if object has any nested objects or arrays
 */
export function hasNestedStructure(obj) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    return false;
  }
  return Object.values(obj).some(v =>
    typeof v === 'object' && v !== null
  );
}

/**
 * Generate a human-readable preview text for a value
 */
export function generatePreviewText(value, maxLength = 50) {
  if (value === null || value === undefined) {
    return 'null';
  }

  if (Array.isArray(value)) {
    const itemType = getArrayItemType(value);
    if (itemType === 'number' || itemType === 'string') {
      const preview = `[${value.slice(0, 3).join(', ')}${value.length > 3 ? ', ...' : ''}]`;
      return preview.length > maxLength ? preview.slice(0, maxLength - 3) + '...' : preview;
    }
    return `Array (${value.length} items)`;
  }

  if (typeof value === 'object') {
    if (isPIDTriplet(value)) {
      const p = value.p ?? value.P ?? 0;
      const i = value.i ?? value.I ?? 0;
      const d = value.d ?? value.D ?? 0;
      return `P:${p} I:${i} D:${d}`;
    }

    const keys = Object.keys(value);
    if (keys.length <= 3) {
      return `{${keys.join(', ')}}`;
    }
    return `Object (${keys.length} keys)`;
  }

  return String(value);
}

/**
 * Count complexity (for display badges)
 */
export function getComplexityLabel(value, schema) {
  if (Array.isArray(value)) {
    return `${value.length} items`;
  }

  if (typeof value === 'object' && value !== null) {
    if (isAxisPIDGroup(value)) {
      return `${Object.keys(value).length} axes`;
    }
    if (isGainSchedule(value)) {
      return `${Object.keys(value).length} ranges`;
    }
    return `${Object.keys(value).length} fields`;
  }

  return null;
}

/**
 * Detect the pattern type for a value based on schema and actual value
 */
export function detectPattern(schema, value) {
  // Handle arrays
  if (schema?.type === 'array' || Array.isArray(value)) {
    const arr = value || [];
    const itemType = getArrayItemType(arr);

    if (itemType === 'number') return PatternType.SCALAR_ARRAY;
    if (itemType === 'string') return PatternType.STRING_ARRAY;
    if (itemType === 'boolean') return PatternType.BOOLEAN_ARRAY;
    if (itemType === 'object') return PatternType.OBJECT_ARRAY;
    return PatternType.SCALAR_ARRAY; // Default for empty arrays
  }

  // Handle objects
  if (schema?.type === 'object' || (typeof value === 'object' && value !== null)) {
    const obj = value || {};

    // Check for specific patterns
    if (isGainSchedule(obj)) {
      return PatternType.GAIN_SCHEDULE;
    }

    if (isAxisPIDGroup(obj)) {
      return PatternType.AXIS_PID_GROUP;
    }

    if (isPIDTriplet(obj)) {
      return PatternType.PID_TRIPLET;
    }

    if (hasNestedStructure(obj)) {
      return PatternType.NESTED_OBJECT;
    }

    return PatternType.FLAT_OBJECT;
  }

  return PatternType.UNKNOWN;
}

/**
 * Generate field configurations from schema properties
 */
export function generateFieldConfigs(schema, value) {
  const configs = [];

  if (!schema?.properties && typeof value === 'object' && value !== null) {
    // No schema properties - generate from value
    for (const [key, val] of Object.entries(value)) {
      configs.push({
        key,
        type: typeof val,
        value: val,
        description: null,
        required: false
      });
    }
    return configs;
  }

  // Generate from schema properties
  const properties = schema?.properties || {};
  for (const [key, propSchema] of Object.entries(properties)) {
    configs.push({
      key,
      type: propSchema.type || 'string',
      value: value?.[key] ?? propSchema.default,
      description: propSchema.description,
      required: propSchema.required || false,
      min: propSchema.minimum,
      max: propSchema.maximum,
      step: propSchema.step,
      options: propSchema.options,
      default: propSchema.default
    });
  }

  return configs;
}

/**
 * Main analysis function - analyzes schema and value to produce rendering info
 */
export function analyzeSchema(schema, value) {
  const pattern = detectPattern(schema, value);
  const previewText = generatePreviewText(value);
  const complexity = getComplexityLabel(value, schema);
  const fieldConfigs = generateFieldConfigs(schema, value);

  return {
    pattern,
    previewText,
    complexity,
    fieldConfigs,
    isComplex: pattern !== PatternType.UNKNOWN &&
               pattern !== PatternType.FLAT_OBJECT,
    canRenderInline: pattern === PatternType.PID_TRIPLET ||
                     pattern === PatternType.SCALAR_ARRAY ||
                     pattern === PatternType.FLAT_OBJECT
  };
}

/**
 * Group PID axes by category for better organization
 */
export function groupPIDAxes(axes) {
  const groups = {
    position: { label: 'Position Axes', axes: [] },
    rate: { label: 'Rate Axes', axes: [] },
    velocity: { label: 'Velocity Axes', axes: [] },
    fixedWing: { label: 'Fixed Wing', axes: [] },
    multicopter: { label: 'Multicopter', axes: [] },
    mcAttitudeRate: { label: 'MC Attitude Rate', axes: [] },
    other: { label: 'Other Axes', axes: [] }
  };

  for (const [key, value] of Object.entries(axes)) {
    const lowerKey = key.toLowerCase();

    if (['x', 'y', 'z'].includes(lowerKey)) {
      groups.position.axes.push({ key, value });
    } else if (lowerKey.includes('speed') || lowerKey.includes('rate')) {
      if (lowerKey.startsWith('fw_')) {
        groups.fixedWing.axes.push({ key, value });
      } else if (lowerKey.startsWith('mc_')) {
        groups.multicopter.axes.push({ key, value });
      } else if (lowerKey.startsWith('mcar_')) {
        groups.mcAttitudeRate.axes.push({ key, value });
      } else {
        groups.rate.axes.push({ key, value });
      }
    } else if (lowerKey.includes('vel')) {
      if (lowerKey.startsWith('mc_')) {
        groups.multicopter.axes.push({ key, value });
      } else {
        groups.velocity.axes.push({ key, value });
      }
    } else if (lowerKey.startsWith('fw_')) {
      groups.fixedWing.axes.push({ key, value });
    } else if (lowerKey.startsWith('mc_')) {
      groups.multicopter.axes.push({ key, value });
    } else if (lowerKey.startsWith('mcar_')) {
      groups.mcAttitudeRate.axes.push({ key, value });
    } else {
      groups.other.axes.push({ key, value });
    }
  }

  // Filter out empty groups and return as array
  return Object.values(groups).filter(g => g.axes.length > 0);
}

const SchemaAnalyzer = {
  PatternType,
  analyzeSchema,
  isPIDTriplet,
  isAxisPIDGroup,
  isGainSchedule,
  detectPattern,
  generateFieldConfigs,
  generatePreviewText,
  getComplexityLabel,
  groupPIDAxes
};

export default SchemaAnalyzer;
