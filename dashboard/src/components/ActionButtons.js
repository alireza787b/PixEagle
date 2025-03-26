// dashboard/src/components/ActionButtons.js
import React from 'react';
import { Grid, Button, Typography, Tooltip, Container } from '@mui/material';
import { endpoints } from '../services/apiEndpoints';
import QuitButton from './QuitButton';

const ActionButtons = ({
  isTracking,
  smartModeActive,
  handleTrackingToggle,
  handleButtonClick,
  handleToggleSmartMode, // ✅ new
}) => {
  return (
    <Container>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {/* Tracker Mode Toggle */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Tracker Mode</Typography>
          <Tooltip title="Switch between Smart Tracker (YOLO) and Classic Tracker (CSRT)">
            <Button
              variant="contained"
              color={smartModeActive ? "success" : "primary"}
              onClick={handleToggleSmartMode}
              fullWidth
            >
              {smartModeActive ? "Smart Mode (YOLO)" : "Classic Mode (CSRT)"}
            </Button>
          </Tooltip>
        </Grid>

        {/* Tracking Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Tracking Controls</Typography>
          <Tooltip title="Start or stop classic tracking">
            <Button
              variant="contained"
              color={isTracking ? "secondary" : "primary"}
              onClick={handleTrackingToggle}
              fullWidth
              disabled={smartModeActive} // ✅ Disable in smart mode
            >
              {isTracking ? "Stop Tracking" : "Start Tracking"}
            </Button>
          </Tooltip>

          <Tooltip title="Re-detect object (Classic only)">
            <Button
              variant="contained"
              color="primary"
              onClick={() => handleButtonClick(endpoints.redetect)}
              fullWidth
              sx={{ mt: 1 }}
              disabled={smartModeActive} // ✅ Disable in smart mode
            >
              Re-Detect
            </Button>
          </Tooltip>

          <Tooltip title="Cancel all tracking activities">
            <Button
              variant="contained"
              color="primary"
              onClick={() => handleButtonClick(endpoints.cancelActivities, true)}
              fullWidth
              sx={{ mt: 1 }}
            >
              Cancel Tracker
            </Button>
          </Tooltip>
        </Grid>

        {/* Segmentation Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Segmentation Controls</Typography>
          <Tooltip title="Toggle YOLO segmentation overlay">
            <Button
              variant="contained"
              color="secondary"
              onClick={() => handleButtonClick(endpoints.toggleSegmentation)}
              fullWidth
            >
              Toggle Segmentation
            </Button>
          </Tooltip>
        </Grid>

        {/* Offboard / PX4 Controls */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Offboard Controls</Typography>
          <Tooltip title="Start following in offboard mode">
            <Button
              variant="contained"
              color="success"
              onClick={() => handleButtonClick(endpoints.startOffboardMode)}
              fullWidth
            >
              Start Following
            </Button>
          </Tooltip>
          <Tooltip title="Stop following in offboard mode">
            <Button
              variant="contained"
              color="success"
              onClick={() => handleButtonClick(endpoints.stopOffboardMode)}
              fullWidth
              sx={{ mt: 1 }}
            >
              Stop Following
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
