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

test('following permits guarded retarget and Stop but no movement or mode change', async () => {
  apiFetchJson.mockResolvedValue({ ...connected, following_active: true,
    available: false, reason: 'stop_following_first' });
  const { result, rerender } = renderHook(({ allowed }) => useGimbalControl(allowed), { initialProps: { allowed: true } });
  await waitFor(() => expect(result.current.enabled).toBe(true));
  expect(result.current.canOperate('select')).toBe(true);
  expect(result.current.canOperate('cancel')).toBe(false);
  expect(result.current.canOperate('pan')).toBe(false);
  expect(result.current.canOperate('stop')).toBe(true);
  rerender({ allowed: false });
  expect(result.current.canOperate('select')).toBe(false);
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

test('movement captures camera owner and Stop preserves the original source guard', async () => {
  const guard = { camera_id: 'camera-1', camera_generation: '1', source_epoch: 'source-1' };
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl
    ? { ...connected, guard } : { status: 'success' });
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  const captured = result.current.captureContext();
  await act(() => result.current.execute('pan', { direction: 1, camera_context: captured }));
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl
    ? { ...connected, guard: { ...guard, camera_id: 'camera-2' } } : { status: 'success' });
  await act(() => result.current.execute('stop', { camera_context: captured }));
  const requests = apiFetchJson.mock.calls.filter(([url]) => url === endpoints.gimbalControlAction);
  expect(JSON.parse(requests[0][1].body).camera_context.guard).toEqual(guard);
  expect(JSON.parse(requests[1][1].body).camera_context).toEqual(captured);
});

test('gesture renewals keep Stop available and do not refresh telemetry per update', async () => {
  const guard = { camera_id: 'camera-1', camera_generation: '1', source_epoch: 'source-1' };
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl
    ? { ...connected, guard, capabilities: [...connected.capabilities, 'manual_begin', 'manual_update'] }
    : { status: 'success', result: { manual: { state: 'preparing' } } });
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  const parameters = { gesture_id: 'gesture-1', sequence: 0, intent: { axis: 'pan', value: 0.5 } };
  await act(() => result.current.execute('manual_begin', parameters));
  await act(() => result.current.execute('manual_update', { ...parameters, sequence: 1 }));
  expect(result.current.busy).toBe(false);
  expect(result.current.canOperate('stop')).toBe(true);
  expect(result.current.status.manual.state).toBe('preparing');
  expect(apiFetchJson.mock.calls.filter(([url]) => url === endpoints.gimbalControl)).toHaveLength(1);
});

test('late movement failure after Stop does not replace the current command status', async () => {
  let rejectMovement;
  apiFetchJson.mockImplementation(url => url === endpoints.gimbalControl
    ? Promise.resolve({ ...connected, capabilities: [...connected.capabilities, 'manual_begin'] })
    : new Promise((_resolve, reject) => { rejectMovement = reject; }));
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  let movement;
  act(() => { movement = result.current.execute('manual_begin').catch(() => {}); });
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl ? connected : { status: 'success' });
  await act(() => result.current.execute('stop'));
  await act(async () => { rejectMovement(new Error('old transmission failed')); await movement; });
  expect(result.current.error).toBe(null);
});

test('Stop adopts returned ownership before the next action without waiting for a status poll', async () => {
  const guard = { camera_id: 'camera-1', camera_generation: '1', source_epoch: 'source-1' };
  const initial = { ...connected, guard, capabilities: [...connected.capabilities, 'home', 'manual_begin'] };
  const updated = { ...initial, guard: { ...guard, camera_generation: '2' } };
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl
    ? initial : { status: 'success', result: { camera_status: updated } });
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  // Deliberately retain the callback across Stop; follow-up uses current ownership.
  const execute = result.current.execute;
  await act(async () => { await execute('stop'); await execute('home'); });
  const requests = apiFetchJson.mock.calls.filter(([url]) => url === endpoints.gimbalControlAction);
  expect(JSON.parse(requests[1][1].body).camera_context.guard.camera_generation).toBe('2');
  expect(apiFetchJson.mock.calls.filter(([url]) => url === endpoints.gimbalControl)).toHaveLength(1);
});

test('automatic Stop preserves a genuine command failure for operator review', async () => {
  const initial = { ...connected, capabilities: [...connected.capabilities, 'manual_begin'] };
  apiFetchJson.mockImplementation(async url => url === endpoints.gimbalControl ? initial : { status: 'success' });
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  apiFetchJson.mockRejectedValueOnce(new Error('Camera transmission failed'));
  await act(async () => { await result.current.execute('manual_begin').catch(() => {}); });
  await act(() => result.current.execute('stop', {}, { preserveError: true }));
  expect(result.current.error).toBe('Camera transmission failed');
});

test('stopping gates new movement but keeps a retryable Stop available', async () => {
  let finish;
  apiFetchJson.mockImplementation(url => url === endpoints.gimbalControl
    ? Promise.resolve(connected) : new Promise(resolve => { finish = resolve; }));
  const { result } = renderHook(() => useGimbalControl(true));
  await waitFor(() => expect(result.current.enabled).toBe(true));
  let stopped;
  act(() => { stopped = result.current.execute('stop'); });
  expect(result.current.canOperate('pan')).toBe(false);
  expect(result.current.canOperate('stop')).toBe(true);
  await act(async () => { finish({ status: 'success', result: { camera_status: connected } }); await stopped; });
  expect(result.current.canOperate('pan')).toBe(true);
});
