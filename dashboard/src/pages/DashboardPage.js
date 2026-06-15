// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect, useCallback } from 'react';
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
import ModelQuickControl from '../components/ModelQuickControl';
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
import axios, { apiFetch, getMediaElementCrossOrigin } from '../services/apiClient';
import {
  useTrackerStatus,
  useFollowerStatus,
  useFollowingTelemetry,
  useSmartModeStatus,
  useTelemetryHealth
} from '../hooks/useStatuses';
import { useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import useBoundingBoxHandlers from '../hooks/useBoundingBoxHandlers';

const DashboardPage = () => {
  const [isTracking, setIsTracking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('auto');
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  const [snackbarSeverity, setSnackbarSeverity] = useState('info');
  const [circuitBreakerActive, setCircuitBreakerActive] = useState(undefined);
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);

  const checkInterval = 2000;

  const isFollowing = useFollowerStatus(checkInterval);
  const trackerStatus = useTrackerStatus(checkInterval);
  const {
    smartModeActive,
    refresh: refreshSmartModeStatus,
  } = useSmartModeStatus(checkInterval);
  const { telemetryStatus } = useTelemetryHealth(checkInterval);
  const { followingTelemetry: followerData } = useFollowingTelemetry(checkInterval);
  const { currentProfile } = useCurrentFollowerProfile();

  // Circuit-breaker status remains separate until safety APIs are migrated to /api/v1.
  useEffect(() => {
    const fetchAllData = async () => {
      try {
        const circuitBreakerResponse = await axios
          .get(endpoints.circuitBreakerStatus)
          .catch(() => ({ data: { available: false } }));

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
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  } = useBoundingBoxHandlers(isTracking, setIsTracking, smartModeActive);

  const handleTrackingToggle = async () => {
    if (isTracking) {
      try {
        await apiFetch(endpoints.stopTracking, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
      } catch (error) {
        console.error('Error:', error);
      }
    }
    setIsTracking(!isTracking);
  };

  const handleButtonClick = async (endpoint, updateTrackingState = false, requestBody = null) => {
    try {
      const requestOptions = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      };
      if (requestBody) {
        requestOptions.body = JSON.stringify(requestBody);
      }

      const response = await apiFetch(endpoint, requestOptions);
      const data = await response.json();
      const legacyDetails = data.details || data.result?.legacy_result?.details || {};
      const isStartEndpoint = (
        endpoint === endpoints.startOffboardMode || endpoint === endpoints.offboardStartAction
      );
      const isStopEndpoint = (
        endpoint === endpoints.stopOffboardMode || endpoint === endpoints.offboardStopAction
      );
      const isAbortEndpoint = (
        endpoint === endpoints.cancelActivities || endpoint === endpoints.operatorAbortAction
      );

      if (isStartEndpoint && legacyDetails.auto_stopped) {
        setSnackbarMessage('Follower was active - automatically restarted');
        setSnackbarSeverity('info');
        setSnackbarOpen(true);
      }

      if (isStartEndpoint && data.status === 'success') {
        if (!legacyDetails.auto_stopped) {
          setSnackbarMessage('Follower started successfully');
          setSnackbarSeverity('success');
          setSnackbarOpen(true);
        }
      } else if (isStopEndpoint && data.status === 'success') {
        setSnackbarMessage('Follower stopped successfully');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      } else if (isAbortEndpoint && data.status === 'success') {
        setSnackbarMessage('Tracking activities cancelled');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      }

      if (!response.ok || data.status === 'failure') {
        setSnackbarMessage(
          `Operation failed: ${data.error || data.detail?.message || data.message || data.code || 'Unknown error'}`
        );
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
      const response = await apiFetch(endpoints.toggleSmartMode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!response.ok) {
        throw new Error(`Failed to toggle smart mode (HTTP ${response.status})`);
      }

      const syncedMode = await refreshSmartModeStatus({ suppressErrors: true });
      const activeMode = typeof syncedMode === 'boolean' ? syncedMode : smartModeActive;

      setSnackbarMessage(`Switched to ${activeMode ? 'Smart Tracker (AI)' : 'Classic Tracker'}`);
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

  // Keyboard shortcuts: M = toggle smart mode, R = toggle recording
  const handleKeyboardShortcut = useCallback((e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) return;

    const key = e.key.toLowerCase();
    if (key === 'm') {
      handleToggleSmartMode();
    } else if (key === 'r') {
      apiFetch(endpoints.recordingToggle, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }).catch((err) => console.error('Recording toggle failed:', err));
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.addEventListener('keydown', handleKeyboardShortcut);
    return () => window.removeEventListener('keydown', handleKeyboardShortcut);
  }, [handleKeyboardShortcut]);

  useEffect(() => {
    if (streamingProtocol === 'websocket' || streamingProtocol === 'webrtc' || streamingProtocol === 'auto') {
      setLoading(false);
      return;
    }

    const checkStream = setInterval(() => {
      const img = new Image();
      const crossOrigin = getMediaElementCrossOrigin();
      if (crossOrigin) {
        img.crossOrigin = crossOrigin;
      }
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
                            trackerStatus={trackerStatus}
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
                            handlePointerDown={handlePointerDown}
                            handlePointerMove={handlePointerMove}
                            handlePointerUp={handlePointerUp}
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
              trackerStatus={trackerStatus}
              smartModeActive={smartModeActive}
              isFollowing={isFollowing}
              circuitBreakerActive={circuitBreakerActive}
              telemetryStatus={telemetryStatus}
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
                <Card><CardContent>
                  <Typography variant="subtitle2" gutterBottom>Detection Model</Typography>
                  <ModelQuickControl />
                </CardContent></Card>
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
