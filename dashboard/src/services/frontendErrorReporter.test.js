import {
  reportFrontendError,
  resetFrontendErrorReporterForTests,
} from './frontendErrorReporter';
import {
  clearDashboardAuthSession,
  setDashboardAuthSession,
} from './apiClient';
import { endpoints } from './apiEndpoints';

const okResponse = () => ({
  ok: true,
  status: 202,
  json: async () => ({ accepted: true }),
});

beforeEach(() => {
  resetFrontendErrorReporterForTests();
  clearDashboardAuthSession(null);
  global.fetch = jest.fn().mockResolvedValue(okResponse());
  window.history.pushState({}, '', '/dashboard?token=abc123456');
});

afterEach(() => {
  resetFrontendErrorReporterForTests();
  clearDashboardAuthSession(null);
  jest.restoreAllMocks();
});

test('reports frontend errors with browser-session CSRF and redacted payload text', async () => {
  setDashboardAuthSession({
    auth_mode: 'browser_session',
    authenticated: true,
    principal: {
      scopes: ['runtime:report'],
    },
    csrf_required: true,
    csrf_header_name: 'X-PixEagle-CSRF',
    csrf_token: 'csrf-token',
  });

  await reportFrontendError(
    new Error('render failed password=swordfish'),
    {
      kind: 'unit_test',
      stack: 'Authorization: Basic dXNlcjpwYXNz',
    }
  );

  expect(global.fetch).toHaveBeenCalledTimes(1);
  const [url, options] = global.fetch.mock.calls[0];
  const payload = JSON.parse(options.body);

  expect(url).toBe(endpoints.frontendErrorReport);
  expect(options.method).toBe('POST');
  expect(options.credentials).toBe('include');
  expect(options.headers.get('X-PixEagle-CSRF')).toBe('csrf-token');
  expect(payload.message).toContain('[REDACTED]');
  expect(payload.message).not.toContain('swordfish');
  expect(payload.stack).not.toContain('dXNlcjpwYXNz');
  expect(payload.route).not.toContain('abc123456');
});

test('skips browser-session reports without runtime report scope', async () => {
  setDashboardAuthSession({
    auth_mode: 'browser_session',
    authenticated: true,
    principal: {
      scopes: ['media:read'],
    },
  });

  const result = await reportFrontendError(new Error('hidden'));

  expect(result).toEqual({ skipped: true });
  expect(global.fetch).not.toHaveBeenCalled();
});

test('waits for discovered auth mode before reporting startup errors', async () => {
  const result = await reportFrontendError(new Error('startup race'));

  expect(result).toEqual({ skipped: true });
  expect(global.fetch).not.toHaveBeenCalled();
});

test('client-side rate limit bounds frontend report volume', async () => {
  setDashboardAuthSession({
    auth_mode: 'browser_session',
    authenticated: true,
    principal: {
      scopes: ['runtime:report'],
    },
    csrf_required: true,
    csrf_header_name: 'X-PixEagle-CSRF',
    csrf_token: 'csrf-token',
  });

  for (let index = 0; index < 21; index += 1) {
    await reportFrontendError(new Error(`render failed ${index}`));
  }

  expect(global.fetch).toHaveBeenCalledTimes(20);
});
