import { fireEvent, render, screen } from '@testing-library/react';
import ActionButtons from './ActionButtons';
import { endpoints } from '../services/apiEndpoints';
import { normalizeTrackerStatus } from '../hooks/useStatuses';

let mockHasScope = () => true;

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: mockHasScope,
  }),
}));

const baseProps = {
  isTracking: false,
  isFollowing: false,
  smartModeActive: false,
  circuitBreakerActive: false,
  handleTrackingToggle: jest.fn(),
  handleButtonClick: jest.fn(),
  handleToggleSmartMode: jest.fn(),
};

afterEach(() => {
  mockHasScope = () => true;
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

test('blocks start following while PX4 command dispatch is inhibited', () => {
  const trackerStatus = normalizeTrackerStatus({
    active_tracking: true,
    has_output: true,
    usable_for_following: true,
  });

  render(
    <ActionButtons
      {...baseProps}
      circuitBreakerActive
      trackerStatus={trackerStatus}
    />
  );

  expect(screen.getByRole('button', { name: 'Start Following' })).toBeDisabled();
});

test('fails closed while circuit-breaker state is unavailable', () => {
  const trackerStatus = normalizeTrackerStatus({
    active_tracking: true,
    has_output: true,
    usable_for_following: true,
  });

  render(
    <ActionButtons
      {...baseProps}
      circuitBreakerActive={undefined}
      trackerStatus={trackerStatus}
    />
  );

  expect(screen.getByRole('button', { name: 'Start Following' })).toBeDisabled();
});

test('blocks tracker mode and target-selection controls until Smart status is known', () => {
  const handleToggleSmartMode = jest.fn();
  render(
    <ActionButtons
      {...baseProps}
      smartModeStatusLoading
      handleToggleSmartMode={handleToggleSmartMode}
    />
  );

  expect(screen.getByRole('button', { name: 'Classic' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Smart (AI)' })).toBeDisabled();
  expect(screen.getByRole('button', { name: /Select target/i })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Smart (AI)' }));
  expect(handleToggleSmartMode).not.toHaveBeenCalled();
});

test('fails closed when Smart status loading ended without a known mode', () => {
  render(
    <ActionButtons
      {...baseProps}
      smartModeActive={undefined}
      smartModeStatusLoading={false}
    />
  );

  expect(screen.getByRole('button', { name: 'Classic' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Smart (AI)' })).toBeDisabled();
  expect(screen.getByRole('button', { name: /Select target/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Re-Detect' })).toBeDisabled();
});

test('uses typed confirmed operator abort action when cancelling tracker activity', () => {
  render(<ActionButtons {...baseProps} />);

  fireEvent.click(screen.getByRole('button', { name: 'Cancel Tracker' }));

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

test('uses typed confirmed tracking redetect action', () => {
  render(<ActionButtons {...baseProps} />);

  fireEvent.click(screen.getByRole('button', { name: 'Re-Detect' }));

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.trackingRedetectAction,
    false,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'redetect_tracking',
      confirm: true,
      idempotency_key: expect.stringMatching(/^dashboard-redetect-tracking-\d+-[a-z0-9]+$/),
      metadata: {
        ui: 'dashboard_control_panel',
      },
    })
  );
});

test('uses typed confirmed segmentation toggle action', () => {
  render(<ActionButtons {...baseProps} />);

  fireEvent.click(screen.getByRole('button', { name: 'Toggle Segmentation' }));

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.segmentationToggleAction,
    false,
    expect.objectContaining({
      source: 'dashboard',
      reason: 'toggle_segmentation',
      confirm: true,
      idempotency_key: expect.stringMatching(/^dashboard-toggle-segmentation-\d+-[a-z0-9]+$/),
      metadata: {
        ui: 'dashboard_control_panel',
      },
    })
  );
});

test('allows typed tracking utility actions with actions execute scope only', () => {
  mockHasScope = (scope) => scope === 'actions:execute';

  render(<ActionButtons {...baseProps} />);

  expect(screen.getByRole('button', { name: 'Select Target' })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: 'Re-Detect' })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: 'Toggle Segmentation' })).not.toBeDisabled();
  expect(screen.getByRole('button', { name: 'Start Following' })).not.toBeDisabled();
});

test('uses typed confirmed stop action when stopping following', () => {
  render(<ActionButtons {...baseProps} isFollowing />);

  fireEvent.click(screen.getByRole('button', { name: 'Stop Following' }));

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

test('keeps defensive Stop available and never exposes Start when following state is unknown', () => {
  render(<ActionButtons {...baseProps} isFollowing={undefined} />);

  expect(screen.queryByRole('button', { name: 'Start Following' })).not.toBeInTheDocument();
  const stopButton = screen.getByRole('button', { name: 'Stop Following' });
  expect(stopButton).not.toBeDisabled();
  fireEvent.click(stopButton);

  expect(baseProps.handleButtonClick).toHaveBeenCalledWith(
    endpoints.offboardStopAction,
    false,
    expect.objectContaining({ reason: 'stop_following' })
  );
});

test('disables operator controls when session lacks write and action scopes', () => {
  mockHasScope = () => false;

  const trackerStatus = normalizeTrackerStatus({
    active: true,
    has_output: true,
    usable_for_following: true,
  });

  render(<ActionButtons {...baseProps} trackerStatus={trackerStatus} />);

  expect(screen.getByRole('button', { name: 'Start Following' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Select Target' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Re-Detect' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Toggle Segmentation' })).toBeDisabled();
});

test('separates target-selection state from authoritative tracker runtime state', () => {
  const handleSelectionToggle = jest.fn();

  const { rerender } = render(
    <ActionButtons
      {...baseProps}
      trackingActive
      selectionArmed={false}
      handleSelectionToggle={handleSelectionToggle}
    />
  );

  fireEvent.click(screen.getByRole('button', { name: 'Select New Target' }));
  expect(handleSelectionToggle).toHaveBeenCalledTimes(1);

  rerender(
    <ActionButtons
      {...baseProps}
      trackingActive
      selectionArmed
      handleSelectionToggle={handleSelectionToggle}
    />
  );
  expect(screen.getByRole('button', { name: 'Cancel Selection' })).toBeInTheDocument();
});
