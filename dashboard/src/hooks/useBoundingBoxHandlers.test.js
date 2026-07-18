import { act, renderHook, waitFor } from '@testing-library/react';
import useBoundingBoxHandlers, {
  buildNormalizedBoundingBox,
  resolveDefaultBoundingBoxSize,
} from './useBoundingBoxHandlers';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';

jest.mock('../services/apiClient', () => ({
  apiFetchJson: jest.fn(),
}));

test('uses the documented eight-percent ROI when the environment value is absent', () => {
  expect(resolveDefaultBoundingBoxSize(undefined)).toBe(0.08);
  expect(resolveDefaultBoundingBoxSize('not-a-number')).toBe(0.08);
  expect(resolveDefaultBoundingBoxSize('1.5')).toBe(0.08);
});

test('clamps a click-centered ROI inside the video surface', () => {
  const selection = buildNormalizedBoundingBox({
    start: { x: 2, y: 3 },
    current: { x: 2, y: 3 },
    containerWidth: 200,
    containerHeight: 100,
    defaultSize: 0.1,
  });

  expect(selection.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0,
    y: 0,
    width: 0.1,
    height: 0.1,
  });
  expect(selection.display).toEqual({ left: 0, top: 0, width: 20, height: 10 });
});

test('treats a thin drag as a bounded default ROI instead of zero-area input', () => {
  const selection = buildNormalizedBoundingBox({
    start: { x: 100, y: 50 },
    current: { x: 180, y: 52 },
    containerWidth: 200,
    containerHeight: 100,
    defaultSize: 0.1,
  });

  expect(selection.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0.45,
    y: 0.45,
    width: 0.1,
    height: 0.1,
  });
});

test('normalizes a real drag and keeps its explicit coordinate space', () => {
  const selection = buildNormalizedBoundingBox({
    start: { x: 150, y: 80 },
    current: { x: 50, y: 20 },
    containerWidth: 200,
    containerHeight: 100,
    defaultSize: 0.1,
  });

  expect(selection.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0.25,
    y: 0.2,
    width: 0.5,
    height: 0.6,
  });
});

test('normalizes selection against visible media instead of letterbox padding', () => {
  const selection = buildNormalizedBoundingBox({
    start: { x: 250, y: 100 },
    current: { x: 850, y: 700 },
    containerWidth: 1600,
    containerHeight: 900,
    contentBounds: { left: 200, top: 0, width: 1200, height: 900 },
    defaultSize: 0.1,
  });

  expect(selection.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 50 / 1200,
    y: 100 / 900,
    width: 0.5,
    height: 600 / 900,
  });
  expect(selection.display).toEqual({ left: 250, top: 100, width: 600, height: 600 });
});

test('centers the default ROI within the visible media bounds', () => {
  const selection = buildNormalizedBoundingBox({
    start: { x: 200, y: 450 },
    current: { x: 200, y: 450 },
    containerWidth: 1600,
    containerHeight: 900,
    contentBounds: { left: 200, top: 0, width: 1200, height: 900 },
    defaultSize: 0.1,
  });

  expect(selection.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0,
    y: 0.45,
    width: 0.1,
    height: 0.1,
  });
  expect(selection.display.left).toBe(200);
});

test('submits normalized release coordinates without a final move and matches the overlay', async () => {
  apiFetchJson.mockResolvedValue({ status: 'success', accepted: true });
  const setSelectionArmed = jest.fn();
  const { result } = renderHook(() => useBoundingBoxHandlers(
    true,
    setSelectionArmed,
    false,
    true,
  ));
  const interactionSurface = {
    getBoundingClientRect: () => ({ left: 100, top: 50, width: 200, height: 200 }),
    querySelector: () => ({
      videoWidth: 200,
      videoHeight: 100,
      dataset: { frameReady: 'true' },
    }),
  };
  result.current.imageRef.current = interactionSurface;
  const pointerTarget = {
    setPointerCapture: jest.fn(),
    hasPointerCapture: jest.fn(() => true),
    releasePointerCapture: jest.fn(),
  };

  act(() => {
    result.current.handlePointerDown({
      button: 0,
      pointerId: 7,
      clientX: 120,
      clientY: 120,
      currentTarget: pointerTarget,
      preventDefault: jest.fn(),
    });
  });
  expect(result.current.currentPos).toEqual({ x: 20, y: 70 });

  await act(async () => {
    await result.current.handlePointerUp({
      pointerId: 7,
      clientX: 280,
      clientY: 180,
      currentTarget: pointerTarget,
    });
  });

  await waitFor(() => expect(apiFetchJson).toHaveBeenCalledTimes(1));
  const [url, request] = apiFetchJson.mock.calls[0];
  expect(url).toBe(endpoints.trackingStartAction);
  expect(JSON.parse(request.body).bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0.1,
    y: 0.2,
    width: 0.8,
    height: 0.6,
  });
  expect(result.current.boundingBox).toEqual({
    left: 20,
    top: 70,
    width: 160,
    height: 60,
  });
  expect(setSelectionArmed).toHaveBeenLastCalledWith(true);
  expect(pointerTarget.releasePointerCapture).toHaveBeenCalledWith(7);
});

test('serializes rapid classic retargets and keeps only the newest pending ROI', async () => {
  let resolveFirst;
  apiFetchJson
    .mockImplementationOnce(() => new Promise((resolve) => {
      resolveFirst = resolve;
    }))
    .mockResolvedValueOnce({ status: 'success', accepted: true });
  const { result } = renderHook(() => useBoundingBoxHandlers(
    true,
    jest.fn(),
    false,
    true,
  ));
  result.current.imageRef.current = {
    getBoundingClientRect: () => ({ left: 100, top: 50, width: 200, height: 200 }),
    querySelector: () => ({
      videoWidth: 200,
      videoHeight: 100,
      dataset: { frameReady: 'true' },
    }),
  };
  const pointerTarget = {
    setPointerCapture: jest.fn(),
    hasPointerCapture: jest.fn(() => true),
    releasePointerCapture: jest.fn(),
  };

  let firstCompletion;
  act(() => {
    result.current.handlePointerDown({
      button: 0,
      pointerId: 1,
      clientX: 120,
      clientY: 120,
      currentTarget: pointerTarget,
      preventDefault: jest.fn(),
    });
    firstCompletion = result.current.handlePointerUp({
      pointerId: 1,
      clientX: 140,
      clientY: 130,
      currentTarget: pointerTarget,
    });
  });

  let secondCompletion;
  act(() => {
    result.current.handlePointerDown({
      button: 0,
      pointerId: 2,
      clientX: 160,
      clientY: 120,
      currentTarget: pointerTarget,
      preventDefault: jest.fn(),
    });
    secondCompletion = result.current.handlePointerUp({
      pointerId: 2,
      clientX: 180,
      clientY: 130,
      currentTarget: pointerTarget,
    });
  });

  expect(apiFetchJson).toHaveBeenCalledTimes(1);
  await act(async () => {
    resolveFirst({ status: 'success', accepted: true });
    await firstCompletion;
    await secondCompletion;
  });
  expect(apiFetchJson).toHaveBeenCalledTimes(2);
  const latestRequest = JSON.parse(apiFetchJson.mock.calls[1][1].body);
  expect(latestRequest.bbox).toEqual({
    coordinate_space: 'normalized',
    x: 0.3,
    y: 0.2,
    width: 0.1,
    height: 0.1,
  });
});

test('does not re-arm or restore a classic selection canceled while its request is pending', async () => {
  let resolveRequest;
  apiFetchJson.mockImplementationOnce(() => new Promise((resolve) => {
    resolveRequest = resolve;
  }));
  const setSelectionArmed = jest.fn();
  const { result, rerender } = renderHook(
    ({ armed }) => useBoundingBoxHandlers(armed, setSelectionArmed, false, true),
    { initialProps: { armed: true } },
  );
  result.current.imageRef.current = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 200, height: 100 }),
    querySelector: () => ({
      videoWidth: 200,
      videoHeight: 100,
      dataset: { frameReady: 'true' },
    }),
  };
  const pointerTarget = {
    setPointerCapture: jest.fn(),
    hasPointerCapture: jest.fn(() => true),
    releasePointerCapture: jest.fn(),
  };

  let completion;
  act(() => {
    result.current.handlePointerDown({
      button: 0,
      pointerId: 1,
      clientX: 40,
      clientY: 30,
      currentTarget: pointerTarget,
      preventDefault: jest.fn(),
    });
    completion = result.current.handlePointerUp({
      pointerId: 1,
      clientX: 80,
      clientY: 60,
      currentTarget: pointerTarget,
    });
  });
  await waitFor(() => expect(apiFetchJson).toHaveBeenCalledTimes(1));

  rerender({ armed: false });
  await act(async () => {
    resolveRequest({ status: 'success', accepted: true });
    await completion;
  });

  expect(setSelectionArmed).not.toHaveBeenCalled();
  expect(result.current.startPos).toBeNull();
  expect(result.current.currentPos).toBeNull();
  expect(result.current.boundingBox).toBeNull();
});
