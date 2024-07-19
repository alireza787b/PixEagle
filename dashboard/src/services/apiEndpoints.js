const apiHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
const apiPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;

export const endpoints = {
  startTracking: `http://${apiHost}:${apiPort}/commands/start_tracking`,
  stopTracking: `http://${apiHost}:${apiPort}/commands/stop_tracking`,
  redetect: `http://${apiHost}:${apiPort}/commands/redetect`,
  cancelActivities: `http://${apiHost}:${apiPort}/commands/cancel_activities`,
  toggleSegmentation: `http://${apiHost}:${apiPort}/commands/toggle_segmentation`,
  startOffboardMode: `http://${apiHost}:${apiPort}/commands/start_offboard_mode`,
  stopOffboardMode: `http://${apiHost}:${apiPort}/commands/stop_offboard_mode`,
  quit: `http://${apiHost}:${apiPort}/commands/quit`,
};

export const videoFeed = `http://${apiHost}:${apiPort}/video_feed`;