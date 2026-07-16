import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

jest.mock('./VideoStream', () => function MockVideoStream() {
  return (
    <canvas
      data-testid="video-stream"
      data-video-media="true"
      data-frame-ready={mockVideoMedia.frameReady ? 'true' : 'false'}
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

const renderDrawer = ({ smartModeActive = true, selectionArmed } = {}) => {
  const imageRef = { current: null };
  const view = render(
    <BoundingBoxDrawer
      isTracking={false}
      selectionArmed={selectionArmed}
      imageRef={imageRef}
      startPos={null}
      currentPos={null}
      boundingBox={null}
      handlePointerDown={jest.fn()}
      handlePointerMove={jest.fn()}
      handlePointerUp={jest.fn()}
      videoSrc="/video_feed"
      protocol="mjpeg"
      smartModeActive={smartModeActive}
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
  return { ...view, drawSurface };
};

const renderSmartDrawer = () => renderDrawer({ smartModeActive: true });

test('explains how to arm classic target selection when the video is clicked', async () => {
  const { drawSurface } = renderDrawer({
    smartModeActive: false,
    selectionArmed: false,
  });

  fireEvent.click(drawSurface, { clientX: 60, clientY: 70 });

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Target selection is off. Use Select Target in Command.'
  );
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
