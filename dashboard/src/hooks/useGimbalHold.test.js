import { act, renderHook } from '@testing-library/react';
import useGimbalHold from './useGimbalHold';

const guard = { camera_id: 'camera-1', camera_generation: '1', source_epoch: 'source-1' };
const cameraContext = { guard, client_id: 'dashboard-test' };
const parametersFor = () => ({ camera_context: cameraContext, speed_deg_s: 10, duration_ms: 250 });
const success = { status: 'success', result: { manual: { state: 'preparing' } } };
const pointer = (pointerId = 1) => ({
  button: 0, isPrimary: true, pointerId, preventDefault: jest.fn(),
  currentTarget: { setPointerCapture: jest.fn() },
});
function setup(execute = jest.fn().mockResolvedValue(success)) {
  const control = {
    enabled: true, execute, canOperate: () => true,
    status: {
      connected: true, available: true, following_active: false, guard,
      capabilities: ['pan', 'tilt', 'stop', 'manual_begin', 'manual_update'],
      motion_settings: { max_speed_deg_s: 30 },
    },
  };
  return { control, execute, ...renderHook(({ current }) => useGimbalHold(current, parametersFor), {
    initialProps: { current: control },
  }) };
}
const press = (result, axis = 'pan', direction = 1) => act(() => {
  result.current.handlers(axis, direction).onPointerDown(pointer());
});
const release = result => act(() => result.current.handlers('pan', 1).onPointerUp(pointer()));
const tick = async () => act(async () => { jest.advanceTimersByTime(100); });
beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('release before begin response sends scoped Stop and never arms delayed movement', async () => {
  let accept;
  const execute = jest.fn(operation => operation === 'manual_begin'
    ? new Promise(resolve => { accept = resolve; }) : Promise.resolve(success));
  const { result } = setup(execute);
  press(result);
  const begin = execute.mock.calls[0][1];
  expect(begin).toEqual({
    camera_context: cameraContext, gesture_id: expect.any(String), sequence: 0,
    intent: { axis: 'pan', value: 1 / 3 },
  });
  release(result);
  expect(execute).toHaveBeenLastCalledWith('stop', {
    camera_context: cameraContext, gesture_id: begin.gesture_id, sequence: 1,
  }, { preserveError: true });
  await act(async () => accept(success));
  await tick();
  expect(execute.mock.calls.map(([operation]) => operation)).toEqual(['manual_begin', 'stop']);
});

test('begin acknowledgement authorizes first renewal; pending updates never accumulate', async () => {
  let acceptUpdate;
  const execute = jest.fn(operation => operation === 'manual_update'
    ? new Promise(resolve => { acceptUpdate = resolve; }) : Promise.resolve(success));
  const { result } = setup(execute);
  await act(async () => press(result));
  expect(execute.mock.calls.map(([operation]) => operation)).toEqual(['manual_begin', 'manual_update']);
  expect(execute.mock.calls[1][1].sequence).toBe(1);
  await act(async () => jest.advanceTimersByTime(600));
  expect(execute).toHaveBeenCalledTimes(2);
  await act(async () => acceptUpdate(success));
  await tick();
  expect(execute).toHaveBeenCalledTimes(3);
  expect(execute.mock.calls[2][1].sequence).toBe(2);
  release(result);
  expect(execute.mock.calls[3][0]).toBe('stop');
  await act(async () => acceptUpdate(success));
  await tick();
  expect(execute).toHaveBeenCalledTimes(4);
});

test('held gesture renews beyond five and ten seconds and stops exactly at release', async () => {
  const { result, execute } = setup();
  await act(async () => press(result));
  for (let index = 0; index < 110; index += 1) await tick();
  expect(result.current.activeKey).toBe('pan:1');
  const updates = execute.mock.calls.filter(([operation]) => operation === 'manual_update');
  expect(updates).toHaveLength(111);
  expect(updates.at(-1)[1].sequence).toBe(111);
  release(result);
  const count = execute.mock.calls.length;
  await tick();
  expect(execute).toHaveBeenCalledTimes(count);
  expect(result.current.activeKey).toBe(null);
});

test.each(['camera_generation', 'source_epoch', 'camera_id'])('%s change stops with captured ownership', async field => {
  const { result, control, execute, rerender } = setup();
  await act(async () => press(result));
  rerender({ current: { ...control, status: { ...control.status, guard: { ...guard, [field]: 'changed' } } } });
  expect(execute).toHaveBeenLastCalledWith('stop', expect.objectContaining({ camera_context: cameraContext }), { preserveError: true });
  expect(result.current.activeKey).toBe(null);
});

test('backend expiry ends renewal and does not silently begin another gesture', async () => {
  const execute = jest.fn(operation => Promise.resolve(operation === 'manual_update'
    ? { status: 'success', result: { manual: { state: 'expired' } } } : success));
  const { result } = setup(execute);
  await act(async () => press(result));
  expect(result.current.activeKey).toBe(null);
  await tick();
  expect(execute.mock.calls.map(([operation]) => operation)).toEqual(['manual_begin', 'manual_update', 'stop']);
});

test('late rejection from released gesture cannot stop the replacement gesture', async () => {
  let rejectOld;
  const execute = jest.fn().mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }))
    .mockResolvedValue(success);
  const { result } = setup(execute);
  press(result);
  release(result);
  await act(async () => press(result, 'tilt', -1));
  const count = execute.mock.calls.length;
  await act(async () => rejectOld(new Error('late response')));
  expect(execute).toHaveBeenCalledTimes(count);
  expect(result.current.activeKey).toBe('tilt:-1');
});
