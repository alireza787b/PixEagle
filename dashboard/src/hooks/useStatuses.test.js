import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import {
  normalizeFollowingTelemetry,
  normalizeTrackingTelemetry,
  normalizeStreamingMediaHealth,
  normalizeTrackerStatus,
  normalizeTelemetryHealth,
  useFollowerStatus,
  useFollowingTelemetry,
  useSmartModeStatus,
  useStreamingMediaHealth,
  useTrackerStatus,
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

const activeFollowingTelemetry = {
  schema_version: 1,
  source: 'following_telemetry',
  status: 'active',
  consumer_guidance: 'following_active',
  following_active: true,
  profile: {
    configured_mode: 'gm_velocity_vector',
    current_mode: 'gm_velocity_vector',
    profile_valid: true,
    display_name: 'Gimbal Velocity Vector',
    control_type: 'velocity_body_offboard',
    available_fields: ['vel_body_fwd', 'yawspeed_deg_s'],
    follower_type: 'GMVelocityVectorFollower',
  },
  fields: {
    vel_body_fwd: 1.25,
    yawspeed_deg_s: 3.0,
  },
  field_source: 'active_follower',
  target_loss_handler: {
    state: 'ACTIVE',
  },
  safety_systems: {
    safety_violations_count: 0,
  },
  performance: {
    success_rate_percent: 100,
  },
  circuit_breaker_active: false,
  command_publication: {
    local_successful_publish_observed: true,
  },
  timestamp: 1717200000.0,
};

const activeTrackingTelemetry = {
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
  center: [0.2, -0.1],
  bounding_box: [0.1, 0.2, 0.3, 0.4],
  fields: {
    data_type: 'POSITION_2D',
    position_2d: [0.2, -0.1],
    normalized_bbox: [0.1, 0.2, 0.3, 0.4],
  },
  field_source: 'tracker_output',
  timestamp: 1717200000.0,
};

const activeStreamingMediaHealth = {
  schema_version: 1,
  source: 'streaming_media',
  status: 'active',
  consumer_guidance: 'serving_media',
  transports: [
    {
      name: 'http_mjpeg',
      enabled: true,
      status: 'idle',
      active_connections: 0,
      max_connections: 20,
      details: {},
    },
    {
      name: 'websocket_jpeg',
      enabled: true,
      status: 'active',
      active_connections: 1,
      max_connections: 10,
      details: {
        clients: [
          {
            id: 'ws-client',
            quality: 45,
            bandwidth_kbps: 128.5,
            frame_drops: 1,
            last_frame_age_s: 0.1,
          },
        ],
      },
    },
    {
      name: 'webrtc_signaling',
      enabled: true,
      status: 'idle',
      active_connections: 0,
      max_connections: 3,
      details: {},
    },
    {
      name: 'gstreamer_udp_h264',
      enabled: true,
      status: 'active',
      active_connections: 0,
      max_connections: null,
      details: {
        connection_semantics: 'udp_output_has_no_client_connection_count',
      },
    },
  ],
  frames: {
    source_available: true,
    preferred_source: 'osd',
    latest_frame_id: 42,
    latest_frame_age_s: 0.2,
    latest_frame_stale: false,
    stale_timeout_s: 1,
    frames_sent: 30,
    frames_dropped: 2,
    drop_ratio: 0.0625,
    total_bandwidth_mb: 1.5,
    cache_size: 1,
  },
  security: {
    required_scope: 'media:read',
  },
  config: {
    streaming_enabled: true,
    stream_fps: 10,
    stream_width: 640,
    stream_height: 480,
    adaptive_quality_enabled: true,
  },
  quality_engine: {},
  health_issues: [],
  claim_boundary: 'Process-local media transport health only.',
  timestamp: 1717200000.0,
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

test('normalizes inactive visible tracker output without treating it as follower usable', () => {
  const normalized = normalizeTrackerStatus({
    active: false,
    has_output: true,
    usable_for_following: false,
    tracker_type: 'GimbalTracker',
    data_type: 'GIMBAL_ANGLES',
  });

  expect(normalized.chipLabel).toBe('Tracking: Visible');
  expect(normalized.navLabel).toBe('Visible');
  expect(normalized.isTracking).toBe(false);
  expect(normalized.hasOutput).toBe(true);
  expect(normalized.usableForFollowing).toBe(false);
});

test('normalizes stale tracker output as not follower usable', () => {
  const normalized = normalizeTrackerStatus({
    active: true,
    has_output: true,
    raw_data: {
      data_is_stale: true,
      usable_for_following: false,
    },
  });

  expect(normalized.chipLabel).toBe('Tracking: Stale');
  expect(normalized.color).toBe('warning');
  expect(normalized.isTracking).toBe(true);
  expect(normalized.usableForFollowing).toBe(false);
  expect(normalized.dataIsStale).toBe(true);
});

test('normalizes typed following telemetry into legacy-compatible card fields', () => {
  const normalized = normalizeFollowingTelemetry(activeFollowingTelemetry);

  expect(normalized.fields.vel_body_fwd).toBe(1.25);
  expect(normalized.vel_body_fwd).toBe(1.25);
  expect(normalized.vel_x).toBe(1.25);
  expect(normalized.yaw_rate).toBe(3.0);
  expect(normalized.timestamp).toBe('2024-06-01T00:00:00.000Z');
  expect(normalized.following_active).toBe(true);
  expect(normalized.profile_name).toBe('Gimbal Velocity Vector');
  expect(normalized.manager_mode).toBe('gm_velocity_vector');
  expect(normalized.implementation_class).toBe('GMVelocityVectorFollower');
  expect(normalized.control_type).toBe('velocity_body_offboard');
  expect(normalized.available_fields).toEqual(['vel_body_fwd', 'yawspeed_deg_s']);
  expect(normalized.validation_status).toBe(true);
  expect(normalized.target_loss_handler.state).toBe('ACTIVE');
  expect(normalized.circuit_breaker_active).toBe(false);
});

test('normalizes typed tracking telemetry into legacy-compatible plot fields', () => {
  const normalized = normalizeTrackingTelemetry(activeTrackingTelemetry);

  expect(normalized.fields.position_2d).toEqual([0.2, -0.1]);
  expect(normalized.center).toEqual([0.2, -0.1]);
  expect(normalized.bounding_box).toEqual([0.1, 0.2, 0.3, 0.4]);
  expect(normalized.timestamp).toBe('2024-06-01T00:00:00.000Z');
  expect(normalized.active_tracking).toBe(true);
  expect(normalized.tracking_active).toBe(true);
  expect(normalized.tracker_started).toBe(true);
  expect(normalized.usable_for_following).toBe(true);
});

test('normalizes no-output tracking telemetry without inventing plot geometry', () => {
  const normalized = normalizeTrackingTelemetry({
    schema_version: 1,
    source: 'tracking_telemetry',
    status: 'no_output',
    consumer_guidance: 'no_output',
    has_output: false,
    active_tracking: false,
    usable_for_following: false,
    data_is_stale: false,
    center: null,
    bounding_box: null,
    fields: {},
    timestamp: 1717200000.0,
  });

  expect(normalized.center).toBeNull();
  expect(normalized.bounding_box).toBeNull();
  expect(normalized.has_output).toBe(false);
  expect(normalized.active_tracking).toBe(false);
  expect(normalized.tracker_started).toBe(false);
  expect(normalized.timestamp).toBe('2024-06-01T00:00:00.000Z');
});

test('normalizes legacy tracker telemetry for typed tracker fallback paths', () => {
  const normalized = normalizeTrackingTelemetry({
    timestamp: '2026-06-06T00:00:00.000Z',
    tracker_started: false,
    tracker_data: {
      legacy_mode: true,
      position_2d: [0.3, -0.2],
      normalized_bbox: [0.2, 0.3, 0.4, 0.5],
    },
  });

  expect(normalized.fields.position_2d).toEqual([0.3, -0.2]);
  expect(normalized.center).toEqual([0.3, -0.2]);
  expect(normalized.bounding_box).toEqual([0.2, 0.3, 0.4, 0.5]);
  expect(normalized.timestamp).toBe('2026-06-06T00:00:00.000Z');
  expect(normalized.tracker_started).toBe(false);
});

test('does not promote legacy pixel tracker boxes into normalized bounding box', () => {
  const normalized = normalizeTrackingTelemetry({
    tracker_data: {
      position_2d: [0.3, -0.2],
      bbox: [100, 120, 30, 40],
      bbox_pixel: [100, 120, 30, 40],
    },
    timestamp: 1717200000.0,
  });

  expect(normalized.center).toEqual([0.3, -0.2]);
  expect(normalized.bounding_box).toBeNull();
  expect(normalized.fields.bbox).toEqual([100, 120, 30, 40]);
  expect(normalized.fields.bbox_pixel).toEqual([100, 120, 30, 40]);
});

test('normalizes legacy follower telemetry setpoints for history plots', () => {
  const normalized = normalizeFollowingTelemetry({
    profile_name: 'Legacy Follower',
    setpoints: {
      vel_body_fwd: 0.75,
      vel_body_right: -0.25,
      vel_body_down: 0.1,
      yawspeed_deg_s: 4.5,
    },
  });

  expect(normalized.fields.vel_body_fwd).toBe(0.75);
  expect(normalized.vel_body_fwd).toBe(0.75);
  expect(normalized.vel_x).toBe(0.75);
  expect(normalized.vel_y).toBe(-0.25);
  expect(normalized.vel_z).toBe(0.1);
  expect(normalized.yaw_rate).toBe(4.5);
  expect(normalized.profile_name).toBe('Legacy Follower');
});

test('normalizes typed streaming media health into dashboard status fields', () => {
  const normalized = normalizeStreamingMediaHealth(activeStreamingMediaHealth);

  expect(normalized.chipLabel).toBe('Media: Active');
  expect(normalized.color).toBe('success');
  expect(normalized.active_method).toBe('websocket_jpeg');
  expect(normalized.methodLabel).toBe('WEBSOCKET_JPEG');
  expect(normalized.http_clients).toBe(0);
  expect(normalized.websocket_clients).toBe(1);
  expect(normalized.webrtc_clients).toBe(0);
  expect(normalized.totalClients).toBe(1);
  expect(normalized.frames.frames_sent).toBe(30);
  expect(normalized.frames.frames_dropped).toBe(2);
  expect(normalized.total_bandwidth_mb).toBe(1.5);
  expect(normalized.quality_engine.clients['ws-client'].quality).toBe(45);
  expect(normalized.transportsByName.gstreamer_udp_h264.active_connections).toBe(0);
});

test('normalizes degraded streaming media health without treating UDP as clients', () => {
  const normalized = normalizeStreamingMediaHealth({
    ...activeStreamingMediaHealth,
    status: 'degraded',
    consumer_guidance: 'operator_attention',
    transports: activeStreamingMediaHealth.transports.map((transport) => (
      transport.name === 'websocket_jpeg'
        ? { ...transport, status: 'idle', active_connections: 0, details: { clients: [] } }
        : transport
    )),
    frames: {
      ...activeStreamingMediaHealth.frames,
      latest_frame_stale: true,
    },
    health_issues: ['published_frame_stale'],
  });

  expect(normalized.chipLabel).toBe('Media: Degraded');
  expect(normalized.color).toBe('warning');
  expect(normalized.totalClients).toBe(0);
  expect(normalized.healthIssues).toEqual(['published_frame_stale']);
});

test('normalizes disabled streaming as not active even with legacy counters', () => {
  const normalized = normalizeStreamingMediaHealth({
    ...activeStreamingMediaHealth,
    config: {
      ...activeStreamingMediaHealth.config,
      streaming_enabled: false,
    },
  });

  expect(normalized.chipLabel).toBe('Media: Disabled');
  expect(normalized.color).toBe('default');
  expect(normalized.consumerGuidance).toBe('disabled');
});

test('useTrackerStatus polls typed tracker runtime status instead of legacy tracker telemetry', async () => {
  axios.get.mockResolvedValueOnce({
    data: {
      schema_version: 1,
      status: 'visible_output',
      consumer_guidance: 'diagnostic_only',
      active_tracking: false,
      has_output: true,
      usable_for_following: false,
    },
  });

  const Probe = () => {
    const trackerStatus = useTrackerStatus(60000);
    return <div>{trackerStatus.chipLabel}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Tracking: Visible')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.trackerRuntimeStatus,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
});

test('useTrackerStatus ignores stale out-of-order runtime responses', async () => {
  jest.useFakeTimers();
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({
      data: {
        schema_version: 1,
        status: 'active_usable',
        consumer_guidance: 'usable',
        active_tracking: true,
        has_output: true,
        usable_for_following: true,
        data_is_stale: false,
      },
    });

  const Probe = () => {
    const trackerStatus = useTrackerStatus(60000);
    return <div>{trackerStatus.chipLabel}</div>;
  };

  try {
    render(<Probe />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(await screen.findByText('Tracking: Active')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest({
        data: {
          schema_version: 1,
          status: 'stale_output',
          consumer_guidance: 'stale',
          active_tracking: true,
          has_output: true,
          usable_for_following: false,
          data_is_stale: true,
        },
      });
    });

    expect(screen.getByText('Tracking: Active')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('useFollowerStatus polls typed following status instead of legacy follower telemetry', async () => {
  axios.get.mockResolvedValueOnce({
    data: {
      schema_version: 1,
      source: 'following_runtime',
      status: 'active',
      consumer_guidance: 'following_active',
      following_active: true,
    },
  });

  const Probe = () => {
    const isFollowing = useFollowerStatus(60000);
    return <div>{isFollowing ? 'Following on' : 'Following off'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Following on')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.followingStatus,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
});

test('useFollowerStatus falls back to legacy follower telemetry during rolling updates', async () => {
  axios.get
    .mockRejectedValueOnce({ response: { status: 404 } })
    .mockResolvedValueOnce({ data: { following_active: true } });

  const Probe = () => {
    const isFollowing = useFollowerStatus(60000);
    return <div>{isFollowing ? 'Following on' : 'Following off'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Following on')).toBeInTheDocument();
  expect(axios.get).toHaveBeenNthCalledWith(1, endpoints.followingStatus, expect.any(Object));
  expect(axios.get).toHaveBeenNthCalledWith(2, endpoints.followerData, expect.any(Object));
});

test('useFollowerStatus ignores stale out-of-order following status responses', async () => {
  jest.useFakeTimers();
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({
      data: {
        schema_version: 1,
        source: 'following_runtime',
        status: 'active',
        consumer_guidance: 'following_active',
        following_active: true,
      },
    });

  const Probe = () => {
    const isFollowing = useFollowerStatus(60000);
    return <div>{isFollowing ? 'Following on' : 'Following off'}</div>;
  };

  try {
    render(<Probe />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(await screen.findByText('Following on')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest({
        data: {
          schema_version: 1,
          source: 'following_runtime',
          status: 'inactive',
          consumer_guidance: 'inactive',
          following_active: false,
        },
      });
    });

    expect(screen.getByText('Following on')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('useFollowingTelemetry polls typed following telemetry instead of legacy follower telemetry', async () => {
  axios.get.mockResolvedValueOnce({ data: activeFollowingTelemetry });

  const Probe = () => {
    const { followingTelemetry } = useFollowingTelemetry(60000);
    return <div>{followingTelemetry.profile_name || 'No telemetry'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Gimbal Velocity Vector')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.followingTelemetry,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
});

test('useFollowingTelemetry falls back to legacy follower telemetry during rolling updates', async () => {
  axios.get
    .mockRejectedValueOnce({ response: { status: 404 } })
    .mockResolvedValueOnce({ data: { profile_name: 'Legacy Follower', fields: { vel_body_fwd: 0 } } });

  const Probe = () => {
    const { followingTelemetry } = useFollowingTelemetry(60000);
    return <div>{followingTelemetry.profile_name || 'No telemetry'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Legacy Follower')).toBeInTheDocument();
  expect(axios.get).toHaveBeenNthCalledWith(1, endpoints.followingTelemetry, expect.any(Object));
  expect(axios.get).toHaveBeenNthCalledWith(2, endpoints.followerData, expect.any(Object));
});

test('useFollowingTelemetry ignores stale out-of-order telemetry responses', async () => {
  jest.useFakeTimers();
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({ data: activeFollowingTelemetry });

  const Probe = () => {
    const { followingTelemetry } = useFollowingTelemetry(60000);
    return <div>{followingTelemetry.profile_name || 'No telemetry'}</div>;
  };

  try {
    render(<Probe />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(await screen.findByText('Gimbal Velocity Vector')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest({
        data: {
          ...activeFollowingTelemetry,
          profile: {
            ...activeFollowingTelemetry.profile,
            display_name: 'Stale Follower',
          },
        },
      });
    });

    expect(screen.getByText('Gimbal Velocity Vector')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
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

test('useStreamingMediaHealth polls the typed api v1 media-health endpoint', async () => {
  axios.get.mockResolvedValueOnce({ data: activeStreamingMediaHealth });

  const Probe = () => {
    const { streamingStatus } = useStreamingMediaHealth(60000);
    return <div>{streamingStatus.chipLabel}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Media: Active')).toBeInTheDocument();
  await waitFor(() => {
    expect(axios.get).toHaveBeenCalledWith(
      endpoints.streamingMediaHealth,
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

test('useStreamingMediaHealth falls back to legacy streaming status only during rolling updates', async () => {
  axios.get
    .mockRejectedValueOnce({ response: { status: 404 } })
    .mockResolvedValueOnce({
      data: {
        active_method: 'websocket',
        websocket_clients: 2,
        adaptive_quality_enabled: true,
        quality_engine: {
          clients: {
            legacy: { quality: 60 },
          },
        },
      },
    });

  const Probe = () => {
    const { streamingStatus } = useStreamingMediaHealth(60000);
    return <div>{`${streamingStatus.chipLabel}:${streamingStatus.websocket_clients}`}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Media: Active:2')).toBeInTheDocument();
  expect(axios.get).toHaveBeenNthCalledWith(1, endpoints.streamingMediaHealth, expect.any(Object));
  expect(axios.get).toHaveBeenNthCalledWith(2, endpoints.streamingStatus, expect.any(Object));
});

test('useStreamingMediaHealth does not fallback on media auth failures', async () => {
  const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
  axios.get.mockRejectedValueOnce({ response: { status: 403 }, message: 'forbidden' });

  const Probe = () => {
    const { streamingStatus } = useStreamingMediaHealth(60000);
    return <div>{streamingStatus.chipLabel}</div>;
  };

  try {
    render(<Probe />);

    expect(await screen.findByText('Media: Unavailable')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(axios.get).toHaveBeenCalledWith(endpoints.streamingMediaHealth, expect.any(Object));
  } finally {
    consoleErrorSpy.mockRestore();
  }
});

test('useStreamingMediaHealth ignores stale out-of-order responses', async () => {
  jest.useFakeTimers();
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({ data: activeStreamingMediaHealth });

  const Probe = () => {
    const { streamingStatus } = useStreamingMediaHealth(60000);
    return <div>{streamingStatus.chipLabel}</div>;
  };

  try {
    render(<Probe />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(await screen.findByText('Media: Active')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest({
        data: {
          ...activeStreamingMediaHealth,
          status: 'degraded',
          consumer_guidance: 'operator_attention',
          health_issues: ['published_frame_stale'],
        },
      });
    });

    expect(screen.getByText('Media: Active')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});

test('useSmartModeStatus polls typed runtime status URL', async () => {
  axios.get.mockResolvedValueOnce({
    data: {
      schema_version: 1,
      source: 'pixeagle_runtime',
      status: 'active',
      consumer_guidance: 'vision_active',
      modes: {
        smart_mode_active: true,
        tracking_started: true,
        segmentation_active: false,
        following_active: false,
      },
    },
  });

  const Probe = () => {
    const { smartModeActive } = useSmartModeStatus(60000);
    return <div>{smartModeActive ? 'Smart on' : 'Smart off'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Smart on')).toBeInTheDocument();
  expect(axios.get).toHaveBeenCalledWith(
    endpoints.runtimeStatus,
    expect.objectContaining({
      headers: expect.objectContaining({
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      }),
    })
  );
});

test('useSmartModeStatus falls back to legacy status route for rolling updates', async () => {
  axios.get
    .mockRejectedValueOnce({ response: { status: 404 } })
    .mockResolvedValueOnce({ data: { smart_mode_active: true } });

  const Probe = () => {
    const { smartModeActive } = useSmartModeStatus(60000);
    return <div>{smartModeActive ? 'Smart on' : 'Smart off'}</div>;
  };

  render(<Probe />);

  expect(await screen.findByText('Smart on')).toBeInTheDocument();
  expect(axios.get).toHaveBeenNthCalledWith(1, endpoints.runtimeStatus, expect.any(Object));
  expect(axios.get).toHaveBeenNthCalledWith(2, endpoints.status, expect.any(Object));
});

test('useSmartModeStatus ignores stale out-of-order runtime responses', async () => {
  jest.useFakeTimers();
  let resolveFirstRequest;
  axios.get
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirstRequest = resolve;
    }))
    .mockResolvedValueOnce({
      data: {
        schema_version: 1,
        modes: {
          smart_mode_active: true,
        },
      },
    });

  const Probe = () => {
    const { smartModeActive } = useSmartModeStatus(60000);
    return <div>{smartModeActive ? 'Smart on' : 'Smart off'}</div>;
  };

  try {
    render(<Probe />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(1));

    act(() => {
      jest.advanceTimersByTime(60000);
    });

    expect(await screen.findByText('Smart on')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest({
        data: {
          schema_version: 1,
          modes: {
            smart_mode_active: false,
          },
        },
      });
    });

    expect(screen.getByText('Smart on')).toBeInTheDocument();
  } finally {
    jest.useRealTimers();
  }
});
