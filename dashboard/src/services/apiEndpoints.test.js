describe('reverse-proxy endpoint selection', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/');
    jest.resetModules();
  });

  test('uses the same-origin proxy for the /pixeagle dashboard', () => {
    window.history.replaceState({}, '', '/pixeagle/dashboard');
    jest.resetModules();

    const {
      endpoints,
      websocketVideoFeed,
      apiConfig,
    } = require('./apiEndpoints');

    expect(apiConfig.isBehindProxy).toBe(true);
    expect(endpoints.authSession).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/auth/session`
    );
    expect(endpoints.systemAbout).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/system/about`
    );
    expect(endpoints.followerSchema).toBe(
      `${window.location.origin}/pixeagle-api/api/follower/schema`
    );
    expect(endpoints.safetyConfig).toBe(
      `${window.location.origin}/pixeagle-api/api/safety/config`
    );
    expect(endpoints.trackerCatalog).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/tracking/catalog`
    );
    expect(endpoints.trackingTelemetry).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/tracking/telemetry`
    );
    expect(endpoints.trackerCurrentStatus).toBeUndefined();
    expect(endpoints.trackerOutput).toBeUndefined();
    expect(endpoints.trackerSchema).toBeUndefined();
    expect(endpoints.trackerCapabilities).toBeUndefined();
    expect(endpoints.trackerSwitchAction).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/actions/tracker-switch`
    );
    expect(endpoints.trackerRestartAction).toBe(
      `${window.location.origin}/pixeagle-api/api/v1/actions/tracker-restart`
    );
    expect(endpoints.safetyVehicleProfiles).toBeUndefined();
    expect(websocketVideoFeed).toBe(
      `ws://${window.location.host}/pixeagle-api/ws/video_feed`
    );
    expect(JSON.stringify(endpoints)).not.toContain(':5077');
  });

  test('keeps direct backend URLs for standalone dashboard mode', () => {
    window.history.replaceState({}, '', '/dashboard');
    jest.resetModules();

    const { endpoints, apiConfig } = require('./apiEndpoints');

    expect(apiConfig.isBehindProxy).toBe(false);
    expect(endpoints.authSession).toBe(
      'http://localhost:5077/api/v1/auth/session'
    );
    expect(endpoints.systemAbout).toBe(
      'http://localhost:5077/api/v1/system/about'
    );
    expect(endpoints.trackerCatalog).toBe(
      'http://localhost:5077/api/v1/tracking/catalog'
    );
    expect(endpoints.trackerSwitchAction).toBe(
      'http://localhost:5077/api/v1/actions/tracker-switch'
    );
    expect(endpoints.trackerRestartAction).toBe(
      'http://localhost:5077/api/v1/actions/tracker-restart'
    );
    expect(endpoints.trackerSchema).toBeUndefined();
    expect(endpoints.trackerCapabilities).toBeUndefined();
  });
});
