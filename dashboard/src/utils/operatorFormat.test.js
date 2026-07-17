import {
  EMPTY_VALUE,
  formatAgeSeconds,
  formatNumber,
  formatOperatorValue,
  formatPercent,
  formatVector,
} from './operatorFormat';

test('formats unavailable values without inventing zero', () => {
  expect(formatOperatorValue(null)).toBe(EMPTY_VALUE);
  expect(formatOperatorValue(undefined)).toBe(EMPTY_VALUE);
  expect(formatOperatorValue(Number.NaN)).toBe(EMPTY_VALUE);
});

test('uses compact numeric precision for operator displays', () => {
  expect(formatNumber(1.25001, { precision: 3, unit: 'm/s' })).toBe('1.25 m/s');
  expect(formatNumber(4, { precision: 3 })).toBe('4');
  expect(formatPercent(0.8732)).toBe('87.3%');
});

test('formats common tracker vectors with labels', () => {
  expect(formatVector([0.12345, -0.5], { labels: ['X', 'Y'], precision: 2 })).toBe('X:0.12  Y:-0.5');
  expect(formatOperatorValue([12.123, -4.456, 0], {
    fieldName: 'angular',
    fieldType: 'angular_3d',
  })).toBe('Y:12.1 deg  P:-4.5 deg  R:0 deg');
});

test('formats timestamp ages', () => {
  expect(formatAgeSeconds('2026-07-04T12:00:00.000Z', Date.parse('2026-07-04T12:00:12.000Z'))).toBe('12 s');
});
