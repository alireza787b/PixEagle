import { buildActionRequest } from './actionRequests';

afterEach(() => {
  jest.restoreAllMocks();
});

test('builds confirmed idempotent dashboard action requests', () => {
  jest.spyOn(Date, 'now').mockReturnValue(1770000000000);
  jest.spyOn(Math, 'random').mockReturnValue(0.5);

  const request = buildActionRequest('start_tracking_roi', {
    ui: 'dashboard_video_canvas',
  });

  expect(request).toEqual({
    source: 'dashboard',
    reason: 'start_tracking_roi',
    confirm: true,
    idempotency_key: expect.stringMatching(
      /^dashboard-start-tracking-roi-1770000000000-[a-z0-9]+$/
    ),
    metadata: {
      ui: 'dashboard_video_canvas',
    },
  });
});
