import { render, screen } from '@testing-library/react';
import OperationalStatusBar from './OperationalStatusBar';
import { normalizeTelemetryHealth, normalizeTrackerStatus } from '../hooks/useStatuses';

const baseProps = {
  isTracking: false,
  smartModeActive: false,
  isFollowing: false,
  circuitBreakerActive: false,
};

test('shows degraded telemetry as a distinct operator state', () => {
  const telemetryStatus = normalizeTelemetryHealth({
    enabled: true,
    status: 'degraded',
    consumer_guidance: 'degraded_latest_request_failed',
    transport: {
      latest_request_ok: false,
      latest_request_result: 'failure',
    },
    request_freshness: {
      fresh: true,
    },
    payload: {
      has_payload: true,
      fresh: true,
    },
  });

  render(<OperationalStatusBar {...baseProps} telemetryStatus={telemetryStatus} />);

  expect(screen.getByText('Telemetry: Degraded')).toBeInTheDocument();
});

test('shows visible tracker output as distinct from active usable tracking', () => {
  const trackerStatus = normalizeTrackerStatus({
    active: false,
    has_output: true,
    usable_for_following: false,
  });

  render(<OperationalStatusBar {...baseProps} trackerStatus={trackerStatus} />);

  expect(screen.getByText('Tracking: Visible')).toBeInTheDocument();
  expect(screen.queryByText('Tracking: ON')).not.toBeInTheDocument();
});

test('shows disabled telemetry even when cached payload exists', () => {
  const telemetryStatus = normalizeTelemetryHealth({
    enabled: false,
    status: 'disabled',
    consumer_guidance: 'disabled',
    transport: {
      latest_request_ok: false,
      latest_request_result: 'success',
    },
    request_freshness: {
      fresh: false,
    },
    payload: {
      has_payload: true,
      fresh: false,
      flight_mode: 393216,
      arm_status: 'Armed',
    },
  });

  render(<OperationalStatusBar {...baseProps} telemetryStatus={telemetryStatus} />);

  expect(screen.getByText('Telemetry: Disabled')).toBeInTheDocument();
});

test('labels unknown tracker mode and command-inhibit state without optimistic defaults', () => {
  render(
    <OperationalStatusBar
      {...baseProps}
      smartModeActive={undefined}
      circuitBreakerActive={undefined}
    />
  );

  expect(screen.getByText('Mode: Unknown')).toBeInTheDocument();
  expect(screen.getByText('Command: Unknown')).toBeInTheDocument();
  expect(screen.queryByText('Command: Live')).not.toBeInTheDocument();
});

test('labels unavailable following state as unknown instead of off', () => {
  render(<OperationalStatusBar {...baseProps} isFollowing={undefined} />);

  expect(screen.getByText('Following: UNKNOWN')).toBeInTheDocument();
  expect(screen.queryByText('Following: OFF')).not.toBeInTheDocument();
});

test('shows the active SmartTracker model in the compact mode status', () => {
  render(
    <OperationalStatusBar
      {...baseProps}
      smartModeActive
      activeModelName="aerial-nano.pt"
    />
  );

  expect(screen.getByText('Mode: Smart: aerial-nano.pt')).toBeInTheDocument();
});
