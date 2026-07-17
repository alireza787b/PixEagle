import { render, screen } from '@testing-library/react';
import PollingStatusIndicator, { POLLING_STATUS_PRESENTATION } from './PollingStatusIndicator';

test.each([
  ['connecting', 'Connecting', 'info.main'],
  ['active', 'Active', 'success.main'],
  ['inactive', 'Inactive', 'text.secondary'],
  ['stale', 'Stale', 'warning.main'],
  ['degraded', 'Degraded', 'warning.main'],
  ['unavailable', 'Unavailable', 'error.main'],
])('presents %s samples as %s with %s', (status, expectedLabel, expectedColor) => {
  render(<PollingStatusIndicator status={status} />);

  const indicator = screen.getByRole('status');
  expect(indicator).toHaveAttribute('data-status', status);
  expect(indicator).toHaveTextContent(expectedLabel);
  expect(indicator).toHaveAccessibleName(new RegExp(expectedLabel));
  expect(POLLING_STATUS_PRESENTATION[status].color).toBe(expectedColor);
});
