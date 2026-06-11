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

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.offboardStartAction,
    false,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'start_following',
      confirm: true,
      idempotency_key: expect.stringMatching(/^dashboard-start-following-\d+-[a-z0-9]+$/),
      metadata: {
        ui: 'dashboard_control_panel',
      },
    })
  );
});

test('uses typed confirmed operator abort action when cancelling tracker activity', () => {
  render(<ActionButtons {...baseProps} />);

  fireEvent.click(screen.getByRole('button', {
    name: 'Cancel all tracking activities and reset',
  }));

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.operatorAbortAction,
    true,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'cancel_activities',
      confirm: true,
      idempotency_key: expect.stringMatching(/^dashboard-cancel-activities-\d+-[a-z0-9]+$/),
      metadata: {
        ui: 'dashboard_control_panel',
      },
    })
  );
});

test('uses typed confirmed stop action when stopping following', () => {
  render(<ActionButtons {...baseProps} isFollowing />);

  fireEvent.click(screen.getByRole('button', {
    name: 'Disengage offboard mode and stop following immediately',
  }));

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.offboardStopAction,
    false,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'stop_following',
      confirm: true,
      idempotency_key: expect.stringMatching(/^dashboard-stop-following-\d+-[a-z0-9]+$/),
      metadata: {
        ui: 'dashboard_control_panel',
      },
    })
  );
});
