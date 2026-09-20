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

test('shows the authoritative CUDA runtime while SmartTracker is active', () => {
  render(
    <OperationalStatusBar
      {...baseProps}
      smartModeActive
      smartTrackerRuntime={{
        effective_device: 'cuda',
        backend: 'cuda',
        device_name: 'Test GPU',
        compute_capability: '12.0',
      }}
    />
  );

  expect(screen.getByText('Compute: CUDA')).toBeInTheDocument();
});

test('makes GPU-to-CPU fallback visible to the operator', () => {
  render(
    <OperationalStatusBar
      {...baseProps}
      smartModeActive
      smartTrackerRuntime={{
        effective_device: 'cpu',
        backend: 'cpu_torch',
        fallback_occurred: true,
        fallback_reason: 'CUDA kernel execution failed',
      }}
    />
  );

  expect(screen.getByText('Compute: CPU fallback')).toBeInTheDocument();
});


test('labels the external gimbal mode and preserves the default classic label', () => {
  const { rerender } = render(<OperationalStatusBar {...baseProps} externalMode />);
  expect(screen.getByText('Mode: Gimbal')).toBeInTheDocument();
  expect(screen.queryByText('Mode: Classic')).not.toBeInTheDocument();
  rerender(<OperationalStatusBar {...baseProps} />);
  expect(screen.getByText('Mode: Classic')).toBeInTheDocument();
});


test.each([
  ['disabled', 'Disabled'], ['target_selection', 'Ready'],
  ['target_lost', 'Target lost'], ['tracking_active', 'Tracking'],
])('external camera state %s overrides generic active tracking', (tracking_state, label) => {
  render(<OperationalStatusBar {...baseProps} externalMode
    trackerStatus={{ chipLabel: 'Tracking: Active', color: 'success', usableForFollowing: true }}
    gimbalStatus={{ connected: true, tracking_state }} />);
  expect(screen.getByText(`Tracking: ${label}`)).toBeInTheDocument();
  expect(screen.queryByText('Tracking: Active')).not.toBeInTheDocument();
});

test('disconnected external camera overrides cached tracking but leaves classic status unchanged', () => {
  const props = {
    ...baseProps,
    trackerStatus: { chipLabel: 'Tracking: Active', color: 'success', usableForFollowing: true },
    gimbalStatus: { connected: false, tracking_state: 'tracking_active' },
  };
  const { rerender } = render(<OperationalStatusBar {...props} externalMode />);
  expect(screen.getByText('Tracking: Disconnected')).toBeInTheDocument();
  expect(screen.queryByText('Tracking: Tracking')).not.toBeInTheDocument();
  rerender(<OperationalStatusBar {...props} />);
  expect(screen.getByText('Tracking: Active')).toBeInTheDocument();
});
