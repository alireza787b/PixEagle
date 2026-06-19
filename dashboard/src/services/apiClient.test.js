import {
  DASHBOARD_AUTH_FAILURE_EVENT,
  apiFetch,
  apiFetchBlob,
  apiFetchJson,
  buildApiFetchOptions,
  clearDashboardAuthSession,
  createDashboardWebSocket,
  getMediaElementCrossOrigin,
  setDashboardAuthSession,
} from './apiClient';

describe('apiClient auth boundary', () => {
  const originalFetch = global.fetch;
  const originalWebSocket = global.WebSocket;

  afterEach(() => {
    clearDashboardAuthSession(null);
    jest.restoreAllMocks();
    global.fetch = originalFetch;
    global.WebSocket = originalWebSocket;
  });

  test('includes credentials and CSRF on unsafe requests only', () => {
    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
      csrf_header_name: 'X-Custom-CSRF',
      csrf_token: 'csrf-token',
    });

    const postOptions = buildApiFetchOptions({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(postOptions.credentials).toBe('include');
    expect(postOptions.headers.get('X-Custom-CSRF')).toBe('csrf-token');

    const getOptions = buildApiFetchOptions({ method: 'GET' });
    expect(getOptions.credentials).toBe('include');
    expect(getOptions.headers.get('X-Custom-CSRF')).toBeNull();
  });

  test('dispatches auth-failure event on rejected API response', async () => {
    const listener = jest.fn();
    window.addEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
    global.fetch = jest.fn(() => Promise.resolve({ status: 403, ok: false }));

    await apiFetch('/api/v1/runtime/status');

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      status: 403,
      url: '/api/v1/runtime/status',
    });
    window.removeEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
  });

  test('apiFetchJson dispatches auth failure and preserves structured error payload', async () => {
    const listener = jest.fn();
    window.addEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
    global.fetch = jest.fn(() => Promise.resolve({
      status: 401,
      ok: false,
      json: () => Promise.resolve({
        detail: {
          message: 'session expired',
          code: 'auth_required',
        },
      }),
    }));

    await expect(apiFetchJson('/api/v1/runtime/status')).rejects.toMatchObject({
      message: 'session expired',
      data: {
        detail: {
          message: 'session expired',
          code: 'auth_required',
        },
      },
    });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      status: 401,
      url: '/api/v1/runtime/status',
    });
    window.removeEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
  });

  test('apiFetchJson dispatches auth failure for non-JSON rejected responses', async () => {
    const listener = jest.fn();
    window.addEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
    global.fetch = jest.fn(() => Promise.resolve({
      status: 403,
      ok: false,
      json: () => Promise.reject(new SyntaxError('Unexpected token <')),
    }));

    await expect(apiFetchJson('/api/v1/runtime/status')).rejects.toMatchObject({
      message: 'HTTP 403',
      data: {},
    });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      status: 403,
      url: '/api/v1/runtime/status',
    });
    window.removeEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
  });

  test('apiFetchBlob dispatches auth failure for protected media downloads', async () => {
    const listener = jest.fn();
    window.addEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
    global.fetch = jest.fn(() => Promise.resolve({
      status: 403,
      ok: false,
      json: () => Promise.resolve({ detail: 'media scope required' }),
    }));

    await expect(apiFetchBlob('/api/v1/streams/media-health')).rejects.toMatchObject({
      message: 'media scope required',
    });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].detail).toEqual({
      status: 403,
      url: '/api/v1/streams/media-health',
    });
    window.removeEventListener(DASHBOARD_AUTH_FAILURE_EVENT, listener);
  });

  test('uses credentialed media props in browser-session mode', () => {
    clearDashboardAuthSession('local_compat');
    expect(getMediaElementCrossOrigin()).toBeUndefined();

    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
      csrf_header_name: 'X-PixEagle-CSRF',
      csrf_token: 'csrf-token',
    });
    expect(getMediaElementCrossOrigin()).toBe('use-credentials');
  });

  test('gates browser WebSocket media on authenticated media scope', () => {
    global.WebSocket = jest.fn(function MockWebSocket(url) {
      this.url = url;
    });

    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: false,
      principal: { scopes: [] },
    });
    expect(() => createDashboardWebSocket('ws://localhost/ws/video_feed')).toThrow(/media:read/);

    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['actions:execute'] },
    });
    expect(() => createDashboardWebSocket('ws://localhost/ws/video_feed')).toThrow(/media:read/);

    setDashboardAuthSession({
      auth_mode: 'browser_session',
      authenticated: true,
      principal: { scopes: ['media:read'] },
      csrf_header_name: 'X-PixEagle-CSRF',
      csrf_token: 'csrf-token',
    });
    const socket = createDashboardWebSocket('ws://localhost/ws/video_feed');
    expect(socket.url).toBe('ws://localhost/ws/video_feed');
    expect(global.WebSocket).toHaveBeenCalledTimes(1);
  });
});
