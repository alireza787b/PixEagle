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
  const latestFollower = followerData[followerData.length - 1] || {};
  return (
    <div data-testid="scope-plot">
      {[
        `tracker:${trackerData.length}`,
        `follower:${followerData.length}`,
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

test('polls typed following telemetry for follower history visualization', async () => {
  axios.get.mockImplementation((url) => {
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
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('tracker:1;follower:1;vel_x:1.25');
  expect(screen.getByTestId('scope-plot')).toHaveTextContent('timestamp:2024-06-01T00:00:00.000Z');
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.followingTelemetry,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
  expect(axios.get).not.toHaveBeenCalledWith(endpoints.followerData, expect.any(Object));
});

test('falls back to legacy follower telemetry only when typed route is missing', async () => {
  axios.get.mockImplementation((url) => {
    if (url === endpoints.trackerData) {
      return Promise.resolve({ status: 200, data: trackerPayload });
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
    if (url === endpoints.trackerData) {
      trackerRequests += 1;
      if (trackerRequests === 1) {
        return new Promise((resolve) => {
          resolveFirstTracker = resolve;
        });
      }
      return Promise.resolve({ status: 200, data: trackerPayload });
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
          ...trackerPayload,
          timestamp: '2026-06-05T23:59:59.000Z',
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
