import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import FollowerPage from './FollowerPage';

jest.mock('axios');

jest.mock('../hooks/useFollowerSchema', () => ({
  useFollowerSchema: () => ({
    schema: {
      command_fields: {
        vel_body_fwd: { description: 'Forward velocity' },
      },
      ui_config: {
        field_groups: {
          velocity: {
            name: 'Velocity',
            color: '#1976d2',
            fields: ['vel_body_fwd'],
          },
        },
      },
    },
    loading: false,
    error: null,
  }),
  useCurrentFollowerProfile: () => ({
    currentProfile: {
      active: true,
      display_name: 'Gimbal Velocity Vector',
      description: 'Test profile',
      control_type: 'velocity_body_offboard',
      validation_status: true,
      available_fields: ['vel_body_fwd'],
    },
    loading: false,
    error: null,
  }),
}));

jest.mock('../components/FollowerProfileSelector', () => () => (
  <div data-testid="profile-selector">Profile selector</div>
));

jest.mock('../components/ScopePlot', () => ({ trackerData, followerData }) => {
  const latestTracker = trackerData[trackerData.length - 1] || {};
  const latestFollower = followerData[followerData.length - 1] || {};
  return (
    <div data-testid="scope-plot">
      {[
        `tracker:${trackerData.length}`,
        `follower:${followerData.length}`,
        `tracker_center:${latestTracker.center ? latestTracker.center.join(',') : 'none'}`,
        `tracker_timestamp:${latestTracker.timestamp ?? 'none'}`,
        `vel_x:${latestFollower.vel_x ?? 'none'}`,
        `timestamp:${latestFollower.timestamp ?? 'none'}`,
      ].join(';')}
    </div>
  );
});

jest.mock('../components/StaticPlot', () => ({ data, dataKey }) => (
  <div data-testid={`static-plot-${dataKey}`}>{`${dataKey}:${data.length}`}</div>
));

jest.mock('../components/RawDataLog', () => ({ rawData }) => (
  <div data-testid="raw-data-log">{`raw:${rawData.length}`}</div>
));

jest.mock('../components/PollingStatusIndicator', () => ({ status }) => (
  <div data-testid="polling-status">{status}</div>
));

jest.mock('../components/DynamicFieldDisplay', () => ({ fieldValues }) => (
  <div data-testid="dynamic-fields">
    {`vel_body_fwd:${fieldValues.vel_body_fwd ?? 'none'}`}
  </div>
));

const trackerPayload = {
  timestamp: '2026-06-06T00:00:00.000Z',
  center: [0.1, 0.2],
  bounding_box: [0, 0, 0.1, 0.1],
  tracker_data: {
    legacy_mode: true,
    position_2d: [0.1, 0.2],
    normalized_bbox: [0, 0, 0.1, 0.1],
  },
};

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
    tracker_id: 'vision_tracker',
    position_2d: [0.1, 0.2],
    normalized_bbox: [0, 0, 0.1, 0.1],
  },
  field_source: 'tracker_output',
  timestamp: 1717200000.0,
};

const noOutputTrackingTelemetry = {
  schema_version: 1,
  source: 'tracking_telemetry',
  status: 'no_output',
  consumer_guidance: 'no_output',
  has_output: false,
  active_tracking: false,
  tracking_active: false,
  tracker_started: false,
  usable_for_following: false,
  data_is_stale: false,
  center: null,
  bounding_box: null,
  fields: {},
  field_source: 'unavailable',
  timestamp: 1717200000.0,
};

const typedFollowingTelemetry = {
  schema_version: 1,
  source: 'following_telemetry',
  status: 'active',
  consumer_guidance: 'following_active',
  following_active: true,
  profile: {
    configured_mode: 'gm_velocity_vector',
    current_mode: 'gm_velocity_vector',
    display_name: 'Gimbal Velocity Vector',
    control_type: 'velocity_body_offboard',
    available_fields: ['vel_body_fwd'],
    profile_valid: true,
  },
  fields: {
    vel_body_fwd: 1.25,
    vel_body_right: 0.1,
  },
  timestamp: 1717200000.0,
};

afterEach(() => {
  jest.clearAllMocks();
});

test('polls typed tracking and following telemetry for follower history visualization', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      return Promise.resolve({ status: 200, data: typedTrackingTelemetry });
    }
    if (url === endpoints.followingTelemetry) {
      return Promise.resolve({ status: 200, data: typedFollowingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  render(<FollowerPage />);

  expect(await screen.findByText('vel_body_fwd:1.25')).toBeInTheDocument();
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker:1;follower:1');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_center:0.1,0.2');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_timestamp:2024-06-01T00:00:00.000Z');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('vel_x:1.25');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('timestamp:2024-06-01T00:00:00.000Z');
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.trackingTelemetry,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.followingTelemetry,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerData, expect.any(Object));
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.followerData, expect.any(Object));
});

test('keeps follower polling status stable while next poll is in flight', async () => {
  jest.useFakeTimers();
  let resolveSecondTracker;
  let resolveSecondFollower;
  let trackerRequests = 0;
  let followerRequests = 0;

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
    if (url === endpoints.followingTelemetry) {
      followerRequests += 1;
      if (followerRequests === 2) {
        return new Promise((resolve) => {
          resolveSecondFollower = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: typedFollowingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  try {
    render(<FollowerPage />);

    await waitFor(() => {
      expect(screen.getByTestId('polling-status')).toHaveTextContent('success');
    });

    act(() => {
      jest.advanceTimersByTime(1000);
    });

    await waitFor(() => expect(followerRequests).toBe(2));
    expect(screen.getByTestId('polling-status')).toHaveTextContent('success');

    await act(async () => {
      resolveSecondTracker({ status: 200, data: typedTrackingTelemetry });
      resolveSecondFollower({ status: 200, data: typedFollowingTelemetry });
    });

    expect(screen.getByTestId('polling-status')).toHaveTextContent('success');
  } finally {
    jest.useRealTimers();
  }
});

test('falls back to legacy tracker telemetry only when typed route is missing', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      return Promise.reject({ response: { status: 404 } });
    }
    if (url === endpoints.trackerData) {
      return Promise.resolve({ status: 200, data: trackerPayload });
    }
    if (url === endpoints.followingTelemetry) {
      return Promise.resolve({ status: 200, data: typedFollowingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  render(<FollowerPage />);

  expect(await screen.findByText('vel_body_fwd:1.25')).toBeInTheDocument();
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_center:0.1,0.2');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_timestamp:2026-06-06T00:00:00.000Z');
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackingTelemetry, expect.any(Object));
  expect(axios.get).toHaveBeenCalledWith(endpoints.trackerData, expect.any(Object));
});

test('does not invent tracker plot geometry for valid typed no-output snapshots', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      return Promise.resolve({ status: 200, data: noOutputTrackingTelemetry });
    }
    if (url === endpoints.followingTelemetry) {
      return Promise.resolve({ status: 200, data: typedFollowingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  render(<FollowerPage />);

  expect(await screen.findByText('vel_body_fwd:1.25')).toBeInTheDocument();
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker:1;follower:1');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_center:none');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker_timestamp:2024-06-01T00:00:00.000Z');
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerData, expect.any(Object));
});

test('falls back to legacy follower telemetry only when typed route is missing', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      return Promise.resolve({ status: 200, data: typedTrackingTelemetry });
    }
    if (url === endpoints.followingTelemetry) {
      return Promise.reject({ response: { status: 404 } });
    }
    if (url === endpoints.followerData) {
      return Promise.resolve({
        status: 200,
        data: {
          profile_name: 'Legacy Follower',
          following_active: true,
          setpoints: {
            vel_body_fwd: 0.5,
            vel_body_right: 0.0,
          },
          timestamp: '2026-06-06T00:00:00.000Z',
        },
      });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  render(<FollowerPage />);

  expect(await screen.findByText('vel_body_fwd:0.5')).toBeInTheDocument();
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('vel_x:0.5');
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.trackerData, expect.any(Object));
  expect(axios.get).toHaveBeenCalledWith(endpoints.followingTelemetry, expect.any(Object));
  expect(axios.get).toHaveBeenCalledWith(endpoints.followerData, expect.any(Object));
});

test('ignores stale out-of-order follower history responses', async () => {
  jest.useFakeTimers();
  let resolveFirstTracker;
  let resolveFirstFollower;
  let trackerRequests = 0;
  let followerRequests = 0;

  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackingTelemetry) {
      trackerRequests += 1;
      if (trackerRequests === 1) {
        return new Promise((resolve) => {
          resolveFirstTracker = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: typedTrackingTelemetry });
    }
    if (url === endpoints.followingTelemetry) {
      followerRequests += 1;
      if (followerRequests === 1) {
        return new Promise((resolve) => {
          resolveFirstFollower = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: typedFollowingTelemetry });
    }
    return Promise.reject(new Error(`unexpected url ${url}`));
  });

  try {
    render(<FollowerPage />);
    await waitFor(() => expect(followerRequests).toBe(1));

    act(() => {
      jest.advanceTimersToNextTimer();
    });

    expect(await screen.findByText('vel_body_fwd:1.25')).toBeInTheDocument();

    await act(async () => {
      resolveFirstTracker({
        status: 200,
        data: {
          ...typedTrackingTelemetry,
          center: [9.9, 9.9],
          timestamp: 1717199999.0,
        },
      });
      resolveFirstFollower({
        status: 200,
        data: {
          ...typedFollowingTelemetry,
          fields: {
            ...typedFollowingTelemetry.fields,
            vel_body_fwd: 9.99,
          },
        },
      });
    });

    expect(screen.getByTestId('dynamic-fields')).toHaveTextContent('vel_body_fwd:1.25');
    expect(screen.getByTestId('scope-plot')).toHaveTextContent('follower:1');
  } finally {
    jest.useRealTimers();
  }
});
