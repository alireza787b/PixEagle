// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect } from 'react';
import {
  Container, Typography, CircularProgress, Box, Grid, Snackbar, Alert,
  FormControl, InputLabel, Select, MenuItem, Card, CardContent,
  IconButton, Tooltip,
} from '@mui/material';
import { TrackChanges, Settings as SettingsIcon } from '@mui/icons-material';

import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';
import FollowerStatusCard from '../components/FollowerStatusCard';
import TrackerStatusCard from '../components/TrackerStatusCard';
import TrackerSelector from '../components/TrackerSelector';
import YOLOModelSelector from '../components/YOLOModelSelector';
import FollowerQuickControl from '../components/FollowerQuickControl';
import StreamingStats from '../components/StreamingStats';
import CircuitBreakerStatusCard from '../components/CircuitBreakerStatusCard';
import OSDToggle from '../components/OSDToggle';
import SafetyConfigCard from '../components/SafetyConfigCard';
import StreamingStatusIndicator from '../components/StreamingStatusIndicator';
import OperationalStatusBar from '../components/OperationalStatusBar';
import QuickConfigDrawer from '../components/QuickConfigDrawer';
import RecordingQuickControl from '../components/RecordingQuickControl';
import RecordingIndicator from '../components/RecordingIndicator';

import { videoFeed, endpoints } from '../services/apiEndpoints';
import {
  useTrackerStatus,
  useFollowerStatus,
  useSmartModeStatus
} from '../hooks/useStatuses';
import { useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import useBoundingBoxHandlers from '../hooks/useBoundingBoxHandlers';
import axios from 'axios';
import { apiConfig } from '../services/apiEndpoints';

const API_URL = `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`;

const DashboardPage = () => {
  const [isTracking, setIsTracking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('auto');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState('info');
  const [followerData, setFollowerData] = useState({});
  const [circuitBreakerActive, setCircuitBreakerActive] = useState(undefined);
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);

  const checkInterval = 2000;

  const isFollowing = useFollowerStatus(checkInterval);
  const trackerStatus = useTrackerStatus(checkInterval);
  const {
    smartModeActive,
    refresh: refreshSmartModeStatus,
  } = useSmartModeStatus(checkInterval);
  const { currentProfile } = useCurrentFollowerProfile();

  // Unified data fetching for better performance
  useEffect(() => {
    const fetchAllData = async () => {
      try {
        const [followerResponse, circuitBreakerResponse] = await Promise.all([
          axios.get(`${API_URL}/telemetry/follower_data`).catch(() => ({ data: {} })),
          axios.get(endpoints.circuitBreakerStatus).catch(() => ({ data: { available: false } }))
        ]);

        setFollowerData(followerResponse.data);
        setCircuitBreakerActive(
          circuitBreakerResponse.data.available
            ? circuitBreakerResponse.data.active
            : undefined
        );
      } catch (error) {
        console.error('Error in unified data fetch:', error);
      }
    };

    fetchAllData();
    const interval = setInterval(fetchAllData, 2000);
    return () => clearInterval(interval);
  }, []);

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

      if (endpoint === endpoints.startOffboardMode && data.details?.auto_stopped) {
        setSnackbarMessage('Follower was active - automatically restarted');
        setSnackbarSeverity('info');
        setSnackbarOpen(true);
      }

      if (endpoint === endpoints.startOffboardMode && data.status === 'success') {
        if (!data.details?.auto_stopped) {
          setSnackbarMessage('Follower started successfully');
          setSnackbarSeverity('success');
          setSnackbarOpen(true);
        }
      } else if (endpoint === endpoints.stopOffboardMode && data.status === 'success') {
        setSnackbarMessage('Follower stopped successfully');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      }

      if (data.status === 'failure') {
        setSnackbarMessage(`Operation failed: ${data.error || 'Unknown error'}`);
        setSnackbarSeverity('error');
        setSnackbarOpen(true);
      }

      if (endpoint === endpoints.quit) {
        window.location.reload();
      }

      if (updateTrackingState) {
        setIsTracking(false);
      }
    } catch (error) {
      console.error(`Error from ${endpoint}:`, error);
      setSnackbarMessage('Operation failed. Check console for details.');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleToggleSmartMode = async () => {
    try {
      const response = await fetch(endpoints.toggleSmartMode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!response.ok) {
        throw new Error(`Failed to toggle smart mode (HTTP ${response.status})`);
      }

      const syncedMode = await refreshSmartModeStatus({ suppressErrors: true });
      const activeMode = typeof syncedMode === 'boolean' ? syncedMode : smartModeActive;

      setSnackbarMessage(`Switched to ${activeMode ? 'Smart Tracker (YOLO)' : 'Classic Tracker'}`);
      setSnackbarSeverity('info');
      setSnackbarOpen(true);
    } catch (err) {
      console.error('Failed to toggle smart mode:', err);
      setSnackbarMessage('Failed to toggle smart mode');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    }
  };

  const handleSnackbarClose = () => setSnackbarOpen(false);

  useEffect(() => {
    if (streamingProtocol === 'websocket' || streamingProtocol === 'webrtc' || streamingProtocol === 'auto') {
      setLoading(false);
      return;
    }

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
  }, [streamingProtocol]);

  return (
    <Container maxWidth="xl" sx={{ mt: 2, mb: 4 }}>
      {loading ? (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {/* PRIMARY: Main Video and Controls Section */}
          <Grid item xs={12}>
            <Card elevation={2}>
              <CardContent sx={{ p: 2 }}>
                <Grid container spacing={2}>
                  {/* Control Panel - Sidebar */}
                  <Grid item xs={12} lg={3}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, height: '100%' }}>
                      {/* Primary Controls */}
                      <Card variant="outlined">
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                            <TrackChanges color="primary" fontSize="small" />
                            <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1 }}>Control Panel</Typography>
                            <Tooltip title="Quick Settings">
                              <IconButton size="small" onClick={() => setConfigDrawerOpen(true)}>
                                <SettingsIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          </Box>
                          <ActionButtons
                            isTracking={isTracking}
                            isFollowing={isFollowing}
                            smartModeActive={smartModeActive}
                            handleTrackingToggle={handleTrackingToggle}
                            handleButtonClick={handleButtonClick}
                            handleToggleSmartMode={handleToggleSmartMode}
                          />
                        </CardContent>
                      </Card>

                      {/* Tracker Selector */}
                      <Card variant="outlined">
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <TrackerSelector />
                        </CardContent>
                      </Card>

                      {/* Follower Quick Control */}
                      <Card variant="outlined">
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <FollowerQuickControl />
                        </CardContent>
                      </Card>
                    </Box>
                  </Grid>

                  {/* Main Video Feed + Streaming Settings */}
                  <Grid item xs={12} lg={9}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      {/* Video Feed */}
                      <Card variant="outlined" sx={{ bgcolor: 'background.paper', minHeight: 400, position: 'relative' }}>
                        <RecordingIndicator />
                        <CardContent sx={{ p: 1 }}>
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
                        </CardContent>
                      </Card>

                      {/* Streaming Settings - Horizontal Below Video */}
                      <Card variant="outlined">
                        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                          <Grid container spacing={3}>
                            {/* Stream Settings Section */}
                            <Grid item xs={12} md={4}>
                              <Typography
                                variant="caption"
                                sx={{
                                  display: 'block',
                                  fontWeight: 700,
                                  color: 'text.secondary',
                                  textTransform: 'uppercase',
                                  letterSpacing: 1,
                                  mb: 1.5,
                                  fontSize: 11
                                }}
                              >
                                Stream
                              </Typography>
                              <Grid container spacing={2} alignItems="center">
                                {/* Protocol Selector */}
                                <Grid item xs={12} sm={6}>
                                  <FormControl variant="outlined" fullWidth size="small">
                                    <InputLabel>Protocol</InputLabel>
                                    <Select
                                      value={streamingProtocol}
                                      onChange={(e) => setStreamingProtocol(e.target.value)}
                                      label="Protocol"
                                    >
                                      <MenuItem value="auto">Auto</MenuItem>
                                      <MenuItem value="webrtc">WebRTC</MenuItem>
                                      <MenuItem value="websocket">WebSocket</MenuItem>
                                      <MenuItem value="http">HTTP</MenuItem>
                                    </Select>
                                  </FormControl>
                                </Grid>

                                {/* Streaming Status */}
                                <Grid item xs={12} sm={6}>
                                  <StreamingStatusIndicator />
                                </Grid>
                              </Grid>
                            </Grid>

                            {/* OSD Section */}
                            <Grid item xs={12} md={4}>
                              <Typography
                                variant="caption"
                                sx={{
                                  display: 'block',
                                  fontWeight: 700,
                                  color: 'text.secondary',
                                  textTransform: 'uppercase',
                                  letterSpacing: 1,
                                  mb: 1.5,
                                  fontSize: 11
                                }}
                              >
                                On-Screen Display
                              </Typography>
                              <OSDToggle />
                            </Grid>

                            {/* Recording Section */}
                            <Grid item xs={12} md={4}>
                              <Typography
                                variant="caption"
                                sx={{
                                  display: 'block',
                                  fontWeight: 700,
                                  color: 'text.secondary',
                                  textTransform: 'uppercase',
                                  letterSpacing: 1,
                                  mb: 1.5,
                                  fontSize: 11
                                }}
                              >
                                Recording
                              </Typography>
                              <RecordingQuickControl />
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Operational Status Bar */}
          <Grid item xs={12}>
            <OperationalStatusBar
              isTracking={trackerStatus}
              smartModeActive={smartModeActive}
              isFollowing={isFollowing}
              circuitBreakerActive={circuitBreakerActive}
            />
          </Grid>

          {/* Status Cards Row */}
          <Grid item xs={12}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <TrackerStatusCard />
              </Grid>
              <Grid item xs={12} md={4}>
                <FollowerStatusCard followerData={followerData} />
              </Grid>
              <Grid item xs={12} md={4}>
                <CircuitBreakerStatusCard />
              </Grid>
            </Grid>
          </Grid>

          {/* Config & Stats Row */}
          <Grid item xs={12}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <SafetyConfigCard followerName={currentProfile?.mode} />
              </Grid>
              <Grid item xs={12} md={4}>
                <StreamingStats />
              </Grid>
              <Grid item xs={12} md={4}>
                <YOLOModelSelector />
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      )}

      {/* Quick Config Drawer */}
      <QuickConfigDrawer open={configDrawerOpen} onClose={() => setConfigDrawerOpen(false)} />

      {/* Snackbar */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000}
        onClose={handleSnackbarClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleSnackbarClose} severity={snackbarSeverity} sx={{ width: '100%' }}>
          <Typography variant="body2">{snackbarMessage}</Typography>
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default DashboardPage;
