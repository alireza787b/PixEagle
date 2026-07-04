import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import TrackerPage from './TrackerPage';

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
};

afterEach(() => {
  jest.clearAllMocks();
});

test('keeps tracker polling status stable while next poll is in flight', async () => {
  jest.useFakeTimers();
  let resolveSecondTracker;
  let trackerRequests = 0;

  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      trackerRequests += 1;
      if (trackerRequests === 2) {
        return new Promise((resolve) => {
          resolveSecondTracker = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: typedTrackingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  try {
    render(<TrackerPage />);

    await waitFor(() => {
      expect(screen.getByTestId('polling-status')).toHaveTextContent('success');
    });

    act(() => {
      jest.advanceTimersByTime(1000);
    });

    await waitFor(() => expect(trackerRequests).toBe(2));
    expect(screen.getByTestId('polling-status')).toHaveTextContent('success');

    await act(async () => {
      resolveSecondTracker({ status: 200, data: typedTrackingTelemetry });
    });

    expect(screen.getByTestId('polling-status')).toHaveTextContent('success');
  } finally {
    jest.useRealTimers();
  }
});
