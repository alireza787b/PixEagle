import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import FollowerSessionControls, { speedText, validSessionControls } from './FollowerSessionControls';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

jest.mock('../services/apiClient', () => ({ get: jest.fn(), post: jest.fn() }));
jest.mock('../context/AuthSessionContext', () => ({ useAuthSession: () => ({ hasScope: () => true }) }));

const control = { control_id: 'requested_speed', label: 'Requested speed', unit: 'm/s', minimum: 0,
  maximum: 5, step: .5, value: 3, revision: 0, available: true, increase_allowed: true };
const snapshot = (controls = [control]) => ({ source: 'native_following_status', following_active: true,
  instance_id: 'instance', runtime_id: 'runtime', follow_session_id: 'a'.repeat(32),
  follow_aircraft_uid: '42', follow_connection_generation: 'connection-1', session_controls: controls });

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: snapshot() });
  axios.post.mockResolvedValue({ data: { action_type: 'following_control_set', status: 'success', executed: true } });
});

test('uses backend steps and session identity, preserving the acknowledged value while pending', async () => {
  let finish;
  axios.post.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<FollowerSessionControls active />);
  const increase = await screen.findByRole('button', { name: 'Increase requested speed by 0.5 m/s' });
  fireEvent.click(increase);
  expect(axios.post).toHaveBeenCalledWith(endpoints.followingControlAction, expect.objectContaining({
    instance_id: 'instance', runtime_id: 'runtime', follow_session_id: 'a'.repeat(32), aircraft_uid: '42',
    connection_generation: 'connection-1', control_id: 'requested_speed', value: 3.5, expected_revision: 0,
  }), expect.anything());
  expect(screen.getByText('3.0 m/s')).toBeInTheDocument();
  expect(increase).toBeDisabled();
  fireEvent.click(increase);
  expect(axios.post).toHaveBeenCalledTimes(1);
  axios.get.mockResolvedValue({ data: snapshot([{ ...control, value: 3.5, revision: 1 }]) });
  await act(async () => finish({ data: { action_type: 'following_control_set', status: 'success', executed: true } }));
  await screen.findByText('3.5 m/s');
});

test('recovery permits reductions but blocks increases', async () => {
  axios.get.mockResolvedValue({ data: snapshot([{ ...control, increase_allowed: false, limiting_reason: 'target_recovery' }]) });
  render(<FollowerSessionControls active />);
  expect(await screen.findByRole('button', { name: /Increase requested speed/ })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: /Decrease requested speed/ }));
  expect(axios.post.mock.calls[0][1].value).toBe(2.5);
  await waitFor(() => expect(screen.getByRole('button', { name: /Decrease requested speed/ })).not.toBeDisabled());
});

test('unsupported backends show no speed control', async () => {
  axios.get.mockResolvedValue({ data: snapshot([]) });
  render(<FollowerSessionControls active />);
  await waitFor(() => expect(axios.get).toHaveBeenCalled());
  expect(screen.queryByText('Requested speed')).not.toBeInTheDocument();
});

test('conflict refreshes without replaying an adjustment', async () => {
  axios.post.mockRejectedValue({ response: { status: 409 } });
  render(<FollowerSessionControls active />);
  fireEvent.click(await screen.findByRole('button', { name: /Increase requested speed/ }));
  await screen.findByText(/Speed or session changed/);
  expect(axios.post).toHaveBeenCalledTimes(1);
  expect(axios.get.mock.calls.length).toBeGreaterThan(1);
});

test('ending the session hides its values and cancels pending transport without replay', async () => {
  axios.post.mockImplementation(() => new Promise(() => {}));
  const { rerender } = render(<FollowerSessionControls active />);
  fireEvent.click(await screen.findByRole('button', { name: /Increase requested speed/ }));
  const signal = axios.post.mock.calls[0][2].signal;
  rerender(<FollowerSessionControls active={false} />);
  expect(signal.aborted).toBe(true);
  expect(screen.queryByText('Requested speed')).not.toBeInTheDocument();
  expect(axios.post).toHaveBeenCalledTimes(1);
});

test.each([NaN, Infinity, -1])('rejects malformed capability value %s', (value) => {
  expect(validSessionControls([{ ...control, value }])).toBe(false);
});

test.each([['3.25', 3.25], ['0.25', .25], ['3.0', 3]])('shows the acknowledged precision %s', (text, value) => {
  expect(speedText(value)).toBe(text);
});

test.each(['session', 'revision'])('a held press cannot adjust a changed %s', async (change) => {
  jest.useFakeTimers();
  try {
    render(<FollowerSessionControls active />);
    await act(async () => {});
    const increase = screen.getByRole('button', { name: /Increase requested speed/ });
    fireEvent.pointerDown(increase);
    const next = change === 'session' ? { ...snapshot(), follow_session_id: 'b'.repeat(32) }
      : snapshot([{ ...control, revision: 1, value: 2.5 }]);
    axios.get.mockResolvedValue({ data: next });
    await act(async () => jest.advanceTimersByTime(1000));
    fireEvent.click(increase, { detail: 1 });
    expect(axios.post).not.toHaveBeenCalled();
    fireEvent.pointerDown(increase);
    fireEvent.click(increase, { detail: 1 });
    await act(async () => {});
    expect(axios.post).toHaveBeenCalledTimes(1);
  } finally {
    jest.useRealTimers();
  }
});

test('cancelled pointer input never applies after fresh status returns', async () => {
  render(<FollowerSessionControls active />);
  const increase = await screen.findByRole('button', { name: /Increase requested speed/ });
  fireEvent.pointerDown(increase);
  fireEvent.pointerCancel(increase);
  fireEvent.click(increase, { detail: 1 });
  expect(axios.post).not.toHaveBeenCalled();
});

test('an unbounded session override can exceed configured limits and reset uses the same action', async () => {
  axios.get.mockResolvedValue({ data: snapshot([{ ...control, maximum: null, value: 5,
    configured_maximum: 3, override_active: true, reset_supported: true }]) });
  render(<FollowerSessionControls active />);
  const increase = await screen.findByRole('button', { name: /Increase requested speed/ });
  fireEvent.click(increase);
  expect(axios.post.mock.calls[0][1].value).toBe(5.5);
  await waitFor(() => expect(increase).not.toBeDisabled());
  const restore = screen.getByRole('button', { name: 'Restore configured velocity limits' });
  increase.focus();
  fireEvent.pointerDown(restore);
  fireEvent.blur(increase);
  restore.focus();
  fireEvent.click(restore, { detail: 1 });
  expect(axios.post.mock.calls[1][1].value).toBeNull();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Restore configured velocity limits' })).not.toBeDisabled());
});
