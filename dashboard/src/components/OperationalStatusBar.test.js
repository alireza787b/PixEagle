import { render, screen } from '@testing-library/react';
import OperationalStatusBar from './OperationalStatusBar';
import { normalizeTelemetryHealth } from '../hooks/useStatuses';

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
