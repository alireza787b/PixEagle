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

test('labels replay follower output as a local follower test, never live control', () => {
  renderCard({
    following_active: true,
    execution_mode: 'COMMAND_PREVIEW',
    command_preview: {
      ready: true,
      commands_sent_to_px4: false,
    },
    fields: {
      vel_x: 0.25,
      vel_y: 0,
      vel_z: 0,
      yaw_rate: 0,
    },
  });

  expect(screen.getByText('Testing')).toBeInTheDocument();
  expect(screen.getByText('Local only')).toBeInTheDocument();
  expect(screen.getByText('Follower Test Intents:')).toBeInTheDocument();
  expect(screen.getByText(/No PX4 or MAVSDK command is sent/i)).toBeInTheDocument();
  expect(screen.queryByText('Live Setpoints:')).not.toBeInTheDocument();
});

test('renders typed local-test warnings without implying PX4 access', () => {
  renderCard({
    following_active: false,
    execution_mode: 'COMMAND_PREVIEW',
    command_preview: {
      ready: true,
      safety_bypass_active: true,
      commands_sent_to_px4: false,
      warnings: [
        'Follower calculation safety checks are bypassed for this local test; '
          + 'PX4/MAVSDK command publication remains disabled.',
      ],
    },
  });

  expect(screen.getByText(/Follower calculation safety checks are bypassed/i)).toBeInTheDocument();
  expect(screen.getByText(/PX4\/MAVSDK command publication remains disabled/i)).toBeInTheDocument();
});

test('distinguishes a recorded all-zero intent from missing command generation', () => {
  mockCurrentProfile = {
    ...mockCurrentProfile,
    description: 'Maintains position; yaw and altitude control remain available.',
  };
  renderCard({
    following_active: true,
    execution_mode: 'COMMAND_PREVIEW',
    last_command_intent: {
      reason: 'mc_velocity_position_active',
      fields: {
        vel_x: 0,
        vel_y: 0,
        vel_z: 0,
        yaw_rate: 0,
      },
    },
    fields: {
      vel_x: 0,
      vel_y: 0,
      vel_z: 0,
      yaw_rate: 0,
    },
  });

  expect(screen.getByText('Intent recorded')).toBeInTheDocument();
  expect(screen.getByText('Mc velocity position active')).toBeInTheDocument();
  expect(screen.getByText(/Maintains position/i)).toBeInTheDocument();
});

test('labels fail-closed defaults as hold output', () => {
  renderCard({
    following_active: true,
    execution_mode: 'COMMAND_PREVIEW',
    command_publication: {
      failsafe_defaults_active: true,
      offboard_commander: {
        last_event: 'operator_target_retarget',
      },
    },
    fields: {
      vel_x: 0,
      vel_y: 0,
      vel_z: 0,
      yaw_rate: 0,
    },
  });

  expect(screen.getByText('Hold output')).toBeInTheDocument();
  expect(screen.getByText(/Previous intent invalidated/i)).toBeInTheDocument();
});
