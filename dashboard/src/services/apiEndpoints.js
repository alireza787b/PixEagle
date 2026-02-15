// dashboard/src/services/apiEndpoints.js
// Dynamic host detection with reverse proxy support (e.g., ARK-OS at /pixeagle/)

/**
 * Get API configuration with smart defaults
 * - Auto-detects host from browser URL (works for localhost, LAN, remote)
 * - Supports explicit override via REACT_APP_API_HOST_OVERRIDE
 * - Detects reverse proxy mode when served behind /pixeagle/ subpath
 * - Detects protocol (http/https) from current page
 */
const getApiConfig = () => {
  // Check for explicit override (useful for reverse proxy, Docker, special deployments)
  const hostOverride = process.env.REACT_APP_API_HOST_OVERRIDE;

  // Auto-detect from browser URL (works for LAN, remote, localhost)
  const detectedHost = typeof window !== 'undefined'
    ? window.location.hostname
    : 'localhost';

  // Port configuration (can be overridden via env)
  const apiPort = process.env.REACT_APP_API_PORT || '5077';

  // Use override if set and non-empty, otherwise auto-detect
  const apiHost = (hostOverride && hostOverride.trim()) || detectedHost;

  // Protocol detection (match current page for CORS compatibility)
  const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
  const protocol = isHttps ? 'https' : 'http';
  const wsProtocol = isHttps ? 'wss' : 'ws';

  // Detect reverse proxy mode (e.g., ARK-OS serves dashboard at /pixeagle/)
  // When behind proxy, route API calls through /pixeagle-api/ instead of direct port
  const isBehindProxy = typeof window !== 'undefined'
    && window.location.pathname.startsWith('/pixeagle');

  let apiBaseUrl, wsBaseUrl;

  if (isBehindProxy) {
    // Behind reverse proxy: use nginx proxy path (no direct port access needed)
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    apiBaseUrl = `${origin}/pixeagle-api`;
    wsBaseUrl = `${wsProtocol}://${typeof window !== 'undefined' ? window.location.host : 'localhost'}/pixeagle-api`;
  } else {
    // Standalone mode: direct connection to API port
    apiBaseUrl = `${protocol}://${apiHost}:${apiPort}`;
    wsBaseUrl = `${wsProtocol}://${apiHost}:${apiPort}`;
  }

  return { apiBaseUrl, wsBaseUrl, apiHost, apiPort, protocol, wsProtocol, isBehindProxy };
};

const { apiBaseUrl, wsBaseUrl, apiHost, apiPort, protocol, wsProtocol, isBehindProxy } = getApiConfig();

// HTTP endpoints (using dynamic protocol for HTTPS support)
export const endpoints = {
  startTracking: `${apiBaseUrl}/commands/start_tracking`,
  stopTracking: `${apiBaseUrl}/commands/stop_tracking`,
  redetect: `${apiBaseUrl}/commands/redetect`,
  cancelActivities: `${apiBaseUrl}/commands/cancel_activities`,
  toggleSegmentation: `${apiBaseUrl}/commands/toggle_segmentation`,
  startOffboardMode: `${apiBaseUrl}/commands/start_offboard_mode`,
  stopOffboardMode: `${apiBaseUrl}/commands/stop_offboard_mode`,
  quit: `${apiBaseUrl}/commands/quit`,
  status: `${apiBaseUrl}/status`,
  toggleSmartMode: `${apiBaseUrl}/commands/toggle_smart_mode`,
  smartClick: `${apiBaseUrl}/commands/smart_click`,

  // Circuit breaker endpoints
  circuitBreakerStatus: `${apiBaseUrl}/api/circuit-breaker/status`,
  toggleCircuitBreaker: `${apiBaseUrl}/api/circuit-breaker/toggle`,
  toggleCircuitBreakerSafety: `${apiBaseUrl}/api/circuit-breaker/toggle-safety`,
  circuitBreakerStats: `${apiBaseUrl}/api/circuit-breaker/statistics`,

  // OSD endpoints
  osdStatus: `${apiBaseUrl}/api/osd/status`,
  toggleOsd: `${apiBaseUrl}/api/osd/toggle`,
  osdPresets: `${apiBaseUrl}/api/osd/presets`,
  loadOsdPreset: (presetName) => `${apiBaseUrl}/api/osd/preset/${presetName}`,
  osdColorModes: `${apiBaseUrl}/api/osd/color-modes`,
  setOsdColorMode: (mode) => `${apiBaseUrl}/api/osd/color-mode/${mode}`,
  osdModes: `${apiBaseUrl}/api/osd/modes`,

  // GStreamer QGC Output endpoints
  gstreamerStatus: `${apiBaseUrl}/api/gstreamer/status`,
  toggleGstreamer: `${apiBaseUrl}/api/gstreamer/toggle`,

  // Recording endpoints
  recordingStart: `${apiBaseUrl}/api/recording/start`,
  recordingPause: `${apiBaseUrl}/api/recording/pause`,
  recordingResume: `${apiBaseUrl}/api/recording/resume`,
  recordingStop: `${apiBaseUrl}/api/recording/stop`,
  recordingStatus: `${apiBaseUrl}/api/recording/status`,
  recordingToggle: `${apiBaseUrl}/api/recording/toggle`,
  recordingsList: `${apiBaseUrl}/api/recordings`,
  recordingDownload: (filename) => `${apiBaseUrl}/api/recordings/${encodeURIComponent(filename)}`,
  recordingDelete: (filename) => `${apiBaseUrl}/api/recordings/${encodeURIComponent(filename)}`,
  storageStatus: `${apiBaseUrl}/api/storage/status`,
  recordingIncludeOsd: (enabled) => `${apiBaseUrl}/api/recording/include-osd/${enabled}`,

  // Detection Model Management endpoints
  models: `${apiBaseUrl}/api/models`,
  activeModel: `${apiBaseUrl}/api/models/active`,
  modelLabels: (modelId) => `${apiBaseUrl}/api/models/${encodeURIComponent(modelId)}/labels`,
  switchModel: `${apiBaseUrl}/api/models/switch`,
  modelUpload: `${apiBaseUrl}/api/models/upload`,
  modelDownload: `${apiBaseUrl}/api/models/download`,
  modelDelete: (modelId) => `${apiBaseUrl}/api/models/${modelId}`,

  // Safety configuration endpoints (v3.5.0+)
  safetyConfig: `${apiBaseUrl}/api/safety/config`,
  safetyLimits: (followerName) => `${apiBaseUrl}/api/safety/limits/${followerName}`,

  // Enhanced safety/config endpoints (v5.0.0+)
  effectiveLimits: (followerName) => `${apiBaseUrl}/api/config/effective-limits${followerName ? `?follower_name=${followerName}` : ''}`,
  relevantSections: (followerMode) => `${apiBaseUrl}/api/config/sections/relevant${followerMode ? `?follower_mode=${followerMode}` : ''}`,
  currentFollowerMode: `${apiBaseUrl}/api/follower/current-mode`,

  // Configuration management endpoints (v4.0.0+)
  configSchema: `${apiBaseUrl}/api/config/schema`,
  configSectionSchema: (section) => `${apiBaseUrl}/api/config/schema/${section}`,
  configSections: `${apiBaseUrl}/api/config/sections`,
  configCategories: `${apiBaseUrl}/api/config/categories`,
  configCurrent: `${apiBaseUrl}/api/config/current`,
  configCurrentSection: (section) => `${apiBaseUrl}/api/config/current/${section}`,
  configDefault: `${apiBaseUrl}/api/config/default`,
  configDefaultSection: (section) => `${apiBaseUrl}/api/config/default/${section}`,
  configUpdateParameter: (section, param) => `${apiBaseUrl}/api/config/${section}/${param}`,
  configUpdateSection: (section) => `${apiBaseUrl}/api/config/${section}`,
  configValidate: `${apiBaseUrl}/api/config/validate`,
  configDiff: `${apiBaseUrl}/api/config/diff`,
  configDefaultsSync: `${apiBaseUrl}/api/config/defaults-sync`,
  configDefaultsSyncPlan: `${apiBaseUrl}/api/config/defaults-sync/plan`,
  configDefaultsSyncApply: `${apiBaseUrl}/api/config/defaults-sync/apply`,
  configRevert: `${apiBaseUrl}/api/config/revert`,
  configRevertSection: (section) => `${apiBaseUrl}/api/config/revert/${section}`,
  configRevertParameter: (section, param) => `${apiBaseUrl}/api/config/revert/${section}/${param}`,
  configHistory: `${apiBaseUrl}/api/config/history`,
  configRestore: (backupId) => `${apiBaseUrl}/api/config/restore/${backupId}`,
  configExport: `${apiBaseUrl}/api/config/export`,
  configImport: `${apiBaseUrl}/api/config/import`,
  configSearch: `${apiBaseUrl}/api/config/search`,
  configAudit: `${apiBaseUrl}/api/config/audit`,

  // System management endpoints (v4.0.0+)
  systemStatus: `${apiBaseUrl}/api/system/status`,
  systemRestart: `${apiBaseUrl}/api/system/restart`,
  systemConfig: `${apiBaseUrl}/api/system/config`,
  videoHealth: `${apiBaseUrl}/api/video/health`,
  videoReconnect: `${apiBaseUrl}/api/video/reconnect`,
};

// Video feed endpoint
export const videoFeed = `${apiBaseUrl}/video_feed`;

// WebSocket endpoints (using dynamic wsProtocol for WSS support)
export const websocketVideoFeed = `${wsBaseUrl}/ws/video_feed`;

// WebRTC Signaling Endpoint
export const webrtcSignalingEndpoint = `${wsBaseUrl}/ws/webrtc_signaling`;

// Streaming status endpoint
export const streamingStatus = `${apiBaseUrl}/api/streaming/status`;

// Export config for debugging/logging
export const apiConfig = { apiHost, apiPort, protocol, wsProtocol, isBehindProxy };
