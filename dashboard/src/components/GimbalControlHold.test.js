import { act, fireEvent, render, screen } from '@testing-library/react';
import GimbalControlPanel from './GimbalControlPanel';

let frames;
let frameId;
beforeEach(() => {
  frames = new Map(); frameId = 0;
  jest.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => {
    frames.set(++frameId, callback); return frameId;
  });
  jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(id => frames.delete(id));
});
afterEach(() => jest.restoreAllMocks());

function setup() {
  const pending = [];
  const execute = jest.fn((operation) => operation === 'stop'
    ? Promise.resolve({ status: 'success' })
    : new Promise((resolve, reject) => pending.push({ resolve, reject })));
  const control = {
    enabled: true, busy: false, execute, canOperate: () => true,
    status: { available: true, connected: true, following_active: false,
      tracking_state: 'disabled', capabilities: ['pan', 'zoom', 'stop'] },
  };
  const rendered = render(<GimbalControlPanel control={control} />);
  const button = screen.getByRole('button', { name: 'Pan right' });
  button.setPointerCapture = jest.fn();
  button.hasPointerCapture = jest.fn(() => true);
  button.releasePointerCapture = jest.fn();
  return { ...rendered, button, execute, control, pending };
}

const pointer = (button, type, overrides = {}) => {
  const event = new MouseEvent(type, { bubbles: true, button: 0 });
  Object.defineProperties(event, {
    pointerId: { value: overrides.pointerId ?? 1 },
    pointerType: { value: overrides.pointerType ?? 'mouse' },
    isPrimary: { value: overrides.isPrimary ?? true },
  });
  fireEvent(button, event);
};
const settle = async pending => {
  await act(async () => pending.shift().resolve({ status: 'success' }));
};
const nextFrame = () => act(() => {
  const queued = [...frames.values()]; frames.clear(); queued.forEach(callback => callback());
});

test('tap completes one step and consumes its generated click', async () => {
  const { button, execute, pending } = setup();
  pointer(button, 'pointerdown');
  pointer(button, 'pointerup');
  fireEvent.click(button, { detail: 1 });
  expect(execute.mock.calls).toEqual([['pan', { direction: 1 }]]);
  await settle(pending);
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(1);
  expect(button.releasePointerCapture).toHaveBeenCalledWith(1);
});

test('touch hold waits for completion, keeps release enabled during busy, and stops repeats on release', async () => {
  const { button, execute, pending, control, rerender } = setup();
  pointer(button, 'pointerdown', { pointerType: 'touch' });
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(1);
  rerender(<GimbalControlPanel control={{ ...control, busy: true, canOperate: op => op === 'stop' }} />);
  expect(button).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Pan left' })).toBeDisabled();
  await settle(pending);
  rerender(<GimbalControlPanel control={control} />);
  nextFrame();
  expect(execute.mock.calls).toEqual([['pan', { direction: 1 }], ['pan', { direction: 1 }]]);
  pointer(button, 'pointerup', { pointerType: 'touch' });
  expect(execute).toHaveBeenLastCalledWith('stop', {});
  await settle(pending);
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(3);
});

test.each(['pointercancel', 'lostpointercapture', 'blur', 'hidden', 'unmount'])('%s aborts an in-flight gesture without queuing another step', async kind => {
  const { button, execute, pending, unmount } = setup();
  pointer(button, 'pointerdown');
  if (kind === 'blur') fireEvent(window, new Event('blur'));
  else if (kind === 'hidden') {
    jest.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    fireEvent(document, new Event('visibilitychange'));
  } else if (kind === 'unmount') unmount();
  else pointer(button, kind);
  expect(execute).toHaveBeenLastCalledWith('stop', {});
  await settle(pending);
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(2);
});

test.each(['disconnect', 'following', 'permission'])('%s ends repeat authority', async kind => {
  const { button, execute, pending, control, rerender } = setup();
  pointer(button, 'pointerdown');
  const next = { ...control, status: { ...control.status } };
  if (kind === 'disconnect') next.status.connected = false;
  if (kind === 'following') next.status.following_active = true;
  if (kind === 'permission') next.canOperate = () => false;
  rerender(<GimbalControlPanel control={next} />);
  await settle(pending);
  nextFrame();
  expect(execute.mock.calls.filter(([op]) => op === 'pan')).toHaveLength(1);
  if (kind === 'permission') expect(execute.mock.calls.filter(([op]) => op === 'stop')).toHaveLength(0);
  else expect(execute).toHaveBeenLastCalledWith('stop', {});
});

test('Stop button cancels hold even while its pulse request is pending', async () => {
  const { button, execute, pending } = setup();
  pointer(button, 'pointerdown');
  fireEvent.click(screen.getByRole('button', { name: 'Stop camera' }));
  await settle(pending);
  nextFrame();
  expect(execute.mock.calls).toEqual([['pan', { direction: 1 }], ['stop', {}]]);
});

test('keyboard hold ignores OS auto-repeat and stops on key release', async () => {
  const { button, execute, pending } = setup();
  fireEvent.keyDown(button, { key: ' ' });
  fireEvent.keyDown(button, { key: ' ', repeat: true });
  expect(execute).toHaveBeenCalledTimes(1);
  await settle(pending);
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(2);
  fireEvent.keyUp(button, { key: ' ' });
  expect(execute).toHaveBeenLastCalledWith('stop', {});
  await settle(pending);
  nextFrame();
  expect(execute).toHaveBeenCalledTimes(3);
});

test('failed pulse stops repeating and secondary touches do not start work', async () => {
  const { button, execute, pending } = setup();
  pointer(button, 'pointerdown', { isPrimary: false });
  expect(execute).not.toHaveBeenCalled();
  pointer(button, 'pointerdown');
  await act(async () => pending.shift().reject(new Error('offline')));
  nextFrame();
  expect(execute.mock.calls).toEqual([['pan', { direction: 1 }], ['stop', {}]]);
});
