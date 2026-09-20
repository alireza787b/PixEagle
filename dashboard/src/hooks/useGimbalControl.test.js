import { act, renderHook, waitFor } from '@testing-library/react';
import useGimbalControl from './useGimbalControl';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

jest.mock('../services/apiClient', () => ({ apiFetchJson: jest.fn() }));
const connected = {
  enabled: true, available: true, connected: true, following_active: false,
  tracking_state: 'ready', capabilities: ['select', 'pan', 'cancel', 'stop'],
};
beforeEach(() => apiFetchJson.mockImplementation(async (url) => (
  url === endpoints.gimbalControl ? connected : { status: 'success' }
)));
afterEach(() => jest.clearAllMocks());

test('manual selection sends confirmed typed action and waits for observed status', async () => {
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  await act(() => result.current.execute('select', { x: 0.2, y: 0.4 }));
  const request = apiFetchJson.mock.calls.find(([url]) => url === endpoints.gimbalControlAction)[1];
  expect(JSON.parse(request.body)).toEqual(expect.objectContaining({
    operation: 'select', x: 0.2, y: 0.4, source: 'dashboard', confirm: true,
    idempotency_key: expect.any(String),
  }));
  expect(result.current.status.tracking_state).toBe('ready');
});

test('following permits stop only and missing permission disables everything', async () => {
  apiFetchJson.mockResolvedValue({ ...connected, following_active: true });
  const { result, rerender } = renderHook(({ allowed }) => useGimbalControl(allowed), { initialProps: { allowed: true } });
  await waitFor(() => expect(result.current.enabled).toBe(true));
  expect(result.current.canOperate('select')).toBe(false);
  expect(result.current.canOperate('cancel')).toBe(false);
  expect(result.current.canOperate('stop')).toBe(true);
  rerender({ allowed: false });
  expect(result.current.canOperate('stop')).toBe(false);
});

test('busy guard prevents overlapping commands but leaves stop available', async () => {
  let finish;
  apiFetchJson.mockImplementation((url) => url === endpoints.gimbalControl
    ? Promise.resolve(connected) : new Promise(resolve => { finish = resolve; }));
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  let command;
  act(() => { command = result.current.execute('pan', { direction: 1 }); });
  expect(result.current.canOperate('select')).toBe(false);
  expect(result.current.canOperate('stop')).toBe(true);
  await expect(result.current.execute('pan', { direction: -1 })).rejects.toThrow('unavailable');
  await act(async () => { finish({ status: 'success' }); await command; });
  expect(result.current.busy).toBe(false);
});

test('failed status refresh keeps external mode and blocks selection', async () => {
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  apiFetchJson.mockImplementation(async url => {
    if (url === endpoints.gimbalControl) throw new Error('offline');
    return { status: 'success' };
  });
  await act(() => result.current.execute('stop'));
  expect(result.current.enabled).toBe(true);
  expect(result.current.canOperate('select')).toBe(false);
  expect(result.current.status.reason).toContain('unavailable');
  expect(result.current.canOperate('stop')).toBe(true);
  expect(result.current.canOperate('cancel')).toBe(true);
});

test('expected Stop interruption rejects the step without showing a camera error', async () => {
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  apiFetchJson.mockResolvedValue({ status: 'failure', result: {
    reason: 'camera_control_interrupted', message: 'Camera operation interrupted by stop',
  } });
  await act(async () => {
    await expect(result.current.execute('pan', { direction: 1 })).rejects.toThrow('interrupted');
  });
  expect(result.current.error).toBe(null);
  expect(result.current.busy).toBe(false);
});
