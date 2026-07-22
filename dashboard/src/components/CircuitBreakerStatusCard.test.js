import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import CircuitBreakerStatusCard from './CircuitBreakerStatusCard';

jest.mock('../services/apiClient', () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
}));

const activeStatus = {
  available: true,
  active: true,
  configuration: {
    persisted_value: true,
    runtime_matches_persisted: true,
  },
  follower_test: {
    enabled: false,
    execution_mode: 'PX4',
    persisted_execution_mode: 'PX4',
    runtime_matches_persisted: true,
    following_active: false,
    configurable: true,
    requires_circuit_breaker: true,
    commands_sent_to_px4: null,
  },
};
const liveStatus = {
  ...activeStatus,
  active: false,
};
const followerTestStatus = {
  ...activeStatus,
  follower_test: {
    ...activeStatus.follower_test,
    enabled: true,
    execution_mode: 'COMMAND_PREVIEW',
    persisted_execution_mode: 'COMMAND_PREVIEW',
    commands_sent_to_px4: false,
  },
};

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockImplementation((url) => {
    if (url === endpoints.circuitBreakerStatus) {
      return Promise.resolve({ data: activeStatus });
    }
    return Promise.resolve({ data: { circuit_breaker: {} } });
  });
  axios.post.mockResolvedValue({ data: { status: 'success' } });
  axios.put.mockResolvedValue({ data: { success: true, applied: true } });
});

test('requires operator confirmation before explicitly permitting live commands', async () => {
  render(<CircuitBreakerStatusCard />);

  const safetyMode = await screen.findByLabelText('Blocked');
  fireEvent.click(safetyMode);

  expect(await screen.findByText('Permit live command dispatch?')).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Permit live commands' }));

  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  const [url, payload] = axios.post.mock.calls[0];
  expect(url).toBe(endpoints.circuitBreakerSetAction);
  expect(payload).toEqual(expect.objectContaining({
    enabled: false,
    confirm: true,
    idempotency_key: expect.stringMatching(/^dashboard-disable-circuit-breaker-/),
  }));
});

test('enables local follower test through the canonical execution-mode config', async () => {
  render(<CircuitBreakerStatusCard />);

  fireEvent.click(await screen.findByRole('checkbox', { name: 'Follower test' }));

  await waitFor(() => expect(axios.put).toHaveBeenCalledTimes(1));
  expect(axios.put).toHaveBeenCalledWith(
    endpoints.configUpdateParameter('Follower', 'FOLLOWER_EXECUTION_MODE'),
    { value: 'COMMAND_PREVIEW' },
    { headers: expect.objectContaining({ 'Cache-Control': expect.any(String) }) },
  );
});

test('does not offer follower test while live command dispatch is permitted', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.circuitBreakerStatus) {
      return Promise.resolve({ data: liveStatus });
    }
    return Promise.resolve({ data: { circuit_breaker: {} } });
  });
  render(<CircuitBreakerStatusCard />);

  expect(await screen.findByRole('checkbox', { name: 'Follower test' })).toBeDisabled();
});

test('requires follower test to be off before permitting live dispatch', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.circuitBreakerStatus) {
      return Promise.resolve({ data: followerTestStatus });
    }
    return Promise.resolve({ data: { circuit_breaker: {} } });
  });
  render(<CircuitBreakerStatusCard />);

  expect(await screen.findByLabelText('Blocked')).toBeDisabled();
  expect(screen.getByText('Records raw local follower intent; sends nothing to PX4.')).toBeInTheDocument();
});

test('clears a previously live state when a suppressed status poll fails', async () => {
  axios.get.mockResolvedValueOnce({ data: liveStatus });
  render(<CircuitBreakerStatusCard />);

  expect(await screen.findByText('Live command dispatch is permitted.')).toBeInTheDocument();
  axios.get.mockRejectedValueOnce(new Error('status transport failed'));

  fireEvent(window, new Event('focus'));

  expect(await screen.findByText('status transport failed')).toBeInTheDocument();
  expect(screen.queryByText('Live command dispatch is permitted.')).not.toBeInTheDocument();
});
