import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import FollowerQuickControl from './FollowerQuickControl';

let mockProfiles;
let mockCurrentProfile;
let mockSwitchProfile;

jest.mock('../hooks/useFollowerSchema', () => ({
  useFollowerProfiles: () => ({
    profiles: mockProfiles,
    loading: false,
  }),
  useCurrentFollowerProfile: () => ({
    currentProfile: mockCurrentProfile,
    switchProfile: mockSwitchProfile,
    loading: false,
    isTransitioning: false,
  }),
}));

beforeEach(() => {
  mockProfiles = {
    mc_velocity_chase: {
      implementation_available: true,
      display_name: 'Multicopter Chase',
      control_type: 'velocity_body',
    },
    gm_velocity_vector: {
      implementation_available: true,
      display_name: 'Gimbal Vector',
      control_type: 'velocity_vector',
    },
  };
  mockCurrentProfile = {
    status: 'configured',
    mode: 'mc_velocity_chase',
    display_name: 'Multicopter Chase',
    control_type: 'velocity_body',
  };
  mockSwitchProfile = jest.fn().mockResolvedValue({
    success: true,
    message: 'Follower profile saved',
  });
});

afterEach(() => {
  jest.clearAllMocks();
});

test('shows the persisted profile and disables a no-op save', () => {
  render(<FollowerQuickControl />);

  expect(screen.getByText('Saved')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Save Follower/ })).toBeDisabled();
});

test('saves a changed profile without requiring a process restart', async () => {
  render(<FollowerQuickControl />);

  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(screen.getByRole('option', { name: /Gimbal Vector/ }));
  fireEvent.click(screen.getByRole('button', { name: /Save Follower/ }));

  await waitFor(() => {
    expect(mockSwitchProfile).toHaveBeenCalledWith('gm_velocity_vector');
  });
});

test('blocks profile changes while following is engaged', () => {
  mockCurrentProfile = {
    ...mockCurrentProfile,
    status: 'engaged',
  };

  render(<FollowerQuickControl />);

  expect(screen.getByText('Active')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Save Follower/ })).toBeDisabled();
  expect(
    screen.getByText(/Stop following before changing the command profile/i)
  ).toBeInTheDocument();
});
