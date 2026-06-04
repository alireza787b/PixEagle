import { fireEvent, render, screen } from '@testing-library/react';
import ActionButtons from './ActionButtons';
import { endpoints } from '../services/apiEndpoints';
import { normalizeTrackerStatus } from '../hooks/useStatuses';

const baseProps = {
  isTracking: false,
  isFollowing: false,
  smartModeActive: false,
  handleTrackingToggle: jest.fn(),
  handleButtonClick: jest.fn(),
  handleToggleSmartMode: jest.fn(),
};

afterEach(() => {
  jest.clearAllMocks();
});

test('blocks start following when tracker output is visible but not follower usable', () => {
  const trackerStatus = normalizeTrackerStatus({
    active: false,
    has_output: true,
    usable_for_following: false,
  });

  render(<ActionButtons {...baseProps} trackerStatus={trackerStatus} />);

  expect(screen.getByRole('button', { name: 'Start Following' })).toBeDisabled();
});

test('allows confirmed start following when tracker output is follower usable', () => {
  const trackerStatus = normalizeTrackerStatus({
    active: true,
    has_output: true,
    usable_for_following: true,
  });

  render(<ActionButtons {...baseProps} trackerStatus={trackerStatus} />);

  fireEvent.click(screen.getByRole('button', { name: 'Start Following' }));
  fireEvent.click(screen.getByRole('button', { name: 'Engage' }));

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(endpoints.startOffboardMode);
});
