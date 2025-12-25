// dashboard/src/services/apiEndpoints.js

const apiHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
const apiPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;

// Existing HTTP and WebSocket endpoints
export const endpoints = {
  startTracking: `http://${apiHost}:${apiPort}/commands/start_tracking`,
  stopTracking: `http://${apiHost}:${apiPort}/commands/stop_tracking`,
  redetect: `http://${apiHost}:${apiPort}/commands/redetect`,
  cancelActivities: `http://${apiHost}:${apiPort}/commands/cancel_activities`,
  toggleSegmentation: `http://${apiHost}:${apiPort}/commands/toggle_segmentation`,
  startOffboardMode: `http://${apiHost}:${apiPort}/commands/start_offboard_mode`,
  stopOffboardMode: `http://${apiHost}:${apiPort}/commands/stop_offboard_mode`,
  quit: `http://${apiHost}:${apiPort}/commands/quit`,
  status: `http://${apiHost}:${apiPort}/status`,
  toggleSmartMode: `http://${apiHost}:${apiPort}/commands/toggle_smart_mode`,
  smartClick: `http://${apiHost}:${apiPort}/commands/smart_click`,

  // Circuit breaker endpoints
  circuitBreakerStatus: `http://${apiHost}:${apiPort}/api/circuit-breaker/status`,
  toggleCircuitBreaker: `http://${apiHost}:${apiPort}/api/circuit-breaker/toggle`,
  toggleCircuitBreakerSafety: `http://${apiHost}:${apiPort}/api/circuit-breaker/toggle-safety`,
  circuitBreakerStats: `http://${apiHost}:${apiPort}/api/circuit-breaker/statistics`,

  // OSD endpoints
  osdStatus: `http://${apiHost}:${apiPort}/api/osd/status`,
  toggleOsd: `http://${apiHost}:${apiPort}/api/osd/toggle`,
  osdPresets: `http://${apiHost}:${apiPort}/api/osd/presets`,
  loadOsdPreset: (presetName) => `http://${apiHost}:${apiPort}/api/osd/preset/${presetName}`,

  // YOLO Model Management endpoints
  yoloModels: `http://${apiHost}:${apiPort}/api/yolo/models`,
  yoloSwitchModel: `http://${apiHost}:${apiPort}/api/yolo/switch-model`,
  yoloUpload: `http://${apiHost}:${apiPort}/api/yolo/upload`,
  yoloDelete: (modelId) => `http://${apiHost}:${apiPort}/api/yolo/delete/${modelId}`,

  // Safety configuration endpoints (v3.5.0+)
  safetyConfig: `http://${apiHost}:${apiPort}/api/safety/config`,
  safetyLimits: (followerName) => `http://${apiHost}:${apiPort}/api/safety/limits/${followerName}`,
  safetyVehicleProfiles: `http://${apiHost}:${apiPort}/api/safety/vehicle-profiles`,

  // Configuration management endpoints (v4.0.0+)
  configSchema: `http://${apiHost}:${apiPort}/api/config/schema`,
  configSectionSchema: (section) => `http://${apiHost}:${apiPort}/api/config/schema/${section}`,
  configSections: `http://${apiHost}:${apiPort}/api/config/sections`,
  configCategories: `http://${apiHost}:${apiPort}/api/config/categories`,
  configCurrent: `http://${apiHost}:${apiPort}/api/config/current`,
  configCurrentSection: (section) => `http://${apiHost}:${apiPort}/api/config/current/${section}`,
  configDefault: `http://${apiHost}:${apiPort}/api/config/default`,
  configDefaultSection: (section) => `http://${apiHost}:${apiPort}/api/config/default/${section}`,
  configUpdateParameter: (section, param) => `http://${apiHost}:${apiPort}/api/config/${section}/${param}`,
  configUpdateSection: (section) => `http://${apiHost}:${apiPort}/api/config/${section}`,
  configValidate: `http://${apiHost}:${apiPort}/api/config/validate`,
  configDiff: `http://${apiHost}:${apiPort}/api/config/diff`,
  configRevert: `http://${apiHost}:${apiPort}/api/config/revert`,
  configRevertSection: (section) => `http://${apiHost}:${apiPort}/api/config/revert/${section}`,
  configRevertParameter: (section, param) => `http://${apiHost}:${apiPort}/api/config/revert/${section}/${param}`,
  configHistory: `http://${apiHost}:${apiPort}/api/config/history`,
  configRestore: (backupId) => `http://${apiHost}:${apiPort}/api/config/restore/${backupId}`,
  configExport: `http://${apiHost}:${apiPort}/api/config/export`,
  configImport: `http://${apiHost}:${apiPort}/api/config/import`,
  configSearch: `http://${apiHost}:${apiPort}/api/config/search`,
  configAudit: `http://${apiHost}:${apiPort}/api/config/audit`,

  // System management endpoints (v4.0.0+)
  systemStatus: `http://${apiHost}:${apiPort}/api/system/status`,
  systemRestart: `http://${apiHost}:${apiPort}/api/system/restart`,
};

export const videoFeed = `http://${apiHost}:${apiPort}/video_feed`;

// Existing WebSocket video feed endpoint
export const websocketVideoFeed = `ws://${apiHost}:${apiPort}/ws/video_feed`;

// **New WebRTC Signaling Endpoint**
export const webrtcSignalingEndpoint = `ws://${apiHost}:${apiPort}/ws/webrtc_signaling`;
