// dashboard/src/services/apiEndpoints.js
// Dynamic host detection with optional override for reverse proxy/special deployments

/**
 * Get API configuration with smart defaults
 * - Auto-detects host from browser URL (works for localhost, LAN, remote)
 * - Supports explicit override via REACT_APP_API_HOST_OVERRIDE
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

  return { apiHost, apiPort, protocol, wsProtocol };
};

const { apiHost, apiPort, protocol, wsProtocol } = getApiConfig();

// HTTP endpoints (using dynamic protocol for HTTPS support)
export const endpoints = {
  startTracking: `${protocol}://${apiHost}:${apiPort}/commands/start_tracking`,
  stopTracking: `${protocol}://${apiHost}:${apiPort}/commands/stop_tracking`,
  redetect: `${protocol}://${apiHost}:${apiPort}/commands/redetect`,
  cancelActivities: `${protocol}://${apiHost}:${apiPort}/commands/cancel_activities`,
  toggleSegmentation: `${protocol}://${apiHost}:${apiPort}/commands/toggle_segmentation`,
  startOffboardMode: `${protocol}://${apiHost}:${apiPort}/commands/start_offboard_mode`,
  stopOffboardMode: `${protocol}://${apiHost}:${apiPort}/commands/stop_offboard_mode`,
  quit: `${protocol}://${apiHost}:${apiPort}/commands/quit`,
  status: `${protocol}://${apiHost}:${apiPort}/status`,
  toggleSmartMode: `${protocol}://${apiHost}:${apiPort}/commands/toggle_smart_mode`,
  smartClick: `${protocol}://${apiHost}:${apiPort}/commands/smart_click`,

  // Circuit breaker endpoints
  circuitBreakerStatus: `${protocol}://${apiHost}:${apiPort}/api/circuit-breaker/status`,
  toggleCircuitBreaker: `${protocol}://${apiHost}:${apiPort}/api/circuit-breaker/toggle`,
  toggleCircuitBreakerSafety: `${protocol}://${apiHost}:${apiPort}/api/circuit-breaker/toggle-safety`,
  circuitBreakerStats: `${protocol}://${apiHost}:${apiPort}/api/circuit-breaker/statistics`,

  // OSD endpoints
  osdStatus: `${protocol}://${apiHost}:${apiPort}/api/osd/status`,
  toggleOsd: `${protocol}://${apiHost}:${apiPort}/api/osd/toggle`,
  osdPresets: `${protocol}://${apiHost}:${apiPort}/api/osd/presets`,
  loadOsdPreset: (presetName) => `${protocol}://${apiHost}:${apiPort}/api/osd/preset/${presetName}`,

  // GStreamer QGC Output endpoints
  gstreamerStatus: `${protocol}://${apiHost}:${apiPort}/api/gstreamer/status`,
  toggleGstreamer: `${protocol}://${apiHost}:${apiPort}/api/gstreamer/toggle`,

  // YOLO Model Management endpoints
  yoloModels: `${protocol}://${apiHost}:${apiPort}/api/yolo/models`,
  yoloActiveModel: `${protocol}://${apiHost}:${apiPort}/api/yolo/active-model`,
  yoloModelLabels: (modelId) => `${protocol}://${apiHost}:${apiPort}/api/yolo/models/${encodeURIComponent(modelId)}/labels`,
  yoloSwitchModel: `${protocol}://${apiHost}:${apiPort}/api/yolo/switch-model`,
  yoloUpload: `${protocol}://${apiHost}:${apiPort}/api/yolo/upload`,
  yoloDownload: `${protocol}://${apiHost}:${apiPort}/api/yolo/download`,
  yoloDelete: (modelId) => `${protocol}://${apiHost}:${apiPort}/api/yolo/delete/${modelId}`,

  // Safety configuration endpoints (v3.5.0+)
  safetyConfig: `${protocol}://${apiHost}:${apiPort}/api/safety/config`,
  safetyLimits: (followerName) => `${protocol}://${apiHost}:${apiPort}/api/safety/limits/${followerName}`,

  // Enhanced safety/config endpoints (v5.0.0+)
  effectiveLimits: (followerName) => `${protocol}://${apiHost}:${apiPort}/api/config/effective-limits${followerName ? `?follower_name=${followerName}` : ''}`,
  relevantSections: (followerMode) => `${protocol}://${apiHost}:${apiPort}/api/config/sections/relevant${followerMode ? `?follower_mode=${followerMode}` : ''}`,
  currentFollowerMode: `${protocol}://${apiHost}:${apiPort}/api/follower/current-mode`,

  // Configuration management endpoints (v4.0.0+)
  configSchema: `${protocol}://${apiHost}:${apiPort}/api/config/schema`,
  configSectionSchema: (section) => `${protocol}://${apiHost}:${apiPort}/api/config/schema/${section}`,
  configSections: `${protocol}://${apiHost}:${apiPort}/api/config/sections`,
  configCategories: `${protocol}://${apiHost}:${apiPort}/api/config/categories`,
  configCurrent: `${protocol}://${apiHost}:${apiPort}/api/config/current`,
  configCurrentSection: (section) => `${protocol}://${apiHost}:${apiPort}/api/config/current/${section}`,
  configDefault: `${protocol}://${apiHost}:${apiPort}/api/config/default`,
  configDefaultSection: (section) => `${protocol}://${apiHost}:${apiPort}/api/config/default/${section}`,
  configUpdateParameter: (section, param) => `${protocol}://${apiHost}:${apiPort}/api/config/${section}/${param}`,
  configUpdateSection: (section) => `${protocol}://${apiHost}:${apiPort}/api/config/${section}`,
  configValidate: `${protocol}://${apiHost}:${apiPort}/api/config/validate`,
  configDiff: `${protocol}://${apiHost}:${apiPort}/api/config/diff`,
  configDefaultsSync: `${protocol}://${apiHost}:${apiPort}/api/config/defaults-sync`,
  configDefaultsSyncPlan: `${protocol}://${apiHost}:${apiPort}/api/config/defaults-sync/plan`,
  configDefaultsSyncApply: `${protocol}://${apiHost}:${apiPort}/api/config/defaults-sync/apply`,
  configRevert: `${protocol}://${apiHost}:${apiPort}/api/config/revert`,
  configRevertSection: (section) => `${protocol}://${apiHost}:${apiPort}/api/config/revert/${section}`,
  configRevertParameter: (section, param) => `${protocol}://${apiHost}:${apiPort}/api/config/revert/${section}/${param}`,
  configHistory: `${protocol}://${apiHost}:${apiPort}/api/config/history`,
  configRestore: (backupId) => `${protocol}://${apiHost}:${apiPort}/api/config/restore/${backupId}`,
  configExport: `${protocol}://${apiHost}:${apiPort}/api/config/export`,
  configImport: `${protocol}://${apiHost}:${apiPort}/api/config/import`,
  configSearch: `${protocol}://${apiHost}:${apiPort}/api/config/search`,
  configAudit: `${protocol}://${apiHost}:${apiPort}/api/config/audit`,

  // System management endpoints (v4.0.0+)
  systemStatus: `${protocol}://${apiHost}:${apiPort}/api/system/status`,
  systemRestart: `${protocol}://${apiHost}:${apiPort}/api/system/restart`,
  systemConfig: `${protocol}://${apiHost}:${apiPort}/api/system/config`,
  videoHealth: `${protocol}://${apiHost}:${apiPort}/api/video/health`,
  videoReconnect: `${protocol}://${apiHost}:${apiPort}/api/video/reconnect`,
};

// Video feed endpoint
export const videoFeed = `${protocol}://${apiHost}:${apiPort}/video_feed`;

// WebSocket endpoints (using dynamic wsProtocol for WSS support)
export const websocketVideoFeed = `${wsProtocol}://${apiHost}:${apiPort}/ws/video_feed`;

// WebRTC Signaling Endpoint
export const webrtcSignalingEndpoint = `${wsProtocol}://${apiHost}:${apiPort}/ws/webrtc_signaling`;

// Streaming status endpoint
export const streamingStatus = `${protocol}://${apiHost}:${apiPort}/api/streaming/status`;

// Export config for debugging/logging
export const apiConfig = { apiHost, apiPort, protocol, wsProtocol };
