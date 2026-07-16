// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect, useCallback } from 'react';
import {
  Container, Typography, CircularProgress, Box, Grid, Snackbar, Alert,
  FormControl, InputLabel, Select, MenuItem, IconButton, Tooltip,
  Accordion, AccordionDetails, AccordionSummary, Divider, Paper, Stack,
} from '@mui/material';
import { ExpandMore, TrackChanges, Settings as SettingsIcon } from '@mui/icons-material';

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
import { buildActionRequest } from '../services/actionRequests';
import axios, { apiFetch, apiFetchJson, getMediaElementCrossOrigin } from '../services/apiClient';
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
  const [selectionArmed, setSelectionArmed] = useState(false);
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
    actionError: targetSelectionError,
    clearActionError: clearTargetSelectionError,
  } = useBoundingBoxHandlers(
    selectionArmed,
    setSelectionArmed,
    smartModeActive,
    trackerStatus.activeTracking,
  );

  const handleSelectionToggle = () => {
    setSelectionArmed((armed) => !armed);
  };

  useEffect(() => {
    if (!targetSelectionError) return;
    setSnackbarMessage(targetSelectionError);
    setSnackbarSeverity('error');
    setSnackbarOpen(true);
    clearTargetSelectionError();
  }, [clearTargetSelectionError, targetSelectionError]);

  useEffect(() => {
    if (smartModeActive) {
      setSelectionArmed(false);
    }
  }, [smartModeActive]);

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
        endpoint === endpoints.offboardStartAction
      );
      const isStopEndpoint = (
        endpoint === endpoints.offboardStopAction
      );
      const isAbortEndpoint = (
        endpoint === endpoints.operatorAbortAction
      );
      const isRedetectEndpoint = (
        endpoint === endpoints.trackingRedetectAction
      );
      const isSegmentationEndpoint = (
        endpoint === endpoints.segmentationToggleAction
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
      } else if (isRedetectEndpoint && data.status === 'success') {
        setSnackbarMessage('Re-detect completed');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      } else if (isSegmentationEndpoint && data.status === 'success') {
        const enabled = data.result?.legacy_result?.segmentation_active;
        setSnackbarMessage(`Segmentation ${enabled ? 'enabled' : 'disabled'}`);
        setSnackbarSeverity('info');
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
        setSelectionArmed(false);
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
      const data = await apiFetchJson(endpoints.smartModeToggleAction, {
        method: 'POST',
        body: JSON.stringify(buildActionRequest(
          'toggle_smart_mode',
          { ui: 'dashboard_tracker_mode_control' }
        )),
      });
      if (data?.status === 'failure') {
        throw new Error(data.error || 'Smart mode toggle action failed');
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
    <Container
      maxWidth="xl"
      sx={{ py: { xs: 1, md: 2 }, px: { xs: 1, sm: 2, md: 3 }, mb: 2 }}
    >
      {loading ? (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      ) : (
        <Stack spacing={1.5}>
          <OperationalStatusBar
            trackerStatus={trackerStatus}
            smartModeActive={smartModeActive}
            isFollowing={isFollowing}
            circuitBreakerActive={circuitBreakerActive}
            telemetryStatus={telemetryStatus}
          />

          <Grid container spacing={1.5} alignItems="flex-start" sx={{ width: '100%', m: 0 }}>
            <Grid item xs={12} lg={8} sx={{ order: { xs: 1, lg: 1 } }}>
              <Paper variant="outlined" sx={{ overflow: 'hidden', position: 'relative', borderRadius: 1 }}>
                <RecordingIndicator />
                <BoundingBoxDrawer
                  isTracking={trackerStatus.activeTracking}
                  selectionArmed={selectionArmed}
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
                <Divider />
                <Box
                  sx={{
                    p: 1.25,
                    display: 'grid',
                    gridTemplateColumns: { xs: 'minmax(0, 1fr)', sm: 'minmax(220px, 1fr) auto minmax(150px, 0.7fr)' },
                    gap: 1.25,
                    alignItems: 'center',
                  }}
                >
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                    <FormControl variant="outlined" size="small" sx={{ minWidth: 118 }}>
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
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <StreamingStatusIndicator />
                    </Box>
                  </Stack>
                  <OSDToggle compact />
                  <RecordingQuickControl />
                </Box>
              </Paper>
            </Grid>

            <Grid item xs={12} lg={4} sx={{ order: { xs: 2, lg: 2 } }}>
              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.25 }}>
                  <TrackChanges color="primary" fontSize="small" />
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1 }}>Command</Typography>
                  <Tooltip title="Quick settings">
                    <IconButton size="small" aria-label="Open quick settings" onClick={() => setConfigDrawerOpen(true)}>
                      <SettingsIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                <ActionButtons
                  selectionArmed={selectionArmed}
                  trackingActive={trackerStatus.activeTracking}
                  trackerStatus={trackerStatus}
                  isFollowing={isFollowing}
                  smartModeActive={smartModeActive}
                  handleSelectionToggle={handleSelectionToggle}
                  handleButtonClick={handleButtonClick}
                  handleToggleSmartMode={handleToggleSmartMode}
                />
                <Divider sx={{ my: 1.5 }} />
                <TrackerSelector />
                <Divider sx={{ my: 1.5 }} />
                <FollowerQuickControl />
              </Paper>
            </Grid>
          </Grid>

          <Grid container spacing={1.5} sx={{ width: '100%', m: 0 }}>
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

          <Accordion
            elevation={0}
            disableGutters
            sx={{
              borderTop: 1,
              borderBottom: 1,
              borderColor: 'divider',
              borderRadius: 0,
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>Diagnostics and configuration</Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ px: 0, pt: 0 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <SafetyConfigCard followerName={currentProfile?.mode} />
              </Grid>
              <Grid item xs={12} md={4}>
                <StreamingStats />
              </Grid>
              <Grid item xs={12} md={4}>
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1, height: '100%' }}>
                  <Typography variant="subtitle2" gutterBottom>Detection Model</Typography>
                  <ModelQuickControl />
                </Paper>
              </Grid>
            </Grid>
            </AccordionDetails>
          </Accordion>
        </Stack>
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
