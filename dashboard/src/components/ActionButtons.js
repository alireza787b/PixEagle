import React from 'react';
import { Grid, Button, Typography, Tooltip } from '@mui/material';

const ActionButtons = ({ isTracking, handleTrackingToggle, handleButtonClick }) => {
  const apiHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
  const apiPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;
  const redetectEndpoint = `http://${apiHost}:${apiPort}/commands/redetect`;
  const cancelActivitiesEndpoint = `http://${apiHost}:${apiPort}/commands/cancel_activities`;
  const toggleSegmentationEndpoint = `http://${apiHost}:${apiPort}/commands/toggle_segmentation`;
  const startOffboardModeEndpoint = `http://${apiHost}:${apiPort}/commands/start_offboard_mode`;
  const stopOffboardModeEndpoint = `http://${apiHost}:${apiPort}/commands/stop_offboard_mode`;
  const quitEndpoint = `http://${apiHost}:${apiPort}/commands/quit`;

  return (
    <Grid container spacing={2} sx={{ mb: 2 }}>
      <Grid item xs={12}>
        <Typography variant="h6" gutterBottom>Tracking Controls</Typography>
        <Button
          variant="contained"
          color={isTracking ? "secondary" : "primary"}
          onClick={handleTrackingToggle}
          fullWidth
        >
          {isTracking ? "Stop Tracking" : "Start Tracking"}
        </Button>
        <Button 
          variant="contained" 
          color="primary" 
          onClick={() => handleButtonClick(redetectEndpoint)}
          fullWidth
          sx={{ mt: 1 }}
        >
          Re-Detect
        </Button>
        <Button 
          variant="contained" 
          color="primary" 
          onClick={() => handleButtonClick(cancelActivitiesEndpoint, true)}
          fullWidth
          sx={{ mt: 1 }}
        >
          Cancel Tracker
        </Button>
      </Grid>
      <Grid item xs={12}>
        <Typography variant="h6" gutterBottom>Segmentation Controls</Typography>
        <Button 
          variant="contained" 
          color="secondary" 
          onClick={() => handleButtonClick(toggleSegmentationEndpoint)}
          fullWidth
        >
          Toggle Segmentation
        </Button>
      </Grid>
      <Grid item xs={12}>
        <Typography variant="h6" gutterBottom>Offboard Controls</Typography>
        <Button 
          variant="contained" 
          color="success" 
          onClick={() => handleButtonClick(startOffboardModeEndpoint)}
          fullWidth
        >
          Start Following Offboard
        </Button>
        <Button 
          variant="contained" 
          color="success" 
          onClick={() => handleButtonClick(stopOffboardModeEndpoint)}
          fullWidth
          sx={{ mt: 1 }}
        >
          Stop Following Offboard
        </Button>
      </Grid>
      <Grid item xs={12}>
        <Button 
          variant="contained" 
          color="error" 
          onClick={() => handleButtonClick(quitEndpoint)}
          fullWidth
        >
          Quit
        </Button>
      </Grid>
    </Grid>
  );
};

export default ActionButtons;
