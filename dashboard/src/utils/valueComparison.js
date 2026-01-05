// dashboard/src/utils/valueComparison.js
/**
 * Utility functions for comparing and handling configuration values.
 * Used across config components to detect changes and display values.
 */

/**
 * Deep equality comparison for detecting modified values.
 * Handles objects, arrays, and primitive types correctly.
 *
 * @param {*} a - First value to compare
 * @param {*} b - Second value to compare
 * @returns {boolean} True if values are deeply equal
 */
export const isDeepEqual = (a, b) => {
  // Same reference or both primitive and equal
  if (a === b) return true;

  // Handle null/undefined
  if (a === null || b === null) return a === b;
  if (a === undefined || b === undefined) return a === b;

  // Different types
  if (typeof a !== typeof b) return false;

  // Primitives
  if (typeof a !== 'object') return a === b;

  // Arrays
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    return a.every((item, i) => isDeepEqual(item, b[i]));
  }

  // Objects
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => isDeepEqual(a[key], b[key]));
};

/**
 * Format a value compactly for mobile display (max chars).
 *
 * @param {*} value - The value to format
 * @param {number} maxLength - Maximum string length (default: 20)
 * @returns {string} Formatted string representation
 */
export const formatCompactValue = (value, maxLength = 20) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') {
    return value.length > maxLength - 3
      ? value.slice(0, maxLength - 3) + '...'
      : value;
  }
  if (Array.isArray(value)) return `[${value.length} items]`;
  if (typeof value === 'object') return `{${Object.keys(value).length} props}`;
  return String(value).slice(0, maxLength);
};

/**
 * Format a value for full display in detail views.
 *
 * @param {*} value - The value to format
 * @returns {string} Formatted string representation
 */
export const formatDisplayValue = (value) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
};

export default {
  isDeepEqual,
  formatCompactValue,
  formatDisplayValue,
};
