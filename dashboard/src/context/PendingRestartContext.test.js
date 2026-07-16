import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import PendingRestartBanner, {
  restartAvailabilityMessage,
} from '../components/config/PendingRestartBanner';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { PendingRestartProvider } from './PendingRestartContext';

jest.mock('../services/apiClient', () => ({
  apiFetchJson: jest.fn(),
}));

const runtimeStatus = ({ pending = true, available = true } = {}) => ({
  schema_version: 1,
  source: 'config_service',
  startup_snapshot_timestamp: pending ? 1770000000 : 1770000001,
  restart_required: pending,
  pending_change_count: pending ? 1 : 0,
  pending_changes: pending ? [{
    path: 'Streaming.HTTP_STREAM_PORT',
    section: 'Streaming',
    parameter: 'HTTP_STREAM_PORT',
    change_type: 'changed',
    reload_tier: 'system_restart',
    sensitive: false,
    startup_value: 5077,
    persisted_value: 5078,
  }] : [],
  restart_action: {
    available,
  },
  timestamp: 1770000000,
});

const renderRestartUi = (routeLabel = 'settings', providerProps = {}) => render(
  <PendingRestartProvider statusPollIntervalMs={0} {...providerProps}>
    <PendingRestartBanner />
    <div data-testid="routed-page">{routeLabel}</div>
  </PendingRestartProvider>
);

describe('persistent pending restart state', () => {
  beforeEach(() => {
    apiFetchJson.mockReset();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('keeps the server-owned pending state after Later, route replacement, and provider remount', async () => {
    apiFetchJson.mockResolvedValue(runtimeStatus());

    const view = renderRestartUi('settings');

    expect(await screen.findByText('System restart required')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Restart Now' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Later' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText('System restart required')).toBeInTheDocument();

    view.rerender(
      <PendingRestartProvider statusPollIntervalMs={0}>
        <PendingRestartBanner />
        <div data-testid="routed-page">dashboard</div>
      </PendingRestartProvider>
    );
    expect(screen.getByTestId('routed-page')).toHaveTextContent('dashboard');
    expect(screen.getByText('System restart required')).toBeInTheDocument();

    view.unmount();
    renderRestartUi('tracker');
    expect(await screen.findByText('System restart required')).toBeInTheDocument();
    expect(screen.getByTestId('routed-page')).toHaveTextContent('tracker');
  });

  test('disables restart when the server capability is unavailable', async () => {
    apiFetchJson.mockResolvedValue(runtimeStatus({ available: false }));

    renderRestartUi();

    const restartButton = await screen.findByRole('button', { name: 'Restart Now' });
    expect(restartButton).toBeDisabled();
    fireEvent.click(restartButton);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(apiFetchJson).toHaveBeenCalledTimes(1);
  });

  test('shows an unavailable state after the initial status failure and recovers on retry', async () => {
    apiFetchJson
      .mockRejectedValueOnce(new Error('backend unavailable'))
      .mockResolvedValueOnce(runtimeStatus({ pending: false }));

    renderRestartUi();

    expect(await screen.findByText('Config restart status unavailable')).toBeInTheDocument();
    expect(screen.getByText('backend unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Status' }));

    await waitFor(() => {
      expect(screen.queryByText('Config restart status unavailable')).not.toBeInTheDocument();
    });
    expect(screen.queryByText('System restart required')).not.toBeInTheDocument();
    expect(apiFetchJson).toHaveBeenCalledTimes(2);
  });

  test('posts a confirmed idempotent action and polls until the backend reconnects', async () => {
    jest.spyOn(Date, 'now').mockReturnValue(1770000000000);
    jest.spyOn(Math, 'random').mockReturnValue(0.5);

    let statusRequests = 0;
    apiFetchJson.mockImplementation((url) => {
      if (url === endpoints.systemRestartAction) {
        return Promise.resolve({
          action_id: 'action-system-restart-1',
          action_type: 'system_restart',
          status: 'success',
          accepted: true,
          executed: true,
        });
      }

      if (url === endpoints.configRuntimeStatus) {
        statusRequests += 1;
        if (statusRequests <= 2) {
          return Promise.resolve(runtimeStatus());
        }
        if (statusRequests === 3) {
          return Promise.resolve(runtimeStatus());
        }
        if (statusRequests === 4) {
          return Promise.reject(new Error('backend offline'));
        }
        return Promise.resolve(runtimeStatus({ pending: false }));
      }

      return Promise.reject(new Error(`Unexpected endpoint: ${url}`));
    });

    renderRestartUi('settings', {
      reconnectInitialDelayMs: 0,
      reconnectPollIntervalMs: 0,
      maxReconnectAttempts: 3,
    });

    fireEvent.click(await screen.findByRole('button', { name: 'Restart Now' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Restart Now' }));

    await waitFor(() => {
      expect(apiFetchJson).toHaveBeenCalledWith(
        endpoints.systemRestartAction,
        expect.objectContaining({ method: 'POST' })
      );
    });
    await waitFor(() => {
      expect(screen.queryByText('System restart required')).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.queryByText('Restart requested')).not.toBeInTheDocument();
    });

    const actionCall = apiFetchJson.mock.calls.find(
      ([url]) => url === endpoints.systemRestartAction
    );
    expect(JSON.parse(actionCall[1].body)).toEqual({
      source: 'dashboard',
      reason: 'apply_pending_config_restart',
      confirm: true,
      idempotency_key: expect.stringMatching(
        /^dashboard-apply-pending-config-restart-1770000000000-[a-z0-9]+$/
      ),
      metadata: {
        ui: 'dashboard_pending_restart_banner',
      },
    });
    expect(statusRequests).toBeGreaterThanOrEqual(5);
  });
});

test('translates restart safety denials into operator guidance', () => {
  expect(restartAvailabilityMessage('following_or_offboard_active')).toBe(
    'Stop following and leave Offboard before restarting.'
  );
  expect(restartAvailabilityMessage('restart_policy_denied')).toBe(
    'Remote restart is disabled by this setup profile. Restart from the PixEagle host.'
  );
  expect(restartAvailabilityMessage('unknown')).toBe(
    'System restart is unavailable for this runtime.'
  );
});
