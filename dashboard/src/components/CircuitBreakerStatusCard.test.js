import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import CircuitBreakerStatusCard from './CircuitBreakerStatusCard';

jest.mock('../services/apiClient', () => ({
  get: jest.fn(),
  post: jest.fn(),
}));

const activeStatus = {
  available: true,
  active: true,
  safety_bypass: false,
  configuration: {
    persisted_value: true,
    runtime_matches_persisted: true,
  },
  safety_bypass_persisted: false,
  safety_bypass_runtime_matches_persisted: true,
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
});

test('requires operator confirmation before explicitly permitting live commands', async () => {
  render(<CircuitBreakerStatusCard />);

  const safetyMode = await screen.findByLabelText('Testing');
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

test('uses an explicit idempotent state action for the safety bypass', async () => {
  render(<CircuitBreakerStatusCard />);

  const safetyBypass = await screen.findByLabelText('OFF');
  fireEvent.click(safetyBypass);

  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  const [url, payload] = axios.post.mock.calls[0];
  expect(url).toBe(endpoints.circuitBreakerSafetyBypassSetAction);
  expect(payload).toEqual(expect.objectContaining({
    enabled: true,
    confirm: true,
    idempotency_key: expect.stringMatching(
      /^dashboard-enable-circuit-breaker-safety-bypass-/,
    ),
  }));
});
