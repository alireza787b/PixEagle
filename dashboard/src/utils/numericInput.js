// dashboard/src/utils/numericInput.js
/**
 * Utilities for numeric text inputs.
 *
 * Keep user input as text while typing so intermediate states (e.g. "-", "1.")
 * are not coerced into unintended values.
 */

const INTEGER_PATTERN = /^[+-]?\d+$/;
const FLOAT_PATTERN = /^[+-]?(?:\d+\.?\d*|\.\d+)$/;

export const isTransientNumericText = (text) => {
  const raw = String(text ?? '').trim();
  return raw === '' || raw === '-' || raw === '+' || raw === '.' || raw === '-.' || raw === '+.';
};

export const parseCommittedNumeric = (text, type = 'float') => {
  const raw = String(text ?? '').trim();

  if (isTransientNumericText(raw)) {
    return { valid: false, transient: true, value: null, raw, reason: 'transient' };
  }

  if (type === 'integer') {
    if (!INTEGER_PATTERN.test(raw)) {
      return { valid: false, transient: false, value: null, raw, reason: 'invalid_integer' };
    }
    const value = Number.parseInt(raw, 10);
    if (!Number.isFinite(value)) {
      return { valid: false, transient: false, value: null, raw, reason: 'invalid_integer' };
    }
    return { valid: true, transient: false, value, raw, reason: null };
  }

  if (!FLOAT_PATTERN.test(raw)) {
    return { valid: false, transient: false, value: null, raw, reason: 'invalid_number' };
  }

  const value = Number.parseFloat(raw);
  if (!Number.isFinite(value)) {
    return { valid: false, transient: false, value: null, raw, reason: 'invalid_number' };
  }

  return { valid: true, transient: false, value, raw, reason: null };
};

export const clampNumericValue = (value, min, max) => {
  if (!Number.isFinite(value)) return value;
  let next = value;
  if (min !== undefined) next = Math.max(min, next);
  if (max !== undefined) next = Math.min(max, next);
  return next;
};

