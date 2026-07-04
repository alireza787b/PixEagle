export const EMPTY_VALUE = '--';

export const isFiniteNumber = (value) => (
  typeof value === 'number' && Number.isFinite(value)
);

const compactNumber = (value, precision = 2) => {
  if (!isFiniteNumber(value)) return EMPTY_VALUE;
  if (Number.isInteger(value)) return String(value);

  return value
    .toFixed(precision)
    .replace(/\.?0+$/, '');
};

export const formatLabel = (value) => {
  if (!value) return '';
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

export const formatNumber = (value, { precision = 2, unit = '' } = {}) => {
  const formatted = compactNumber(value, precision);
  return formatted === EMPTY_VALUE || !unit ? formatted : `${formatted} ${unit}`;
};

export const formatPercent = (value, { precision = 1 } = {}) => {
  if (!isFiniteNumber(value)) return EMPTY_VALUE;
  const percentValue = Math.abs(value) <= 1 ? value * 100 : value;
  return `${compactNumber(percentValue, precision)}%`;
};

export const formatVector = (
  value,
  { labels = [], precision = 2, unit = '', separator = '  ' } = {}
) => {
  if (!Array.isArray(value) || value.length === 0) return EMPTY_VALUE;

  return value.map((entry, index) => {
    const prefix = labels[index] ? `${labels[index]}:` : '';
    if (!isFiniteNumber(entry)) return `${prefix}${EMPTY_VALUE}`;
    return `${prefix}${formatNumber(entry, { precision, unit })}`;
  }).join(separator);
};

export const formatTimestamp = (value) => {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE;

  const date = typeof value === 'number'
    ? new Date(Math.abs(value) < 1000000000000 ? value * 1000 : value)
    : new Date(value);

  if (Number.isNaN(date.getTime())) return String(value);
  return date.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z');
};

export const formatAgeSeconds = (timestamp, nowMs = Date.now()) => {
  if (timestamp === null || timestamp === undefined || timestamp === '') return EMPTY_VALUE;

  const timestampMs = typeof timestamp === 'number'
    ? (Math.abs(timestamp) < 1000000000000 ? timestamp * 1000 : timestamp)
    : new Date(timestamp).getTime();

  if (!Number.isFinite(timestampMs)) return EMPTY_VALUE;

  const ageSeconds = Math.max(0, (nowMs - timestampMs) / 1000);
  if (ageSeconds < 1) return '<1 s';
  if (ageSeconds < 60) return `${compactNumber(ageSeconds, 1)} s`;
  return `${compactNumber(ageSeconds / 60, 1)} min`;
};

export const formatOperatorValue = (
  value,
  { fieldName = '', fieldType = '', unit = '', precision = 2 } = {}
) => {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE;
  if (typeof value === 'number' && !Number.isFinite(value)) return EMPTY_VALUE;

  if (fieldType === 'confidence' || fieldType === 'percentage' || fieldName.includes('confidence')) {
    return formatPercent(value, { precision: 1 });
  }

  if (fieldName === 'angular' && Array.isArray(value) && value.length === 3) {
    return formatVector(value, { labels: ['Y', 'P', 'R'], precision: 1, unit: unit || 'deg' });
  }

  if (fieldType === 'angular_3d' && Array.isArray(value) && value.length === 3) {
    return formatVector(value, { labels: ['Y', 'P', 'R'], precision: 1, unit: unit || 'deg' });
  }

  if ((fieldType === 'position_2d' || fieldType === 'tuple_2d') && Array.isArray(value)) {
    return formatVector(value, { labels: ['X', 'Y'], precision: 3, unit });
  }

  if (fieldType === 'bbox' && Array.isArray(value)) {
    return formatVector(value, { labels: ['X', 'Y', 'W', 'H'], precision: 3, unit });
  }

  if (fieldType === 'velocity' && Array.isArray(value)) {
    return formatVector(value, { labels: ['X', 'Y', 'Z'], precision, unit });
  }

  if (fieldName === 'timestamp' || fieldType === 'timestamp') {
    return formatTimestamp(value);
  }

  if (Array.isArray(value)) {
    return formatVector(value, { precision, unit });
  }

  if (isFiniteNumber(value)) {
    return formatNumber(value, { precision, unit });
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }

  if (typeof value === 'object') {
    return JSON.stringify(value);
  }

  return String(value);
};
