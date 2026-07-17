import { render, screen } from '@testing-library/react';
import TrackerDataDisplay from './TrackerDataDisplay';

const inactiveVisibleGimbalStatus = {
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
    },
    tracking: {
      value: 'TARGET_LOST',
      type: 'tracking_status',
      display_name: 'Tracking'
    }
  },
  raw_data: {
    connection_status: 'receiving',
    has_output: true,
    gimbal_tracking_active: false,
    usable_for_following: false
  }
};

test('renders inactive visible tracker output without implying follower usability', () => {
  render(
    <TrackerDataDisplay
      currentStatus={inactiveVisibleGimbalStatus}
      schema={{ tracker_data_types: {} }}
    />
  );

  expect(screen.queryByText('No Tracker Output')).not.toBeInTheDocument();
  expect(screen.getByText('Output Visible')).toBeInTheDocument();
  expect(screen.getByText('Not For Follow')).toBeInTheDocument();
  expect(screen.getByText(/active target tracking is not confirmed/i)).toBeInTheDocument();
  expect(screen.getByText('RECEIVING')).toBeInTheDocument();
  expect(screen.getByText(/Y:12 deg/)).toBeInTheDocument();
});

test('keeps no-output state distinct from inactive visible output', () => {
  render(<TrackerDataDisplay currentStatus={{ active: false, has_output: false }} />);

  expect(screen.getByText('No Tracker Output')).toBeInTheDocument();
  expect(screen.getByText(/connect an external tracker/i)).toBeInTheDocument();
});
