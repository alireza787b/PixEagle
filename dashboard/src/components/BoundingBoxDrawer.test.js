import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import BoundingBoxDrawer from './BoundingBoxDrawer';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';

let mockHasScope = () => true;

jest.mock('../services/apiClient', () => ({
  apiFetchJson: jest.fn(),
}));

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({
    hasScope: mockHasScope,
  }),
}));

jest.mock('./VideoStream', () => function MockVideoStream() {
  return <div data-testid="video-stream" />;
});

beforeEach(() => {
  apiFetchJson.mockResolvedValue({ status: 'success' });
});

afterEach(() => {
  mockHasScope = () => true;
  jest.clearAllMocks();
});

const renderSmartDrawer = () => {
  const imageRef = { current: null };
  const rendered = render(
    <BoundingBoxDrawer
      isTracking={false}
      imageRef={imageRef}
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
  const drawSurface = rendered.container.firstChild;
  drawSurface.getBoundingClientRect = jest.fn(() => ({
    left: 10,
    top: 20,
    width: 200,
    height: 100,
    right: 210,
    bottom: 120,
  }));
  return { ...rendered, drawSurface };
};

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
    click: { x: 0.25, y: 0.5 },
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
