import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import {
  normalizeTelemetryHealth,
  useSmartModeStatus,
  useTelemetryHealth,
} from './useStatuses';

jest.mock('axios');

const degradedTelemetryHealth = {
  schema_version: 1,
  source: 'mavlink2rest',
  enabled: true,
  status: 'degraded',
  consumer_guidance: 'degraded_latest_request_failed',
  transport: {
    state: 'error',
    latest_request_ok: false,
    latest_request_result: 'failure',
    latest_request_age_s: 0.1,
    last_error: 'Connection timeout - simulated',
    endpoint: 'http://127.0.0.1:8088',
  },
  request_freshness: {
    fresh: true,
    last_success_age_s: 0.2,
    stale_timeout_s: 2.0,
    last_success_monotonic_available: true,
  },
  payload: {
    has_payload: true,
    fresh: true,
    sample_count: 2,
    available_keys: ['arm_status', 'flight_mode'],
    flight_mode: 393216,
    arm_status: 'Armed',
    payload_age_s: 0.2,
  },
  claim_boundary: 'PixEagle local MAVLink2REST client health only.',
  timestamp: 1717200000.0,
};

const usableTelemetryHealth = {
  ...degradedTelemetryHealth,
  status: 'healthy',
  consumer_guidance: 'usable',
  transport: {
    ...degradedTelemetryHealth.transport,
    state: 'connected',
    latest_request_ok: true,
    latest_request_result: 'success',
    last_error: null,
  },
};

afterEach(() => {
  jest.clearAllMocks();
});

test('normalizes degraded telemetry without treating it as usable', () => {
  const normalized = normalizeTelemetryHealth(degradedTelemetryHealth);

  expect(normalized.chipLabel).toBe('Telemetry: Degraded');
  expect(normalized.color).toBe('warning');
  expect(normalized.usableForFollowing).toBe(false);
  expect(normalized.transport.latestRequestResult).toBe('failure');
  expect(normalized.requestFreshness.fresh).toBe(true);
  expect(normalized.payload.fresh).toBe(true);
  expect(normalized.payload.flightModeLabel).toBe('393216');
  expect(normalized.payload.armStatusLabel).toBe('Armed');
});

test('normalizes disabled telemetry with cached payload as not fresh', () => {
  const normalized = normalizeTelemetryHealth({
    ...degradedTelemetryHealth,
    enabled: false,
    status: 'disabled',
    consumer_guidance: 'disabled',
    transport: {
      ...degradedTelemetryHealth.transport,
      latest_request_ok: false,
      latest_request_result: 'success',
      last_error: null,
    },
    request_freshness: {
      ...degradedTelemetryHealth.request_freshness,
      fresh: true,
    },
    payload: {
      ...degradedTelemetryHealth.payload,
      fresh: true,
    },
  });

  expect(normalized.enabled).toBe(false);
  expect(normalized.chipLabel).toBe('Telemetry: Disabled');
  expect(normalized.usableForFollowing).toBe(false);
  expect(normalized.requestFreshness.fresh).toBe(false);
  expect(normalized.payload.hasPayload).toBe(true);
  expect(normalized.payload.fresh).toBe(false);
});

test('normalizes each telemetry guidance state to distinct dashboard copy', () => {
  const expectations = {
    usable: 'Telemetry: Usable',
    degraded_latest_request_failed: 'Telemetry: Degraded',
    stale: 'Telemetry: Stale',
    unavailable: 'Telemetry: Unavailable',
    disabled: 'Telemetry: Disabled',
    connecting: 'Telemetry: Connecting',
  };

  Object.entries(expectations).forEach(([consumerGuidance, chipLabel]) => {
    const normalized = normalizeTelemetryHealth({
      enabled: consumerGuidance !== 'disabled',
      status: consumerGuidance === 'usable' ? 'healthy' : consumerGuidance,
      consumer_guidance: consumerGuidance,
      transport: {
        latest_request_ok: consumerGuidance === 'usable',
        latest_request_result: consumerGuidance === 'usable' ? 'success' : 'failure',
      },
      request_freshness: {
        fresh: consumerGuidance === 'usable',
      },
      payload: {
        has_payload: consumerGuidance === 'usable',
        fresh: consumerGuidance === 'usable',
      },
    });

    expect(normalized.chipLabel).toBe(chipLabel);
  });
});

test('useTelemetryHealth starts in connecting state before the first response', () => {
  axios.get.mockReturnValueOnce(new Promise(() => {}));

  const Probe = () => {
    const { telemetryStatus } = useTelemetryHealth(60000);
    return <div>{telemetryStatus.chipLabel}</div>;
  };

  render(<Probe />);

  expect(screen.getByText('Telemetry: Connecting')).toBeInTheDocument();
});

test('useTelemetryHealth polls the typed api v1 telemetry health endpoint', async () => {
  axios.get.mockResolvedValueOnce({ data: degradedTelemetryHealth });

  const Probe = () => {
    const { telemetryStatus } = useTelemetryHealth(60000);
    return <div>{telemetryStatus.chipLabel}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Telemetry: Degraded')).toBeInTheDocument();
  await waitFor(() => {
    expect(axios.get).toHaveBeenCalledWith(
      endpoints.telemetryHealth,
      expect.objectContaining({
        headers: expect.objectContaining({
          'Cache-Control': 'no-cache, no-store, must-revalidate',
        }),
        params: expect.objectContaining({
          _t: expect.any(Number),
        }),
      })
    );
  });
});

test('useTelemetryHealth ignores stale out-of-order responses', async () => {
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({ data: usableTelemetryHealth });

  const Probe = () => {
    const { refresh, telemetryStatus } = useTelemetryHealth(60000);
    return (
      <div>
        <span>{telemetryStatus.chipLabel}</span>
        <button type="button" onClick={() => refresh()}>refresh</button>
      </div>
    );
  };

  render(<Probe />);
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

  fireEvent.click(screen.getByRole('button', { name: 'refresh' }));

  expect(await screen.findByText('Telemetry: Usable')).toBeInTheDocument();

  await act(async () => {
    resolveFirstRequest({ data: degradedTelemetryHealth });
  });

  expect(screen.getByText('Telemetry: Usable')).toBeInTheDocument();
});

test('useTelemetryHealth replaces stale raw health on request failure', async () => {
  axios.get
    .mockResolvedValueOnce({ data: usableTelemetryHealth })
    .mockRejectedValueOnce(new Error('network down'));

  const Probe = () => {
    const { refresh, telemetryHealth, telemetryStatus } = useTelemetryHealth(60000);
    return (
      <div>
        <span>{telemetryStatus.chipLabel}</span>
        <span>{`raw:${telemetryHealth?.consumer_guidance || 'none'}`}</span>
        <button type="button" onClick={() => refresh({ suppressErrors: true })}>refresh</button>
      </div>
    );
  };

  render(<Probe />);

  expect(await screen.findByText('Telemetry: Usable')).toBeInTheDocument();
  expect(screen.getByText('raw:usable')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'refresh' }));

  expect(await screen.findByText('Telemetry: Unavailable')).toBeInTheDocument();
  expect(screen.getByText('raw:unavailable')).toBeInTheDocument();
});

test('useSmartModeStatus uses endpoint registry status URL', async () => {
  axios.get.mockResolvedValueOnce({ data: { smart_mode_active: true } });

  const Probe = () => {
    const { smartModeActive } = useSmartModeStatus(60000);
    return <div>{smartModeActive ? 'Smart on' : 'Smart off'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Smart on')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.status,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
});
