import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FollowerStatusCard from './FollowerStatusCard';

let mockCurrentProfile;

jest.mock('../hooks/useFollowerSchema', () => ({
  useCurrentFollowerProfile: () => ({
    currentProfile: mockCurrentProfile,
    loading: false,
    error: null,
    isTransitioning: false,
  }),
}));

const renderCard = (followerData) => render(
  <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
    <FollowerStatusCard followerData={followerData} />
  </MemoryRouter>
);

beforeEach(() => {
  mockCurrentProfile = {
    status: 'engaged',
    control_type: 'velocity_body',
    validation_status: true,
    display_name: 'Velocity Follower',
    available_fields: ['vel_x', 'vel_y', 'vel_z', 'yaw_rate'],
  };
});

test('shows unavailable for missing and nonfinite live command values while preserving zero', () => {
  renderCard({
    fields: {
      vel_x: 0,
      vel_y: Number.NaN,
      vel_z: Number.POSITIVE_INFINITY,
    },
  });

  expect(screen.getByText('0.000 m/s')).toBeInTheDocument();
  expect(screen.getAllByText('--')).toHaveLength(3);
  expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
});

test('shows unavailable performance metrics without replacing genuine zero', () => {
  const { rerender } = renderCard({
    target_loss_handler: { state: 'ACTIVE' },
    performance: {
      success_rate_percent: Number.NaN,
      successful_transformations: undefined,
      total_follow_calls: Number.POSITIVE_INFINITY,
    },
  });

  expect(screen.getByText(/^Success:/)).toHaveTextContent('Success: -- (--/--)');

  rerender(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <FollowerStatusCard
        followerData={{
          target_loss_handler: { state: 'ACTIVE' },
          performance: {
            success_rate_percent: 0,
            successful_transformations: 0,
            total_follow_calls: 0,
          },
        }}
      />
    </MemoryRouter>
  );

  expect(screen.getByText(/^Success:/)).toHaveTextContent('Success: 0.0% (0/0)');
});
