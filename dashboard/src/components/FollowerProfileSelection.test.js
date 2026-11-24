import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import FollowerProfileSelector from './FollowerProfileSelector';
import FollowerQuickControl from './FollowerQuickControl';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

jest.mock('../services/apiClient', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

const profiles = {
  mc_velocity_chase: { implementation_available: true, display_name: 'Multicopter Chase', control_type: 'velocity_body' },
  gm_velocity_vector: { implementation_available: true, display_name: 'Gimbal Vector', control_type: 'velocity_vector' },
  mc_velocity_position: { implementation_available: true, display_name: 'Multicopter Position', control_type: 'velocity_body' },
};

let current;
let readFailure;

const profile = (mode, extra = {}) => ({
  mode, configured_mode: mode, status: 'configured', active: false,
  display_name: profiles[mode].display_name, ...extra,
});

beforeEach(() => {
  jest.useFakeTimers();
  current = profile('mc_velocity_chase');
  readFailure = false;
  axios.get.mockImplementation(async (endpoint) => {
    if (endpoint === endpoints.followerProfiles) return { data: profiles };
    if (endpoint === endpoints.followerCurrentProfile) {
      if (readFailure) throw new Error('Refresh failed');
      return { data: { ...current } };
    }
    throw new Error(`Unexpected endpoint: ${endpoint}`);
  });
  axios.post.mockResolvedValue({ data: { status: 'success', message: 'Profile saved' } });
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

async function choose(name = 'Gimbal Vector') {
  fireEvent.mouseDown(screen.getByRole('combobox'));
  fireEvent.click(await screen.findByRole('option', { name: new RegExp(name) }));
}

async function save({ pending = false } = {}) {
  fireEvent.click(screen.getByRole('button', { name: /Save (Profile|Follower)/ }));
  const dialog = screen.queryByRole('dialog');
  if (dialog) fireEvent.click(within(dialog).getByRole('button', { name: 'Save Profile' }));
  if (!pending) {
    await act(async () => { await Promise.allSettled([axios.post.mock.results.at(-1).value]); });
  }
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
}

async function poll() {
  await act(async () => { jest.advanceTimersByTime(2000); });
}

describe.each([
  ['full selector', FollowerProfileSelector],
  ['quick control', FollowerQuickControl],
])('%s draft selection', (_, Component) => {
  async function mount() {
    render(<Component />);
    await screen.findByRole('combobox');
  }

  test('keeps a changed selection before Save and sends no automatic mutation', async () => {
    await mount();
    await choose();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeEnabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('preserves the draft through same-mode polls and external changes while editing', async () => {
    await mount();
    await choose();
    current = { ...current, current_field_values: { vel_body_fwd: 2 } };
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    current = profile('mc_velocity_position');
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('preserves the draft after a rejected save and later polls', async () => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
    axios.post.mockRejectedValueOnce(new Error('Save failed'));
    await mount();
    await choose();
    await save();
    await screen.findByText('Save failed');
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeEnabled();
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith(endpoints.followerSwitchProfile, { profile_name: 'gm_velocity_vector' });
  });

  test('preserves the draft if refresh fails, including readback after an acknowledged save', async () => {
    jest.spyOn(console, 'error').mockImplementation(() => {});
    await mount();
    await choose();
    readFailure = true;
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    await save();
    await screen.findByText('Profile saved');
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeEnabled();
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  test('competing configured readback remains authoritative status without acknowledging the draft', async () => {
    await mount();
    await choose();
    current = profile('mc_velocity_position');
    await save();
    await screen.findByText('Profile saved');
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeEnabled();
    expect(screen.getByText('Multicopter Position', { selector: 'span' })).toBeInTheDocument();
    current = profile('gm_velocity_vector');
    await poll();
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeDisabled();
    current = profile('mc_velocity_position');
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Multicopter Position');
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  test('observed acknowledgement clears the draft without emptying the selector', async () => {
    await mount();
    await choose();
    current = profile('gm_velocity_vector');
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeDisabled();
    current = profile('mc_velocity_position');
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Multicopter Position');
    expect(axios.post).not.toHaveBeenCalled();
  });

  test.each(['instance_id', 'runtime_id', 'source'])('a changed observed %s discards the old draft without saving', async field => {
    current = profile('mc_velocity_chase', { [field]: 'first' });
    await mount();
    await choose();
    current = profile('mc_velocity_position', { [field]: 'second' });
    await poll();
    expect(screen.getByRole('combobox')).toHaveTextContent('Multicopter Position');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test.each([{ active: true }, { status: 'engaged' }])('blocks draft and save while following is active: %j', async status => {
    current = profile('mc_velocity_chase', status);
    await mount();
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('button', { name: /Save (Profile|Follower)/ })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  test('a poll during the pending save cannot enable a second save', async () => {
    let resolve;
    axios.post.mockReturnValueOnce(new Promise(done => { resolve = done; }));
    await mount();
    await choose();
    await save({ pending: true });
    await poll();
    expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-disabled', 'true');
    await act(async () => {
      current = profile('gm_velocity_vector');
      resolve({ data: { status: 'success', message: 'Profile saved' } });
    });
    await screen.findByText('Profile saved');
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(axios.post).toHaveBeenCalledTimes(1);
  });

  test('an aborted older read cannot replace the current backend state or draft', async () => {
    let resolveOld;
    let first = true;
    axios.get.mockImplementation(async endpoint => {
      if (endpoint === endpoints.followerProfiles) return { data: profiles };
      if (first) {
        first = false;
        return new Promise(resolve => { resolveOld = resolve; });
      }
      return { data: { ...current } };
    });
    render(<Component />);
    current = profile('mc_velocity_position');
    await poll();
    await screen.findByRole('combobox');
    await choose();
    await act(async () => { resolveOld({ data: profile('mc_velocity_chase') }); });
    expect(screen.getByRole('combobox')).toHaveTextContent('Gimbal Vector');
    expect(screen.getByText('Multicopter Position', { selector: 'span' })).toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });
});

test('an engaged update also blocks an already-open confirmation dialog', async () => {
  render(<FollowerProfileSelector />);
  await screen.findByRole('combobox');
  await choose();
  fireEvent.click(screen.getByRole('button', { name: 'Save Profile' }));
  const dialog = screen.getByRole('dialog');
  current = profile('mc_velocity_chase', { active: true });
  await poll();
  expect(within(dialog).getByRole('button', { name: 'Save Profile' })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});
