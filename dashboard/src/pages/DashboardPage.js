// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect } from 'react';
import {
  Container, Typography, CircularProgress, Box, Grid, Snackbar, Alert,
  FormControl, InputLabel, Select, MenuItem, Divider, Card, CardContent,
  Chip, Button
} from '@mui/material';
import { 
  TrackChanges, 
  FlightTakeoff, 
  LiveTv,
  Speed,
  Rotate90DegreesCcw,
  Warning,
  CheckCircle
} from '@mui/icons-material';

import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';
import StatusIndicator from '../components/StatusIndicator';
import FollowerStatusCard from '../components/FollowerStatusCard';
import FollowerQuickControl from '../components/FollowerQuickControl';

import { videoFeed, endpoints } from '../services/apiEndpoints';
import {
  useTrackerStatus,
  useFollowerStatus,
  useSmartModeStatus
} from '../hooks/useStatuses';
import { useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import useBoundingBoxHandlers from '../hooks/useBoundingBoxHandlers';
import axios from 'axios';

const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

const SystemHealthCard = ({ trackerStatus, isFollowing, smartModeActive }) => {
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          System Health
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Tracking:</Typography>
            <Chip 
              label={trackerStatus ? 'Active' : 'Inactive'}
              color={trackerStatus ? 'success' : 'default'}
              size="small"
              icon={trackerStatus ? <CheckCircle /> : <Warning />}
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Following:</Typography>
            <Chip 
              label={isFollowing ? 'Active' : 'Inactive'}
              color={isFollowing ? 'success' : 'default'}
              size="small"
              icon={isFollowing ? <CheckCircle /> : <Warning />}
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Smart Mode:</Typography>
            <Chip 
              label={smartModeActive ? 'YOLO' : 'CSRT'}
              color={smartModeActive ? 'secondary' : 'primary'}
              size="small"
            />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Connection:</Typography>
            <Chip 
              label="Connected"
              color="success"
              size="small"
            />
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

const QuickActionsCard = () => {
  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Quick Navigation
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Button 
            variant="outlined" 
            onClick={() => window.location.href = '/tracker'}
            startIcon={<TrackChanges />}
            fullWidth
            size="small"
          >
            Tracker Control
          </Button>
          <Button 
            variant="outlined"
            onClick={() => window.location.href = '/follower'}
            startIcon={<FlightTakeoff />}
            fullWidth
            size="small"
          >
            Follower Control
          </Button>
          <Button 
            variant="outlined"
            onClick={() => window.location.href = '/live-feed'}
            startIcon={<LiveTv />}
            fullWidth
            size="small"
          >
            Live Feed
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

const DashboardPage = () => {
  const [isTracking, setIsTracking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('websocket');
  const [smartModeActive, setSmartModeActive] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [followerData, setFollowerData] = useState({});

  const checkInterval = 2000;

  const isFollowing = useFollowerStatus(checkInterval);
  const trackerStatus = useTrackerStatus(checkInterval);
  const smartModeStatus = useSmartModeStatus(checkInterval);
  const { currentProfile } = useCurrentFollowerProfile();

  useEffect(() => {
    setSmartModeActive(smartModeStatus);
  }, [smartModeStatus]);

  // Fetch follower telemetry data
  useEffect(() => {
    const fetchFollowerData = async () => {
      try {
        const response = await axios.get(`${API_URL}/telemetry/follower_data`);
        setFollowerData(response.data);
      } catch (error) {
        console.error('Error fetching follower data:', error);
      }
    };

    // Initial fetch
    fetchFollowerData();
    
    // Set up polling
    const interval = setInterval(fetchFollowerData, 2000);
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
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom align="center">
          PixEagle Dashboard
        </Typography>
        <Typography variant="subtitle1" color="textSecondary" align="center">
          System Overview and Real-time Control
        </Typography>
      </Box>

      {loading ? (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {/* Top Status Cards Row */}
          <Grid item xs={12}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <FollowerStatusCard followerData={followerData} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <SystemHealthCard 
                  trackerStatus={trackerStatus}
                  isFollowing={isFollowing}
                  smartModeActive={smartModeActive}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FollowerQuickControl />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <QuickActionsCard />
              </Grid>
            </Grid>
          </Grid>

          {/* Main Control Section */}
          <Grid item xs={12}>
            <Grid container spacing={2}>
              {/* Sidebar Controls */}
              <Grid item xs={12} sm={3} md={2}>
                <Grid container direction="column" spacing={2}>
                  {/* Tracker Mode Controls */}
                  <Grid item>
                    <Card>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>Tracker Control</Typography>
                        <ActionButtons
                          isTracking={isTracking}
                          smartModeActive={smartModeActive}
                          handleTrackingToggle={handleTrackingToggle}
                          handleButtonClick={handleButtonClick}
                          handleToggleSmartMode={handleToggleSmartMode}
                        />
                      </CardContent>
                    </Card>
                  </Grid>

                  <Divider sx={{ my: 1 }} />

                  {/* Streaming Protocol */}
                  <Grid item>
                    <Card>
                      <CardContent>
                        <FormControl variant="outlined" fullWidth size="small">
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
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Current Status Summary */}
                  <Grid item>
                    <Card>
                      <CardContent>
                        <Typography variant="subtitle2" gutterBottom>Current Status</Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                          <StatusIndicator label="Tracking" status={trackerStatus} />
                          <StatusIndicator label="Following" status={isFollowing} />
                          {currentProfile && currentProfile.active && (
                            <Box sx={{ mt: 1 }}>
                              <Typography variant="caption" color="textSecondary">
                                Profile:
                              </Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {currentProfile.display_name}
                              </Typography>
                            </Box>
                          )}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>

              {/* Main Video + Bounding Box */}
              <Grid item xs={12} sm={9} md={10}>
                <Card>
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
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      )}

      {/* Enhanced Snackbar confirmation */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000}
        onClose={handleSnackbarClose}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={handleSnackbarClose} severity="info" sx={{ width: '100%' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2">
              Switched to {smartModeActive ? 'Smart Tracker (YOLO)' : 'Classic Tracker (CSRT)'}
            </Typography>
          </Box>
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default DashboardPage;