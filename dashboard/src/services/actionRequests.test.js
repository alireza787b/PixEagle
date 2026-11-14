import { buildActionRequest, followingStartFailureMessage } from './actionRequests';

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

test.each([
  { result: { legacy_result: { details: { precondition: { code: 'image_measurement_unavailable' } } } } },
  { result: { outcome: { precondition: { code: 'image_measurement_unavailable' } } } },
  { code: 'image_measurement_unavailable' },
])('formats typed startup refusal from supported action/HTTP envelopes', (data) => {
  expect(followingStartFailureMessage({ ...data, status: 'failure', error: 'Raw internal exception detail' }))
    .toBe('Target measurement is not current. Reacquire the target before starting.');
});

test.each([
  ['source_attitude_alignment_unavailable', 'Camera and aircraft timing are not aligned. Wait for current tracking before starting.'],
  ['target_not_tracking', 'Target is not being tracked. Select or reacquire a target before starting.'],
  ['following_input_context_changed', 'Target or camera changed. Reacquire the target before starting.'],
  ['guidance_image_geometry_changed', 'Camera geometry changed. Reacquire the target before starting.'],
  ['image_receipt_stale', 'Target measurement is not current. Reacquire the target before starting.'],
])('uses the vetted operator explanation for %s', (code, expected) => {
  expect(followingStartFailureMessage({ code })).toBe(expected);
});

test('prefers the precise startup outcome over an outer HTTP failure', () => {
  expect(followingStartFailureMessage({ code: 'unknown_failure', result: {
    outcome: { precondition: { code: 'target_not_tracking' } },
  } })).toBe('Target is not being tracked. Select or reacquire a target before starting.');
});

test.each([undefined, null, {}, { code: '__proto__' }, { code: 'unknown_native_failure' },
  { error: 'Failed to connect/start offboard mode: image_measurement_unavailable' },
  { detail: { message: 'source_attitude_alignment_unavailable' } },
  { result: { outcome: { precondition: { code: {} } } } },
])('unknown/untyped startup errors remain generic without parsing raw exceptions: %p', (data) => {
  expect(followingStartFailureMessage(data)).toBe('Following did not start. Check aircraft and tracking status.');
});
