//dashboard/src/components/ActionButtons.js
import React from 'react';
import { Grid, Button, Typography, Tooltip, Container } from '@mui/material';
import { endpoints } from '../services/apiEndpoints';
import QuitButton from './QuitButton';

const ActionButtons = ({ isTracking, handleTrackingToggle, handleButtonClick }) => {
  return (
    <Container>
      <Typography variant="h5" gutterBottom>Controls</Typography>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Tracking Controls</Typography>
          <Tooltip title="Start or stop tracking">
            <Button
              variant="contained"
              color={isTracking ? "secondary" : "primary"}
              onClick={handleTrackingToggle}
              fullWidth
            >
              {isTracking ? "Stop Tracking" : "Start Tracking"}
            </Button>
          </Tooltip>
          <Tooltip title="Redetect object">
            <Button 
              variant="contained" 
              color="primary" 
              onClick={() => handleButtonClick(endpoints.redetect)}
              fullWidth
              sx={{ mt: 1 }}
            >
              Re-Detect
            </Button>
          </Tooltip>
          <Tooltip title="Cancel current tracker">
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
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Segmentation Controls</Typography>
          <Tooltip title="Toggle segmentation">
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
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>Offboard Controls</Typography>
          <Tooltip title="Start following in offboard mode">
            <Button 
              variant="contained" 
              color="success" 
              onClick={() => handleButtonClick(endpoints.startOffboardMode)}
              fullWidth
            >
              Start Following Offboard
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
              Stop Following Offboard
            </Button>
          </Tooltip>
        </Grid>
        <Grid item xs={12}>
          <QuitButton fullWidth />
        </Grid>
      </Grid>
    </Container>
  );
};

export default ActionButtons;
