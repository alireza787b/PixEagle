import { fireEvent, render, screen } from '@testing-library/react';
import StreamingStatusIndicator from './StreamingStatusIndicator';
import { useStreamingMediaHealth } from '../hooks/useStatuses';

jest.mock('../hooks/useStatuses', () => ({
  useStreamingMediaHealth: jest.fn(),
}));

const activeStatus = {
  chipLabel: 'Media: Active',
  label: 'Active',
  color: 'success',
  consumerGuidance: 'serving_media',
  methodLabel: 'WEBSOCKET_JPEG',
  http_clients: 0,
  websocket_clients: 1,
  webrtc_clients: 0,
  totalClients: 1,
  adaptive_quality_enabled: true,
  config: {
    stream_width: 640,
    stream_height: 480,
    stream_fps: 10,
  },
  frames: {
    source_available: true,
    latest_frame_stale: false,
  },
  quality_engine: {
    clients: {
      'ws-client': {
        quality: 45,
        bandwidth_kbps: 128,
        encoding_time_ms: 3.2,
      },
    },
  },
  transportsByName: {
    gstreamer_udp_h264: {
      enabled: true,
      status: 'active',
      active_connections: 0,
    },
  },
  healthIssues: [],
};

afterEach(() => {
  jest.clearAllMocks();
});

test('renders typed media-health active transport and client count', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: activeStatus,
    error: null,
  });

  render(<StreamingStatusIndicator />);

  expect(screen.getByText('WEBSOCKET_JPEG | Q:45')).toBeInTheDocument();
});

test('renders degraded media-health issues without treating UDP as clients', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: {
      ...activeStatus,
      chipLabel: 'Media: Degraded',
      label: 'Degraded',
      color: 'warning',
      consumerGuidance: 'operator_attention',
      methodLabel: 'GSTREAMER_UDP_H264',
      websocket_clients: 0,
      totalClients: 0,
      frames: {
        source_available: true,
        latest_frame_stale: true,
      },
      quality_engine: {
        clients: {},
      },
      healthIssues: ['published_frame_stale'],
    },
    error: null,
  });

  render(<StreamingStatusIndicator />);
  fireEvent.click(screen.getByText('Media: Degraded | 0 clients'));

  expect(screen.getByText('Issues: published_frame_stale')).toBeInTheDocument();
  expect(screen.getByText('RTP: active')).toBeInTheDocument();
});

test('renders media-health fetch failure distinctly', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: null,
    error: new Error('forbidden'),
  });

  render(<StreamingStatusIndicator />);
  fireEvent.click(screen.getByText('Media: ? | 0 clients'));

  expect(screen.getByText('Unable to fetch media health')).toBeInTheDocument();
});
