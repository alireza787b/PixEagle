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
  circuitBreakerStats: `http://${apiHost}:${apiPort}/api/circuit-breaker/statistics`,
};

export const videoFeed = `http://${apiHost}:${apiPort}/video_feed`;

// Existing WebSocket video feed endpoint
export const websocketVideoFeed = `ws://${apiHost}:${apiPort}/ws/video_feed`;

// **New WebRTC Signaling Endpoint**
export const webrtcSignalingEndpoint = `ws://${apiHost}:${apiPort}/ws/webrtc_signaling`;
