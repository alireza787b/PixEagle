import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import BoundingBoxDrawer from './BoundingBoxDrawer';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';

let mockHasScope = () => true;
let mockVideoMedia = { width: 200, height: 100, frameReady: true };

jest.mock('../services/apiClient', () => ({
  apiFetchJson: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: mockHasScope,
  }),
}));

jest.mock('./VideoStream', () => function MockVideoStream({ showOperatorOverlays }) {
  return (
    <canvas
      data-testid="video-stream"
      data-video-media="true"
      data-frame-ready={mockVideoMedia.frameReady ? 'true' : 'false'}
      data-operator-overlays={showOperatorOverlays ? 'true' : 'false'}
      width={mockVideoMedia.width}
      height={mockVideoMedia.height}
    />
  );
});

beforeEach(() => {
  mockVideoMedia = { width: 200, height: 100, frameReady: true };
  apiFetchJson.mockResolvedValue({ status: 'success' });
});

afterEach(() => {
  mockHasScope = () => true;
  jest.clearAllMocks();
});

const renderDrawer = (options = {}) => {
  const smartModeActive = Object.prototype.hasOwnProperty.call(options, 'smartModeActive')
    ? options.smartModeActive
    : true;
  const { selectionArmed } = options;
  const imageRef = { current: null };
  const pointerHandlers = {
    handlePointerDown: jest.fn(),
    handlePointerMove: jest.fn(),
    handlePointerUp: jest.fn(),
  };
  const view = render(
    <BoundingBoxDrawer
      isTracking={false}
      selectionArmed={selectionArmed}
      imageRef={imageRef}
      startPos={null}
      currentPos={null}
      boundingBox={null}
      {...pointerHandlers}
      videoSrc="/video_feed"
      protocol="mjpeg"
      smartModeActive={smartModeActive}
      showOperatorOverlays={options.showOperatorOverlays}
      externalControl={options.externalControl}
    />
  );
  const drawSurface = screen.getByTestId('bounding-box-draw-surface');
  drawSurface.getBoundingClientRect = jest.fn(() => ({
    left: 10,
    top: 20,
    width: 200,
    height: 100,
    right: 210,
    bottom: 120,
  }));
  return { ...view, drawSurface, pointerHandlers };
};

const renderSmartDrawer = () => renderDrawer({ smartModeActive: true });

test('explains how to arm classic target selection when the video is clicked', async () => {
  const { drawSurface } = renderDrawer({
    smartModeActive: false,
    selectionArmed: false,
  });

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Selection paused'
  );
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('enters fullscreen without triggering target selection', async () => {
  const { drawSurface } = renderDrawer({ smartModeActive: true });
  drawSurface.requestFullscreen = jest.fn().mockResolvedValue(undefined);
  fireEvent(window, new Event('resize'));

  const fullscreenButton = await screen.findByRole('button', { name: 'Fullscreen video' });
  await waitFor(() => expect(fullscreenButton).toBeEnabled());
  fireEvent.click(fullscreenButton);

  await waitFor(() => expect(drawSurface.requestFullscreen).toHaveBeenCalledTimes(1));
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('labels tracker mode explicitly on the video overlay', () => {
  const { rerender } = renderDrawer({ smartModeActive: false });

  expect(screen.getByTestId('tracker-mode-badge')).toHaveTextContent('Tracker: Classic');

  rerender(
    <BoundingBoxDrawer
      isTracking={false}
      imageRef={{ current: null }}
      startPos={null}
      currentPos={null}
      boundingBox={null}
      handlePointerDown={jest.fn()}
      handlePointerMove={jest.fn()}
      handlePointerUp={jest.fn()}
      videoSrc="/video_feed"
      protocol="mjpeg"
      smartModeActive
    />
  );

  expect(screen.getByTestId('tracker-mode-badge')).toHaveTextContent('Tracker: AI');
});

test('hides routine tracker and transport overlays when OSD is disabled', () => {
  renderDrawer({ smartModeActive: false, showOperatorOverlays: false });

  expect(screen.queryByTestId('tracker-mode-badge')).not.toBeInTheDocument();
  expect(screen.getByTestId('video-stream')).toHaveAttribute(
    'data-operator-overlays',
    'false'
  );
});

test('shows unknown mode and does not execute canvas actions until status is known', () => {
  const { drawSurface, pointerHandlers } = renderDrawer({
    smartModeActive: undefined,
    selectionArmed: true,
  });

  expect(screen.getByTestId('tracker-mode-badge')).toHaveTextContent('Tracker mode: Unknown');
  fireEvent.pointerDown(drawSurface, { clientX: 60, clientY: 70 });
  fireEvent.pointerMove(drawSurface, { clientX: 70, clientY: 75 });
  fireEvent.pointerUp(drawSurface, { clientX: 80, clientY: 80 });
  fireEvent.click(drawSurface, { clientX: 80, clientY: 80 });

  expect(pointerHandlers.handlePointerDown).not.toHaveBeenCalled();
  expect(pointerHandlers.handlePointerMove).not.toHaveBeenCalled();
  expect(pointerHandlers.handlePointerUp).not.toHaveBeenCalled();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('keeps the classic canvas read-only without action scope', () => {
  mockHasScope = () => false;
  const { drawSurface, pointerHandlers } = renderDrawer({
    smartModeActive: false,
    selectionArmed: true,
  });

  fireEvent.pointerDown(drawSurface, { clientX: 60, clientY: 70 });
  fireEvent.pointerMove(drawSurface, { clientX: 70, clientY: 75 });
  fireEvent.pointerUp(drawSurface, { clientX: 80, clientY: 80 });

  expect(pointerHandlers.handlePointerDown).not.toHaveBeenCalled();
  expect(pointerHandlers.handlePointerMove).not.toHaveBeenCalled();
  expect(pointerHandlers.handlePointerUp).not.toHaveBeenCalled();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('uses typed confirmed smart-click action with normalized coordinates', async () => {
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  await waitFor(() => {
    expect(apiFetchJson).toHaveBeenCalledWith(
      endpoints.smartClickAction,
      expect.objectContaining({
        method: 'POST',
        body: expect.any(String),
      })
    );
  });

  const request = JSON.parse(apiFetchJson.mock.calls[0][1].body);
  expect(request).toEqual(expect.objectContaining({
    source: 'dashboard',
    reason: 'smart_click',
    confirm: true,
    idempotency_key: expect.stringMatching(/^dashboard-smart-click-\d+-[a-z0-9]+$/),
    metadata: { ui: 'dashboard_video_canvas' },
    click: { coordinate_space: 'normalized', x: 0.25, y: 0.5 },
  }));
  expect(await screen.findByRole('status')).toHaveTextContent('Target selected');
});

test('keeps pending smart selection visible and announces completion', async () => {
  let resolveSelection;
  apiFetchJson.mockImplementationOnce(() => new Promise((resolve) => {
    resolveSelection = resolve;
  }));
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });
  expect(await screen.findByRole('status')).toHaveTextContent('Selecting target');

  await act(async () => {
    resolveSelection({ status: 'success' });
  });
  expect(await screen.findByRole('status')).toHaveTextContent('Target selected');
});

test('submits rapid smart clicks immediately and only reports the newest result', async () => {
  const resolvers = [];
  apiFetchJson.mockImplementation(() => new Promise((resolve) => {
    resolvers.push(resolve);
  }));
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 50, clientY: 60 });
  fireEvent.click(drawSurface, { clientX: 70, clientY: 70 });
  fireEvent.click(drawSurface, { clientX: 90, clientY: 80 });

  expect(apiFetchJson).toHaveBeenCalledTimes(3);
  expect(await screen.findByRole('status')).toHaveTextContent('Selecting target');

  await act(async () => {
    resolvers[0]({ status: 'success' });
  });
  expect(screen.getByRole('status')).toHaveTextContent('Selecting target');

  const latestRequest = JSON.parse(apiFetchJson.mock.calls[2][1].body);
  expect(latestRequest.click).toEqual({
    coordinate_space: 'normalized',
    x: 0.4,
    y: 0.6,
  });

  await act(async () => {
    resolvers[2]({ status: 'success' });
  });
  expect(await screen.findByRole('status')).toHaveTextContent('Target selected');
});

test('shows smart-click action failures to the operator', async () => {
  apiFetchJson.mockResolvedValueOnce({
    status: 'failure',
    error: 'No AI detection selected. Override not applied.',
  });
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  expect(
    await screen.findByText('No AI detection selected. Override not applied.')
  ).toBeInTheDocument();
});

test('blocks smart-click action without actions execute scope', async () => {
  mockHasScope = () => false;
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  expect(await screen.findByText('Action permission required')).toBeInTheDocument();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('rejects smart clicks in letterbox padding', async () => {
  mockVideoMedia = { width: 100, height: 100, frameReady: true };
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 30, clientY: 70 });

  expect(await screen.findByText('Select within the visible video')).toBeInTheDocument();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('rejects smart clicks until a frame is available', async () => {
  mockVideoMedia = { width: 200, height: 100, frameReady: false };
  const { drawSurface } = renderSmartDrawer();

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  expect(await screen.findByText('Video frame unavailable')).toBeInTheDocument();
  expect(apiFetchJson).not.toHaveBeenCalled();
});


test('external click uses normalized visible video coordinates without local tracker requests', () => {
  const execute = jest.fn().mockResolvedValue({ status: 'success' });
  const { drawSurface } = renderDrawer({ externalControl: { enabled: true, canOperate: () => true, execute } });
  // 2:1 video in a square container: top and bottom are letterboxed.
  drawSurface.getBoundingClientRect = () => ({ left: 10, top: 20, width: 200, height: 200 });
  fireEvent.click(drawSurface, { clientX: 60, clientY: 120 });
  expect(execute).toHaveBeenCalledWith('select', { x: 0.25, y: 0.5 });
  fireEvent.click(drawSurface, { clientX: 60, clientY: 35 });
  expect(execute).toHaveBeenCalledTimes(1);
  expect(apiFetchJson).not.toHaveBeenCalled();
  expect(screen.getByTestId('tracker-mode-badge')).toHaveTextContent('Tracker: Gimbal');
});

test('external selection is blocked when controls are unavailable', () => {
  const execute = jest.fn();
  const { drawSurface } = renderDrawer({
    selectionArmed: true,
    externalControl: { enabled: true, canOperate: () => false, execute },
  });
  fireEvent.click(drawSurface, { clientX: 110, clientY: 70 });
  fireEvent.pointerDown(drawSurface, { button: 0, clientX: 110, clientY: 70 });
  expect(execute).not.toHaveBeenCalled();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

// jsdom lacks PointerEvent; retain mouse coordinates and explicit pointer identity.
const externalPointer = (surface, type, x, y, extra = {}) => {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 });
  Object.defineProperties(event, {
    pointerId: { value: extra.pointerId ?? 7 },
    isPrimary: { value: extra.isPrimary ?? true },
    pointerType: { value: extra.pointerType ?? 'mouse' },
  });
  fireEvent(surface, event);
};
const renderExternalDrawer = (overrides = {}) => {
  const execute = jest.fn().mockResolvedValue({ status: 'success' });
  const externalControl = {
    enabled: true, status: { selection_mode: 'classic' }, canOperate: () => true,
    execute, ...overrides,
  };
  const rendered = renderDrawer({ externalControl });
  rendered.drawSurface.setPointerCapture = jest.fn();
  rendered.drawSurface.hasPointerCapture = jest.fn(() => true);
  rendered.drawSurface.releasePointerCapture = jest.fn();
  return { ...rendered, externalControl, execute };
};

test('external Classic drag uses letterboxed image dimensions and consumes the synthetic click', () => {
  const { drawSurface, execute, pointerHandlers } = renderExternalDrawer();
  drawSurface.getBoundingClientRect = () => ({ left: 10, top: 20, width: 200, height: 200 });
  externalPointer(drawSurface, 'pointerdown', 50, 90);
  externalPointer(drawSurface, 'pointermove', 170, 150);
  expect(screen.getByTestId('external-selection-rectangle')).toHaveStyle({
    left: '40px', top: '70px', width: '120px', height: '60px',
  });
  externalPointer(drawSurface, 'pointerup', 170, 150);
  fireEvent.click(drawSurface, { clientX: 170, clientY: 150 });
  expect(execute).toHaveBeenCalledTimes(1);
  expect(execute).toHaveBeenCalledWith('select', { x: 0.5, y: 0.5, width: 0.6, height: 0.6 });
  expect(drawSurface.setPointerCapture).toHaveBeenCalledWith(7);
  expect(drawSurface.releasePointerCapture).toHaveBeenCalledWith(7);
  expect(screen.queryByTestId('external-selection-rectangle')).not.toBeInTheDocument();
  expect(pointerHandlers.handlePointerDown).not.toHaveBeenCalled();
  expect(apiFetchJson).not.toHaveBeenCalled();
});

test('external reversed touch drag normalizes the same rectangle', () => {
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 170, 100, { pointerType: 'touch' });
  externalPointer(drawSurface, 'pointermove', 50, 40, { pointerType: 'touch' });
  externalPointer(drawSurface, 'pointerup', 50, 40, { pointerType: 'touch' });
  expect(execute).toHaveBeenCalledWith('select', { x: 0.5, y: 0.5, width: 0.6, height: 0.6 });
});

test('external tap retains the fixed-size click selection and does not submit twice', () => {
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 109, 69);
  externalPointer(drawSurface, 'pointerup', 110, 70);
  fireEvent.click(drawSurface, { clientX: 110, clientY: 70 });
  expect(execute).toHaveBeenCalledTimes(1);
  expect(execute).toHaveBeenCalledWith('select', { x: 0.5, y: 0.5 });
});

test.each(['pointercancel', 'lostpointercapture'])('external %s discards the rectangle and its click', eventType => {
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 50, 40);
  externalPointer(drawSurface, 'pointermove', 170, 100);
  externalPointer(drawSurface, eventType, 170, 100);
  externalPointer(drawSurface, 'pointerup', 170, 100);
  fireEvent.click(drawSurface, { clientX: 170, clientY: 100 });
  expect(execute).not.toHaveBeenCalled();
  expect(screen.queryByTestId('external-selection-rectangle')).not.toBeInTheDocument();
});

test('external drag cannot begin in letterbox padding or become a one-dimensional box', () => {
  mockVideoMedia = { width: 100, height: 100, frameReady: true };
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 30, 70);
  externalPointer(drawSurface, 'pointerup', 100, 70);
  fireEvent.click(drawSurface, { clientX: 100, clientY: 70 });
  externalPointer(drawSurface, 'pointerdown', 70, 70);
  externalPointer(drawSurface, 'pointerup', 130, 72);
  fireEvent.click(drawSurface, { clientX: 130, clientY: 72 });
  expect(execute).not.toHaveBeenCalled();
});

test('external drag clips its release to video edges', () => {
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 110, 70);
  externalPointer(drawSurface, 'pointerup', 500, 500);
  expect(execute).toHaveBeenCalledWith('select', { x: 0.75, y: 0.75, width: 0.5, height: 0.5 });
});

test('external drag is rejected if availability or geometry changes before release', () => {
  let available = true;
  const { drawSurface, execute } = renderExternalDrawer({ canOperate: () => available });
  externalPointer(drawSurface, 'pointerdown', 50, 40);
  available = false;
  externalPointer(drawSurface, 'pointerup', 170, 100);
  available = true;
  externalPointer(drawSurface, 'pointerdown', 50, 40);
  drawSurface.getBoundingClientRect = () => ({ left: 10, top: 20, width: 400, height: 200 });
  externalPointer(drawSurface, 'pointerup', 170, 100);
  expect(execute).not.toHaveBeenCalled();
});

test('external Smart remains click-only and does not send rectangle dimensions', () => {
  const { drawSurface, execute } = renderExternalDrawer({ status: { selection_mode: 'smart' } });
  externalPointer(drawSurface, 'pointerdown', 50, 40);
  externalPointer(drawSurface, 'pointermove', 170, 100);
  externalPointer(drawSurface, 'pointerup', 170, 100);
  fireEvent.click(drawSurface, { clientX: 110, clientY: 70 });
  expect(execute).toHaveBeenCalledWith('select', { x: 0.5, y: 0.5 });
  expect(drawSurface.setPointerCapture).not.toHaveBeenCalled();
  expect(screen.queryByTestId('external-selection-rectangle')).not.toBeInTheDocument();
});

test('external selection ignores secondary pointers and fullscreen controls', () => {
  const { drawSurface, execute } = renderExternalDrawer();
  externalPointer(drawSurface, 'pointerdown', 50, 40, { isPrimary: false });
  externalPointer(drawSurface, 'pointerup', 170, 100, { pointerId: 8 });
  externalPointer(screen.getByRole('button', { name: 'Fullscreen video' }), 'pointerdown', 170, 100);
  externalPointer(drawSurface, 'pointerup', 170, 100);
  expect(execute).not.toHaveBeenCalled();
  expect(drawSurface.setPointerCapture).not.toHaveBeenCalled();
});
