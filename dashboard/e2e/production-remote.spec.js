const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const baseURL = process.env.PIXEAGLE_E2E_BASE_URL;
const username = process.env.PIXEAGLE_E2E_USERNAME;
const password = process.env.PIXEAGLE_E2E_PASSWORD;
const evidenceDir = process.env.PIXEAGLE_E2E_EVIDENCE_DIR;
const secretHandoffFile = process.env.PIXEAGLE_E2E_SECRET_HANDOFF_FILE;

const requiredEnvironment = {
  PIXEAGLE_E2E_BASE_URL: baseURL,
  PIXEAGLE_E2E_USERNAME: username,
  PIXEAGLE_E2E_PASSWORD: password,
  PIXEAGLE_E2E_EVIDENCE_DIR: evidenceDir,
  PIXEAGLE_E2E_SECRET_HANDOFF_FILE: secretHandoffFile,
};

for (const [name, value] of Object.entries(requiredEnvironment)) {
  if (!value) {
    throw new Error(`${name} is required`);
  }
}

const resultPath = path.join(evidenceDir, 'browser-results.json');
const requestLedgerPath = path.join(evidenceDir, 'request-ledger.json');
const websocketLedgerPath = path.join(evidenceDir, 'websocket-ledger.json');
const responseLedgerPath = path.join(evidenceDir, 'response-ledger.json');
const requestFailuresPath = path.join(evidenceDir, 'request-failures.json');
const expectedAuthority = new URL(baseURL);
const expectedPort = expectedAuthority.port
  || (expectedAuthority.protocol === 'https:' ? '443' : '80');
const approvedDashboardRoutes = new Set([
  '/pixeagle',
  '/pixeagle/',
  '/pixeagle/dashboard',
  '/pixeagle/tracker',
  '/pixeagle/follower',
  '/pixeagle/live-feed',
  '/pixeagle/recordings',
  '/pixeagle/models',
  '/pixeagle/settings',
]);
const approvedApiPaths = new Set([
  '/pixeagle-api/status',
  '/pixeagle-api/telemetry/follower_data',
  '/pixeagle-api/video_feed',
  '/pixeagle-api/api/circuit-breaker/status',
  '/pixeagle-api/api/config/categories',
  '/pixeagle-api/api/config/defaults-sync',
  '/pixeagle-api/api/config/diff',
  '/pixeagle-api/api/config/history',
  '/pixeagle-api/api/config/schema',
  '/pixeagle-api/api/config/sections',
  '/pixeagle-api/api/config/sections/relevant',
  '/pixeagle-api/api/follower/current-mode',
  '/pixeagle-api/api/follower/current-profile',
  '/pixeagle-api/api/follower/profiles',
  '/pixeagle-api/api/follower/schema',
  '/pixeagle-api/api/gstreamer/status',
  '/pixeagle-api/api/models',
  '/pixeagle-api/api/models/active',
  '/pixeagle-api/api/osd/presets',
  '/pixeagle-api/api/osd/color-modes',
  '/pixeagle-api/api/osd/status',
  '/pixeagle-api/api/recording/status',
  '/pixeagle-api/api/recordings',
  '/pixeagle-api/api/system/config',
  '/pixeagle-api/api/system/status',
  '/pixeagle-api/api/v1/actions/tracker-restart',
  '/pixeagle-api/api/v1/actions/tracker-switch',
  '/pixeagle-api/api/v1/actions/tracking-stop',
  '/pixeagle-api/api/v1/auth/login',
  '/pixeagle-api/api/v1/auth/logout',
  '/pixeagle-api/api/v1/auth/session',
  '/pixeagle-api/api/v1/config/runtime-status',
  '/pixeagle-api/api/v1/following/status',
  '/pixeagle-api/api/v1/following/telemetry',
  '/pixeagle-api/api/v1/runtime/status',
  '/pixeagle-api/api/v1/streams/media-health',
  '/pixeagle-api/api/v1/system/about',
  '/pixeagle-api/api/v1/telemetry/health',
  '/pixeagle-api/api/v1/tracking/catalog',
  '/pixeagle-api/api/v1/tracking/runtime-status',
  '/pixeagle-api/api/v1/tracking/telemetry',
  '/pixeagle-api/api/video/health',
]);
const approvedWebSocketPaths = new Set([
  '/pixeagle-api/ws/video_feed',
  '/pixeagle-api/ws/webrtc_signaling',
]);
const approvedApiQueryKeys = new Map([
  ['/pixeagle-api/api/circuit-breaker/status', new Set(['_t'])],
  ['/pixeagle-api/api/config/sections/relevant', new Set(['follower_mode'])],
  ['/pixeagle-api/api/models', new Set(['_t', 'force_rescan'])],
  ['/pixeagle-api/api/models/active', new Set(['_t'])],
  ['/pixeagle-api/api/v1/following/status', new Set(['_t'])],
  ['/pixeagle-api/api/v1/following/telemetry', new Set(['_t'])],
  ['/pixeagle-api/api/v1/runtime/status', new Set(['_t'])],
  ['/pixeagle-api/api/v1/streams/media-health', new Set(['_t'])],
  ['/pixeagle-api/api/v1/telemetry/health', new Set(['_t'])],
  ['/pixeagle-api/api/v1/tracking/runtime-status', new Set(['_t'])],
  ['/pixeagle-api/api/v1/tracking/telemetry', new Set(['_t'])],
]);

const sanitizedUrl = (rawUrl) => {
  const url = new URL(rawUrl);
  return {
    scheme: url.protocol.replace(':', ''),
    host: url.hostname,
    port: url.port || (url.protocol === 'https:' ? '443' : '80'),
    path: url.pathname,
    has_query: Boolean(url.search),
    query_keys: [...url.searchParams.keys()].sort(),
  };
};

const sanitizedRequest = (request) => {
  return {
    method: request.method(),
    ...sanitizedUrl(request.url()),
    resource_type: request.resourceType(),
  };
};

const isApprovedHttpPath = (request) => (
  approvedDashboardRoutes.has(request.path)
  || approvedApiPaths.has(request.path)
  || /^\/pixeagle\/static\/(?:css|js)\/[A-Za-z0-9._-]+$/.test(request.path)
  || /^\/pixeagle\/(?:asset-manifest\.json|favicon\.ico|logo\d+\.png|manifest\.json)$/.test(request.path)
);

const hasApprovedQueryKeys = (request) => {
  if (request.query_keys.length === 0) {
    return true;
  }
  if (new Set(request.query_keys).size !== request.query_keys.length) {
    return false;
  }
  if (
    request.path === '/pixeagle-api/ws/video_feed'
    && request.query_keys.length === 1
    && request.query_keys[0] === 'token'
  ) {
    return true;
  }
  if (!approvedApiPaths.has(request.path)) {
    return false;
  }
  const allowed = approvedApiQueryKeys.get(request.path);
  if (!allowed) {
    return false;
  }
  return request.query_keys.every((key) => allowed.has(key));
};

const isApprovedLocalBlob = (request) => (
  request.scheme === 'blob'
  && request.host === ''
  && request.resource_type === 'image'
  && request.has_query === false
  && request.path.startsWith(`${expectedAuthority.origin}/`)
);

test('production remote browser session stays behind the HTTPS proxy', async ({ page, context }) => {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const requests = [];
  const responses = [];
  const requestFailures = [];
  const websockets = [];
  const pageErrors = [];
  let applicationTransition = null;
  const result = {
    passed: false,
    claim_boundary: (
      'Local self-signed HTTPS reverse-proxy and browser-policy evidence only; '
      + 'not certificate-trust, firewall, target deployment, PX4/SITL/HIL, field, '
      + 'or real-aircraft evidence.'
    ),
    checks: {},
  };

  page.on('request', (request) => requests.push(sanitizedRequest(request)));
  page.on('response', (response) => {
    responses.push({
      ...sanitizedUrl(response.url()),
      status: response.status(),
      method: response.request().method(),
    });
  });
  page.on('requestfailed', (request) => {
    requestFailures.push({
      ...sanitizedRequest(request),
      error: request.failure()?.errorText || 'unknown',
      transition: applicationTransition,
    });
  });
  page.on('websocket', (websocket) => {
    const entry = {
      ...sanitizedUrl(websocket.url()),
      closed: false,
    };
    websockets.push(entry);
    websocket.on('close', () => {
      entry.closed = true;
    });
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  try {
    await page.goto('/pixeagle', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/pixeagle\/$/);
    await expect(page.getByText('Operator sign in')).toBeVisible();
    await page.screenshot({
      path: path.join(evidenceDir, 'login-gate.png'),
      fullPage: true,
    });

    const anonymousMediaStatus = await page.evaluate(async () => {
      const response = await fetch(
        '/pixeagle-api/api/v1/streams/media-health',
        { credentials: 'include' }
      );
      return response.status;
    });
    expect(anonymousMediaStatus).toBe(401);
    result.checks.unauthenticated_media_denied = true;

    const anonymousSocket = await page.evaluate(() => (
      new Promise((resolve) => {
        let opened = false;
        const socket = new WebSocket(
          `${window.location.origin.replace('https:', 'wss:')}`
          + '/pixeagle-api/ws/video_feed'
        );
        const timeout = setTimeout(() => {
          socket.close();
          resolve({ opened, timedOut: true });
        }, 5000);
        socket.addEventListener('open', () => {
          opened = true;
        });
        socket.addEventListener('close', (event) => {
          clearTimeout(timeout);
          resolve({ opened, timedOut: false, code: event.code });
        });
        socket.addEventListener('error', () => {});
      })
    ));
    expect(anonymousSocket.opened).toBe(false);
    expect(anonymousSocket.timedOut).toBe(false);
    result.checks.unauthenticated_websocket_denied = true;

    await page.getByLabel('Username').fill(username);
    await page.getByLabel('Password').fill(`${password}-wrong`);
    await page.getByRole('button', { name: 'Sign In' }).click();
    await expect(page.getByText('Username or password is invalid.')).toBeVisible();
    expect(await context.cookies(baseURL)).toHaveLength(0);
    result.checks.invalid_login_denied = true;

    await page.getByLabel('Password').fill(password);
    applicationTransition = 'session_enter';
    try {
      await page.getByRole('button', { name: 'Sign In' }).click();
      await expect(page.getByRole('button', { name: 'sign out' })).toBeVisible();
      await page.waitForTimeout(50);
    } finally {
      applicationTransition = null;
    }

    const cookies = await context.cookies(baseURL);
    const sessionCookie = cookies.find((cookie) => cookie.name === 'pixeagle_session');
    expect(sessionCookie).toBeTruthy();
    expect(sessionCookie.secure).toBe(true);
    expect(sessionCookie.httpOnly).toBe(true);
    expect(sessionCookie.sameSite).toBe('Lax');
    expect(await page.evaluate(() => document.cookie)).not.toContain('pixeagle_session');
    result.checks.secure_http_only_session_cookie = true;

    const session = await page.evaluate(async () => {
      const response = await fetch('/pixeagle-api/api/v1/auth/session', {
        credentials: 'include',
      });
      return response.json();
    });
    expect(session.authenticated).toBe(true);
    expect(session.principal.scopes).toContain('media:read');
    expect(session.principal.scopes).toContain('actions:execute');
    fs.writeFileSync(
      secretHandoffFile,
      JSON.stringify({
        session_cookie: sessionCookie.value,
        csrf_token: session.csrf_token,
      }),
      { encoding: 'utf8', mode: 0o600 }
    );

    const csrfStatuses = await page.evaluate(async ({ csrfHeaderName, csrfToken }) => {
      const endpoint = '/pixeagle-api/api/v1/actions/tracking-stop';
      const body = JSON.stringify({
        source: 'browser_e2e',
        reason: 'csrf_contract',
        dry_run: true,
        confirm: false,
        metadata: {},
      });
      const request = async (headers) => {
        const response = await fetch(endpoint, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...headers,
          },
          body,
        });
        return response.status;
      };
      return {
        missing: await request({}),
        wrong: await request({ [csrfHeaderName]: `${csrfToken}-wrong` }),
        correct: await request({ [csrfHeaderName]: csrfToken }),
      };
    }, {
      csrfHeaderName: session.csrf_header_name,
      csrfToken: session.csrf_token,
    });
    expect(csrfStatuses).toEqual({
      missing: 403,
      wrong: 403,
      correct: 202,
    });
    result.checks.session_bound_csrf = true;

    const mediaHealth = await page.evaluate(async () => {
      const response = await fetch('/pixeagle-api/api/v1/streams/media-health', {
        credentials: 'include',
      });
      return {
        status: response.status,
        payload: await response.json(),
      };
    });
    expect(mediaHealth.status).toBe(200);
    expect(mediaHealth.payload.security.required_scope).toBe('media:read');

    const deepLinks = {
      dashboard: 'Command',
      tracker: 'Tracker',
      follower: 'Follower',
      'live-feed': 'Live Video Feed',
      recordings: 'Recordings',
      models: 'Detection Models',
      settings: 'Configuration Manager',
    };
    for (const [route, heading] of Object.entries(deepLinks)) {
      applicationTransition = 'route_navigation';
      try {
        await page.goto(`/pixeagle/${route}`, { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('button', { name: 'sign out' })).toBeVisible();
        await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible();
        await page.waitForTimeout(50);
      } finally {
        applicationTransition = null;
      }
    }
    result.checks.dashboard_deep_links = true;

    await page.getByRole('button', { name: 'Sync Defaults' }).click();
    await expect(page.getByText('Config Sync', { exact: true })).toBeVisible();
    await expect(page.getByText('No config migration is required')).toBeVisible();
    await expect(page.getByText('Config migration status unavailable')).toHaveCount(0);
    await page.getByRole('button', { name: 'Close' }).click();
    result.checks.config_sync_v2_ready = true;

    const queryTokenSocket = await page.evaluate(() => (
      new Promise((resolve) => {
        let opened = false;
        const socket = new WebSocket(
          `${window.location.origin.replace('https:', 'wss:')}`
          + '/pixeagle-api/ws/video_feed?token=not-real'
        );
        const timeout = setTimeout(() => {
          socket.close();
          resolve({ opened, timedOut: true });
        }, 5000);
        socket.addEventListener('open', () => {
          opened = true;
        });
        socket.addEventListener('close', (event) => {
          clearTimeout(timeout);
          resolve({ opened, timedOut: false, code: event.code });
        });
        socket.addEventListener('error', () => {});
      })
    ));
    expect(queryTokenSocket.opened).toBe(false);
    expect(queryTokenSocket.timedOut).toBe(false);
    result.checks.authenticated_query_token_websocket_denied = true;

    await page.evaluate(() => {
      window.__pixeagleMediaSocketResult = new Promise((resolve, reject) => {
        const timeout = setTimeout(
          () => reject(new Error('Timed out waiting for media WebSocket')),
          10_000
        );
        const socket = new WebSocket(
          `${window.location.origin.replace('https:', 'wss:')}`
          + '/pixeagle-api/ws/video_feed'
        );
        socket.binaryType = 'arraybuffer';
        window.__pixeagleMediaSocket = socket;
        socket.addEventListener('open', () => {
          socket.send(JSON.stringify({
            type: 'ping',
            client_timestamp: Date.now(),
          }));
        });
        socket.addEventListener('message', (event) => {
          if (typeof event.data !== 'string') {
            return;
          }
          const payload = JSON.parse(event.data);
          if (payload.type === 'pong') {
            clearTimeout(timeout);
            resolve({ opened: true, pong: true });
          }
        });
        socket.addEventListener('error', () => {
          clearTimeout(timeout);
          reject(new Error('Authenticated media WebSocket failed'));
        });
      });
    });
    expect(await page.evaluate(() => window.__pixeagleMediaSocketResult)).toEqual({
      opened: true,
      pong: true,
    });
    result.checks.authenticated_websocket_media = true;

    const mjpeg = await page.evaluate(async () => {
      const response = await fetch('/pixeagle-api/video_feed', {
        credentials: 'include',
      });
      const reader = response.body.getReader();
      const first = await reader.read();
      window.__pixeagleMjpegClosed = (async () => {
        try {
          while (true) {
            const next = await reader.read();
            if (next.done) {
              return { done: true };
            }
          }
        } catch (error) {
          return { done: false, error: error.name };
        }
      })();
      return {
        status: response.status,
        contentType: response.headers.get('content-type'),
        firstDone: first.done,
        firstLength: first.value?.byteLength || 0,
      };
    });
    expect(mjpeg.status).toBe(200);
    expect(mjpeg.contentType).toContain('multipart/x-mixed-replace');
    expect(mjpeg.firstDone).toBe(false);
    expect(mjpeg.firstLength).toBeGreaterThan(0);
    result.checks.authenticated_production_mjpeg = true;

    await page.screenshot({
      path: path.join(evidenceDir, 'authenticated-dashboard.png'),
      fullPage: true,
    });

    await page.evaluate(() => {
      window.__pixeagleMediaSocketClosed = new Promise((resolve) => {
        const socket = window.__pixeagleMediaSocket;
        socket.addEventListener('close', (event) => {
          resolve({ code: event.code, reason: event.reason });
        }, { once: true });
      });
    });
    applicationTransition = 'session_exit';
    try {
      await page.getByRole('button', { name: 'sign out' }).click();
      await expect(page.getByText('Operator sign in')).toBeVisible();
      await page.waitForTimeout(50);
    } finally {
      applicationTransition = null;
    }
    const closeEvent = await page.evaluate(() => window.__pixeagleMediaSocketClosed);
    expect(closeEvent.code).toBe(1008);
    expect(closeEvent.reason).toContain('expired or revoked');
    result.checks.logout_closes_existing_websocket = true;
    expect(await page.evaluate(() => window.__pixeagleMjpegClosed)).toEqual({
      done: true,
    });
    result.checks.logout_closes_existing_mjpeg = true;

    const postLogoutMediaStatus = await page.evaluate(async () => {
      const response = await fetch(
        '/pixeagle-api/api/v1/streams/media-health',
        { credentials: 'include' }
      );
      return response.status;
    });
    expect(postLogoutMediaStatus).toBe(401);
    result.checks.logout_denies_new_media = true;

    const networkRequests = requests.filter((request) => request.scheme !== 'blob');
    const unexpectedBlobRequests = requests.filter(
      (request) => request.scheme === 'blob' && !isApprovedLocalBlob(request)
    );
    const unexpectedAuthorityRequests = networkRequests.filter(
      (request) => (
        request.host !== expectedAuthority.hostname
        || request.port !== expectedPort
      )
    );
    const unexpectedPathRequests = networkRequests.filter(
      (request) => !isApprovedHttpPath(request)
    );
    const unexpectedHttpQueries = networkRequests.filter(
      (request) => !hasApprovedQueryKeys(request)
    );
    const unexpectedWebsockets = websockets.filter(
      (websocket) => (
        websocket.scheme !== 'wss'
        || websocket.host !== expectedAuthority.hostname
        || websocket.port !== expectedPort
        || !approvedWebSocketPaths.has(websocket.path)
        || !hasApprovedQueryKeys(websocket)
      )
    );
    const unexpectedRequestFailures = requestFailures.filter(
      (failure) => !(
        failure.error === 'net::ERR_ABORTED'
        && ['session_enter', 'route_navigation', 'session_exit'].includes(
          failure.transition
        )
        && ['fetch', 'xhr'].includes(failure.resource_type)
        && approvedApiPaths.has(failure.path)
      )
    );
    const unexpectedErrorResponses = responses.filter(
      (response) => (
        response.status >= 400
        && !(
          response.status === 401
          && response.method === 'POST'
          && response.path === '/pixeagle-api/api/v1/auth/login'
        )
        && !(
          response.status === 401
          && response.method === 'GET'
          && response.path === '/pixeagle-api/api/v1/streams/media-health'
        )
        && !(
          response.status === 403
          && response.method === 'POST'
          && response.path === '/pixeagle-api/api/v1/actions/tracking-stop'
        )
      )
    );
    expect(unexpectedBlobRequests).toEqual([]);
    expect(unexpectedAuthorityRequests).toEqual([]);
    expect(unexpectedPathRequests).toEqual([]);
    expect(unexpectedHttpQueries).toEqual([]);
    expect(unexpectedWebsockets).toEqual([]);
    expect(networkRequests.every((request) => request.scheme === 'https')).toBe(true);
    expect(unexpectedErrorResponses).toEqual([]);
    expect(unexpectedRequestFailures).toEqual([]);
    result.checks.exact_https_proxy_boundary = true;
    result.checks.no_unexpected_request_failures = true;

    expect(pageErrors).toEqual([]);
    result.checks.no_page_errors = true;
    result.passed = true;
  } catch (error) {
    result.error = {
      name: error.name,
      message: error.message,
    };
    throw error;
  } finally {
    result.page_error_count = pageErrors.length;
    result.request_count = requests.length;
    result.response_count = responses.length;
    result.websocket_count = websockets.length;
    result.request_failure_count = requestFailures.length;
    fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`);
    fs.writeFileSync(requestLedgerPath, `${JSON.stringify(requests, null, 2)}\n`);
    fs.writeFileSync(websocketLedgerPath, `${JSON.stringify(websockets, null, 2)}\n`);
    fs.writeFileSync(responseLedgerPath, `${JSON.stringify(responses, null, 2)}\n`);
    fs.writeFileSync(requestFailuresPath, `${JSON.stringify(requestFailures, null, 2)}\n`);
  }
});
