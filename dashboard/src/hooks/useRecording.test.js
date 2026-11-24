import { act, renderHook, waitFor } from '@testing-library/react';
import { apiFetch } from '../services/apiClient';
import { useRecording, useRecordingsList } from './useRecording';

jest.mock('../services/apiClient', () => ({
  ...jest.requireActual('../services/apiClient'),
  apiFetch: jest.fn(),
}));

const unavailableStatus = {
  recording: { state: 'unavailable' },
  storage: {
    free_gb: 0,
    total_gb: 0,
    used_percent: 0,
    warning_level: 'error',
    error: 'ValueError: recording output directory is not writable',
  },
  available: false,
  storage_available: false,
  reason: 'ValueError: recording output directory is not writable',
  timestamp: 1,
};

const response = (payload, ok = true, status = 200) => ({
  ok,
  status,
  json: async () => payload,
  text: async () => JSON.stringify(payload),
});

beforeEach(() => {
  apiFetch.mockReset();
});

test('useRecording reports an unavailable subsystem reason', async () => {
  apiFetch.mockResolvedValue(response(unavailableStatus));

  const { result } = renderHook(() => useRecording(60000));

  await waitFor(() => expect(result.current.recordingAvailable).toBe(false));
  expect(result.current.recordingUnavailableReason).toBe(unavailableStatus.reason);
  expect(result.current.storageStatus.warning_level).toBe('error');
});

test('useRecordingsList reports an unavailable subsystem reason', async () => {
  apiFetch.mockResolvedValue(response({
    recordings: [],
    count: 0,
    available: false,
    reason: 'OSError: recordings path is not writable',
    timestamp: 1,
  }));

  const { result } = renderHook(() => useRecordingsList());

  await waitFor(() => expect(result.current.available).toBe(false));
  expect(result.current.unavailableReason).toBe('OSError: recordings path is not writable');
  expect(result.current.recordings).toEqual([]);
});

test('useRecording surfaces backend status error payloads', async () => {
  apiFetch.mockImplementation((url) => {
    if (String(url).includes('/api/recording/status')) {
      return Promise.resolve(response({ ...unavailableStatus, available: true, reason: null }));
    }
    return Promise.resolve(response({
      status: 'error',
      message: 'Failed to initialize video writer',
      timestamp: 1,
    }));
  });

  const { result } = renderHook(() => useRecording(60000));

  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    await expect(result.current.startRecording()).rejects.toThrow(
      'Failed to initialize video writer'
    );
  });
});
