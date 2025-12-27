// dashboard/src/components/ActionButtons.js
import React, { useState } from 'react';
import {
  Grid,
  Button,
  Typography,
  Tooltip,
  Container,
  FormControlLabel,
  Switch,
  Box,
} from '@mui/material';
import { endpoints } from '../services/apiEndpoints';
import QuitButton from './QuitButton';

const ActionButtons = ({
  isTracking,
  smartModeActive,
  handleTrackingToggle,
  handleButtonClick,
  handleToggleSmartMode,
}) => {
  const [switchLoading, setSwitchLoading] = useState(false);

  const handleSmartModeSwitch = async () => {
    setSwitchLoading(true);
    await handleToggleSmartMode();
    setSwitchLoading(false);
  };

  return (
    <Container>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {/* Smart Tracker Toggle */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>🎯 Tracker Mode</Typography>
          <Box display="flex" justifyContent="center" alignItems="center">
            <Tooltip title={smartModeActive ? "AI-powered YOLO detection - Click video to track" : "Classic tracker - Draw bounding box to track"}>
              <FormControlLabel
                control={
                  <Switch
                    checked={smartModeActive}
                    onChange={handleSmartModeSwitch}
                    disabled={switchLoading}
                    color="success"
                  />
                }
                label={smartModeActive ? '🧠 Smart Tracker (AI)' : '🎯 Classic Tracker'}
              />
            </Tooltip>
          </Box>
        </Grid>

        {/* Tracking Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>📹 Tracking Controls</Typography>
          <Tooltip title={smartModeActive ? "Tracking is automatic in Smart Mode - just click on the video" : "Start or stop classic tracking"}>
            <span>
              <Button
                variant="contained"
                color={isTracking ? "secondary" : "primary"}
                onClick={handleTrackingToggle}
                fullWidth
                disabled={smartModeActive}
              >
                {isTracking ? "⏹️ Stop Tracking" : "▶️ Start Tracking"}
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="Re-detect object (Classic tracker only)">
            <span>
              <Button
                variant="contained"
                color="primary"
                onClick={() => handleButtonClick(endpoints.redetect)}
                fullWidth
                sx={{ mt: 1 }}
                disabled={smartModeActive}
              >
                🔍 Re-Detect
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="Cancel all tracking activities and reset">
            <Button
              variant="contained"
              color="warning"
              onClick={() => handleButtonClick(endpoints.cancelActivities, true)}
              fullWidth
              sx={{ mt: 1 }}
            >
              ❌ Cancel Tracker
            </Button>
          </Tooltip>
        </Grid>

        {/* Segmentation Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>🎨 Segmentation Controls</Typography>
          <Tooltip title="Toggle YOLO segmentation overlay for object detection visualization">
            <Button
              variant="contained"
              color="secondary"
              onClick={() => handleButtonClick(endpoints.toggleSegmentation)}
              fullWidth
            >
              🎭 Toggle Segmentation
            </Button>
          </Tooltip>
        </Grid>

        {/* PX4 Offboard Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>🚁 Drone Control</Typography>
          <Tooltip title="Engage offboard mode and start autonomous following">
            <Button
              variant="contained"
              color="success"
              onClick={() => handleButtonClick(endpoints.startOffboardMode)}
              fullWidth
            >
              🚀 Start Following
            </Button>
          </Tooltip>
          <Tooltip title="Disengage offboard mode and stop following">
            <Button
              variant="contained"
              color="error"
              onClick={() => handleButtonClick(endpoints.stopOffboardMode)}
              fullWidth
              sx={{ mt: 1 }}
            >
              🛑 Stop Following
            </Button>
          </Tooltip>
        </Grid>

        {/* Quit App */}
        <Grid item xs={12}>
          <QuitButton fullWidth />
        </Grid>
      </Grid>
    </Container>
  );
};

export default ActionButtons;
