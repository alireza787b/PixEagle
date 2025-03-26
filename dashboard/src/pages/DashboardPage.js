// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect } from 'react';
import {
  Container, Typography, CircularProgress, Box, Grid, Snackbar, Alert,
  FormControl, InputLabel, Select, MenuItem, Divider
} from '@mui/material';

import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';
import StatusIndicator from '../components/StatusIndicator';

import { videoFeed, endpoints } from '../services/apiEndpoints';
import {
  useTrackerStatus,
  useFollowerStatus,
  useSmartModeStatus
} from '../hooks/useStatuses';
import useBoundingBoxHandlers from '../hooks/useBoundingBoxHandlers';

const DashboardPage = () => {
  const [isTracking, setIsTracking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('websocket');
  const [smartModeActive, setSmartModeActive] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  const checkInterval = 2000;

  const isFollowing = useFollowerStatus(checkInterval);
  const trackerStatus = useTrackerStatus(checkInterval);
  const smartModeStatus = useSmartModeStatus(checkInterval);

  useEffect(() => {
    setSmartModeActive(smartModeStatus);
  }, [smartModeStatus]);

  const {
    imageRef,
    startPos,
    currentPos,
    boundingBox,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  } = useBoundingBoxHandlers(isTracking, setIsTracking, smartModeActive);

  const handleTrackingToggle = async () => {
    if (isTracking) {
      try {
        await fetch(endpoints.stopTracking, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        console.log('Tracking stopped');
      } catch (error) {
        console.error('Error:', error);
      }
    }
    setIsTracking(!isTracking);
  };

  const handleButtonClick = async (endpoint, updateTrackingState = false) => {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await response.json();
      console.log(`Response from ${endpoint}:`, data);

      if (endpoint === endpoints.quit) {
        window.location.reload();
      }

      if (updateTrackingState) {
        setIsTracking(false);
      }
    } catch (error) {
      console.error(`Error from ${endpoint}:`, error);
      alert(`Operation failed for endpoint ${endpoint}. Check console for details.`);
    }
  };

  const handleToggleSmartMode = async () => {
    try {
      await fetch(endpoints.toggleSmartMode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      setSmartModeActive((prev) => !prev);
      setSnackbarOpen(true);
    } catch (err) {
      console.error('Failed to toggle smart mode:', err);
    }
  };

  const handleSnackbarClose = () => setSnackbarOpen(false);

  useEffect(() => {
    const checkStream = setInterval(() => {
      const img = new Image();
      img.src = videoFeed;
      img.onload = () => {
        setLoading(false);
        clearInterval(checkStream);
      };
      img.onerror = () => console.error('Error loading video feed');
    }, checkInterval);

    return () => clearInterval(checkStream);
  }, []);

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" gutterBottom align="center">
        Dashboard
      </Typography>

      {loading ? (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {/* Sidebar */}
          <Grid item xs={12} sm={3} md={2}>
            <Grid container direction="column" spacing={2}>
              {/* Mode Toggle Button */}
              <Grid item>
                <Typography variant="h6">Tracker Mode</Typography>
                <Box mt={1}>
                  <ActionButtons
                    isTracking={isTracking}
                    smartModeActive={smartModeActive}
                    handleTrackingToggle={handleTrackingToggle}
                    handleButtonClick={handleButtonClick}
                    handleToggleSmartMode={handleToggleSmartMode}
                  />
                </Box>
              </Grid>

              <Divider sx={{ my: 2 }} />

              {/* Streaming protocol dropdown */}
              <Grid item>
                <FormControl variant="outlined" fullWidth>
                  <InputLabel id="streaming-protocol-label">Streaming Protocol</InputLabel>
                  <Select
                    labelId="streaming-protocol-label"
                    value={streamingProtocol}
                    onChange={(e) => setStreamingProtocol(e.target.value)}
                    label="Streaming Protocol"
                  >
                    <MenuItem value="websocket">WebSocket</MenuItem>
                    <MenuItem value="http">HTTP</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Grid>

          {/* Main Video + Bounding */}
          <Grid item xs={12} sm={9} md={10}>
            <BoundingBoxDrawer
              isTracking={isTracking}
              imageRef={imageRef}
              startPos={startPos}
              currentPos={currentPos}
              boundingBox={boundingBox}
              handleMouseDown={handleMouseDown}
              handleMouseMove={handleMouseMove}
              handleMouseUp={handleMouseUp}
              handleTouchStart={handleTouchStart}
              handleTouchMove={handleTouchMove}
              handleTouchEnd={handleTouchEnd}
              videoSrc={videoFeed}
              protocol={streamingProtocol}
              smartModeActive={smartModeActive}
            />
          </Grid>

          {/* Status Indicators */}
          <Grid item xs={12}>
            <Grid container justifyContent="center" spacing={2}>
              <Grid item>
                <StatusIndicator label="Tracking Status" status={trackerStatus} />
              </Grid>
              <Grid item>
                <StatusIndicator label="Follower Status" status={isFollowing} />
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      )}

      {/* Snackbar confirmation for mode toggle */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000}
        onClose={handleSnackbarClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleSnackbarClose} severity="info" sx={{ width: '100%' }}>
          Switched to {smartModeActive ? 'Smart Tracker (YOLO)' : 'Classic Tracker (CSRT)'}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default DashboardPage;
