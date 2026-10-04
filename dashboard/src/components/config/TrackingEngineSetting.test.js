import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import TrackingEngineSetting from './TrackingEngineSetting';
import axios from '../../services/apiClient';
import { endpoints } from '../../services/apiEndpoints';

jest.mock('../../services/apiClient', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock('../../hooks/useTrackerSchema', () => ({
  useAvailableTrackers: () => ({
    trackers: { available_trackers: {
      local: { name: 'KCF', request_tracker_type: 'KCF', target_engine: 'local', available: true },
      camera: { name: 'Gimbal', request_tracker_type: 'Gimbal', target_engine: 'camera', available: true },
    } },
    refetch: jest.fn(),
  }),
  useCurrentTracker: () => ({ currentTracker: { tracker_type: 'KCF' }, refetch: jest.fn() }),
}));

test('retries a failed startup save without selecting a different engine', async () => {
  axios.get.mockImplementation((url) => Promise.resolve({ data: url === endpoints.nativeTargetState
    ? { saved_engine: 'camera', allowed_actions: ['tracker_switch'], guard: { target_revision: '7' } }
    : { command: { connected: false }, telemetry: { connected: false } } }));
  axios.post.mockResolvedValue({ data: { status: 'success', result: { legacy_result: { saved: true } } } });

  render(<TrackingEngineSetting />);
  const retry = await screen.findByRole('button', { name: 'Retry save' });
  fireEvent.click(retry);

  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    endpoints.trackerSwitchAction,
    expect.objectContaining({
      tracker_type: 'KCF', persist: true, restore_engine_selection: true,
      native_context: expect.objectContaining({ binding_mode: 'companion_only' }),
    }),
  ));
});
