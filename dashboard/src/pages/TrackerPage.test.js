import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import TrackerPage, { appendMeasuredTrackingTelemetry } from './TrackerPage';

jest.mock('axios');

jest.mock('../hooks/useTrackerSchema', () => ({
  useTrackerSchema: () => ({
    schema: {},
    loading: false,
    error: null,
  }),
  useCurrentTrackerStatus: () => ({
    currentStatus: {
      status: 'no_output',
      active_tracking: false,
      fields: {},
    },
    loading: false,
    error: null,
  }),
  useTrackerOutput: () => ({
    output: null,
    error: null,
  }),
}));

jest.mock('../components/ScopePlot', () => ({ trackerData }) => (
  <div data-testid="scope-plot">{`tracker:${trackerData.length}`}</div>
));

jest.mock('../components/StaticPlot', () => ({ data, dataKey }) => (
  <div data-testid={`static-plot-${dataKey}`}>{`${dataKey}:${data.length}`}</div>
));

jest.mock('../components/RawDataLog', () => ({ rawData }) => (
  <div data-testid="raw-data-log">{`raw:${rawData.length}`}</div>
));

jest.mock('../components/PollingStatusIndicator', () => ({ status }) => (
  <div data-testid="polling-status">{status}</div>
));

jest.mock('../components/TrackerDataDisplay', () => () => (
  <div data-testid="tracker-data-display">Tracker data</div>
));

const typedTrackingTelemetry = {
  schema_version: 1,
  source: 'tracking_telemetry',
  status: 'active_usable',
  consumer_guidance: 'usable',
  has_output: true,
  active_tracking: true,
  tracking_active: true,
  tracker_started: true,
  usable_for_following: true,
  data_is_stale: false,
  center: [0.1, 0.2],
  bounding_box: [0, 0, 0.1, 0.1],
  fields: {
    data_type: 'POSITION_2D',
    position_2d: [0.1, 0.2],
    normalized_bbox: [0, 0, 0.1, 0.1],
    confidence: 0.75,
  },
  field_source: 'tracker_output',
  timestamp: 1717200000.0,
  observed_at: 1717200000.1,
};

afterEach(() => {
  jest.clearAllMocks();
});

test('adds only unique fresh measurements to plot history', () => {
  const fresh = { ...typedTrackingTelemetry, timestamp: 10 };
  const firstHistory = appendMeasuredTrackingTelemetry([], fresh);

  expect(firstHistory).toEqual([fresh]);
  expect(appendMeasuredTrackingTelemetry(firstHistory, fresh)).toBe(firstHistory);
  expect(appendMeasuredTrackingTelemetry(firstHistory, {
    ...fresh,
    data_is_stale: true,
    observed_at: 20,
  })).toBe(firstHistory);
  expect(appendMeasuredTrackingTelemetry(firstHistory, {
    ...fresh,
    timestamp: 11,
  })).toHaveLength(2);
});

test.each([
  [
    'stale_output',
    { data_is_stale: true, usable_for_following: false },
    'stale',
    'Tracking: Stale',
  ],
  [
    'no_output',
    {
      active_tracking: false,
      tracking_active: false,
      tracker_started: false,
      has_output: false,
      center: null,
      bounding_box: null,
    },
    'inactive',
    'Tracking: No Output',
  ],
  [
    'unavailable',
    { active_tracking: false, has_output: false, center: null, bounding_box: null },
    'unavailable',
    'Tracking: Unavailable',
  ],
])('renders tracker %s independently from HTTP success', async (
  status,
  overrides,
  expectedPollingStatus,
  expectedLabel,
) => {
  axios.get.mockResolvedValueOnce({
    status: 200,
    data: {
      ...typedTrackingTelemetry,
      ...overrides,
      status,
      timestamp: Date.now() / 1000,
    },
  });

  render(<TrackerPage />);

  await waitFor(() => {
    expect(screen.getByTestId('polling-status')).toHaveTextContent(expectedPollingStatus);
  });
  expect(screen.getByText(expectedLabel)).toBeInTheDocument();
});

test('serializes polling and bounds a slow in-flight sample as stale then unavailable', async () => {
  jest.useFakeTimers();
  let resolveSecondTracker;
  let trackerRequests = 0;
  const freshTelemetry = () => ({
    ...typedTrackingTelemetry,
    timestamp: Date.now() / 1000,
  });

  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      trackerRequests += 1;
      if (trackerRequests === 2) {
        return new Promise((resolve) => {
          resolveSecondTracker = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: freshTelemetry() });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  try {
    render(<TrackerPage />);

    await waitFor(() => {
      expect(screen.getByTestId('polling-status')).toHaveTextContent('active');
    });
    expect(screen.getByText('Tracking: Active')).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(1000);
    });
    expect(trackerRequests).toBe(2);

    act(() => {
      jest.advanceTimersByTime(2000);
    });
    expect(screen.getByTestId('polling-status')).toHaveTextContent('stale');
    expect(screen.getByText('Tracking: Stale')).toBeInTheDocument();

    act(() => {
      jest.advanceTimersByTime(3000);
    });
    expect(trackerRequests).toBe(2);
    expect(screen.getByTestId('polling-status')).toHaveTextContent('unavailable');
    expect(screen.getByText('Tracking: Unavailable')).toBeInTheDocument();

    await act(async () => {
      resolveSecondTracker({ status: 200, data: freshTelemetry() });
    });

    expect(screen.getByTestId('polling-status')).toHaveTextContent('active');
    expect(screen.getByText('Tracking: Active')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});
