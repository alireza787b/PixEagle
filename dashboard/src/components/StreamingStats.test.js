import { fireEvent, render, screen } from '@testing-library/react';
import StreamingStats from './StreamingStats';
import { useStreamingMediaHealth } from '../hooks/useStatuses';

jest.mock('../hooks/useStatuses', () => ({
  useStreamingMediaHealth: jest.fn(),
}));

const mediaStatus = {
  totalClients: 1,
  active_method: 'websocket_jpeg',
  quality_engine: {
    clients: {
      'ws-client': {
        quality: 48,
      },
    },
  },
  frames: {
    frames_sent: 120,
    frames_dropped: 3,
    total_bandwidth_mb: 4.5,
    cache_size: 2,
  },
};

afterEach(() => {
  jest.clearAllMocks();
});

test('renders typed media-health frame counters and client summary', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: mediaStatus,
    loading: false,
  });

  render(<StreamingStats />);

  expect(screen.getByText('Stream Performance')).toBeInTheDocument();
  expect(screen.getByText('WEBSOCKET_JPEG')).toBeInTheDocument();
  expect(screen.getByText('48')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button'));

  expect(screen.getByText('Frames Sent:')).toBeInTheDocument();
  expect(screen.getByText('120')).toBeInTheDocument();
  expect(screen.getByText('Frames Dropped:')).toBeInTheDocument();
  expect(screen.getByText('3')).toBeInTheDocument();
  expect(screen.getByText('4.5 MB')).toBeInTheDocument();
  expect(screen.getByText('2 frames')).toBeInTheDocument();
});

test('handles missing adaptive quality clients without crashing', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: {
      ...mediaStatus,
      active_method: 'none',
      totalClients: 0,
      quality_engine: {},
    },
    loading: false,
  });

  render(<StreamingStats />);

  expect(screen.getByText('NONE')).toBeInTheDocument();
  expect(screen.queryByText('JPEG Quality:')).not.toBeInTheDocument();
});

test('renders loading state before first typed media-health payload', () => {
  useStreamingMediaHealth.mockReturnValue({
    streamingStatus: null,
    loading: true,
  });

  render(<StreamingStats />);

  expect(screen.getByText('Loading...')).toBeInTheDocument();
});
