import { render, screen } from '@testing-library/react';
import TrackerStatusCard from './TrackerStatusCard';
import {
  useCurrentTrackerStatus,
  useTrackerSchema,
  useTrackerSelection
} from '../hooks/useTrackerSchema';

jest.mock('../hooks/useTrackerSchema', () => ({
  useTrackerSchema: jest.fn(),
  useCurrentTrackerStatus: jest.fn(),
  useTrackerSelection: jest.fn()
}));

const baseSelection = {
  availableTrackers: {
    available_trackers: {
      GimbalTracker: {
        display_name: 'External Gimbal Tracker',
        description: 'Receives gimbal angle packets from the configured provider.',
        suitable_for: ['external gimbal', 'seeker payload']
      }
    }
  },
  currentConfig: {
    configured_tracker: 'GimbalTracker',
    expected_data_type: 'GIMBAL_ANGLES',
    smart_mode_active: false
  },
  loading: false
};

beforeEach(() => {
  useTrackerSchema.mockReturnValue({ loading: false, error: null });
  useTrackerSelection.mockReturnValue(baseSelection);
});

test('shows visible but follower-blocked gimbal output on the dashboard card', () => {
  useCurrentTrackerStatus.mockReturnValue({
    loading: false,
    error: null,
    currentStatus: {
      active: false,
      has_output: true,
      usable_for_following: false,
      tracker_type: 'GimbalTracker',
      data_type: 'GIMBAL_ANGLES',
      fields: {
        angular: {
          value: [12, -4, 0],
          type: 'angular_3d',
          display_name: 'Gimbal Angles'
        }
      },
      raw_data: {
        has_output: true,
        gimbal_tracking_active: false,
        usable_for_following: false,
        connection_status: 'receiving'
      }
    }
  });

  render(<TrackerStatusCard />);

  expect(screen.getByText('Output Visible')).toBeInTheDocument();
  expect(screen.getByText('Not For Follow')).toBeInTheDocument();
  expect(screen.getByText('Visible Output:')).toBeInTheDocument();
  expect(screen.getByText(/Y:12\.0/)).toBeInTheDocument();
  expect(screen.queryByText('Ready to Start:')).not.toBeInTheDocument();
});

test('shows configured tracker information only when no runtime output exists', () => {
  useCurrentTrackerStatus.mockReturnValue({
    loading: false,
    error: null,
    currentStatus: {
      active: false,
      has_output: false,
      fields: {}
    }
  });

  render(<TrackerStatusCard />);

  expect(screen.getByText('No Output')).toBeInTheDocument();
  expect(screen.getByText('Ready to Start:')).toBeInTheDocument();
});
