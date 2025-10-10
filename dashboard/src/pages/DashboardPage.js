// dashboard/src/pages/DashboardPage.js
import React, { useState, useEffect } from 'react';
import {
  Container, Typography, CircularProgress, Box, Grid, Snackbar, Alert,
  FormControl, InputLabel, Select, MenuItem, Card, CardContent,
  Chip, Button
} from '@mui/material';
import {
  TrackChanges,
  FlightTakeoff,
  LiveTv,
  Speed,
  Warning,
  CheckCircle,
  Security
} from '@mui/icons-material';

import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';
import FollowerStatusCard from '../components/FollowerStatusCard';
import TrackerStatusCard from '../components/TrackerStatusCard';
import FollowerQuickControl from '../components/FollowerQuickControl';
import StreamingStats from '../components/StreamingStats';
import CircuitBreakerStatusCard from '../components/CircuitBreakerStatusCard';
import OSDToggle from '../components/OSDToggle';


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

const SystemHealthCard = ({ trackerStatus, isFollowing, smartModeActive, circuitBreakerActive }) => {
  const getSystemStatus = () => {
    if (circuitBreakerActive) return { label: 'Testing Mode', color: 'warning', icon: <Security /> };
    if (trackerStatus && isFollowing) return { label: 'Fully Active', color: 'success', icon: <CheckCircle /> };
    if (trackerStatus || isFollowing) return { label: 'Partially Active', color: 'warning', icon: <Warning /> };
    return { label: 'Standby', color: 'default', icon: <Warning /> };
  };

  const systemStatus = getSystemStatus();

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Speed color="action" />
          <Typography variant="h6">🏥 System Health</Typography>
          <Chip
            label={systemStatus.label}
            color={systemStatus.color}
            size="small"
            icon={systemStatus.icon}
            sx={{ fontWeight: 'bold' }}
          />
        </Box>
        
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
          <Chip 
            label={`Tracking: ${trackerStatus ? 'ON' : 'OFF'}`}
            color={trackerStatus ? 'success' : 'default'}
            size="small"
            variant="outlined"
          />
          <Chip 
            label={`Following: ${isFollowing ? 'ON' : 'OFF'}`}
            color={isFollowing ? 'success' : 'default'}
            size="small"
            variant="outlined"
          />
        </Box>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="body2" color="textSecondary">
            Detection Mode:
          </Typography>
          <Chip 
            label={smartModeActive ? 'YOLO (Smart)' : 'CSRT (Classic)'}
            color={smartModeActive ? 'secondary' : 'primary'}
            size="small"
          />
        </Box>
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
          <Typography variant="body2" color="textSecondary">
            Connection:
          </Typography>
          <Chip
            label="Online"
            color="success"
            size="small"
            variant="outlined"
          />
        </Box>

        {/* Circuit Breaker Status */}
        {circuitBreakerActive !== undefined && (
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1 }}>
            <Typography variant="body2" color="textSecondary">
              Safety Mode:
            </Typography>
            <Chip
              label={circuitBreakerActive ? 'Testing' : 'Live'}
              color={circuitBreakerActive ? 'warning' : 'success'}
              size="small"
              variant={circuitBreakerActive ? 'filled' : 'outlined'}
              icon={circuitBreakerActive ? <Security /> : <CheckCircle />}
            />
          </Box>
        )}
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
  const [circuitBreakerActive, setCircuitBreakerActive] = useState(undefined);

  const checkInterval = 2000;

  const isFollowing = useFollowerStatus(checkInterval);
  const trackerStatus = useTrackerStatus(checkInterval);
  const smartModeStatus = useSmartModeStatus(checkInterval);
  const { currentProfile } = useCurrentFollowerProfile();

  useEffect(() => {
    setSmartModeActive(smartModeStatus);
  }, [smartModeStatus]);

  // Unified data fetching for better performance
  useEffect(() => {
    const fetchAllData = async () => {
      try {
        // Fetch all data in parallel
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

    // Initial fetch
    fetchAllData();

    // Set up unified polling interval
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
    <Container maxWidth="xl" sx={{ mt: 2, mb: 4 }}>
      <Box sx={{
        mb: 3,
        py: 2,
        borderBottom: '1px solid',
        borderColor: 'divider',
        borderRadius: 1
      }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 500, color: 'text.primary' }}>
          🦅 PixEagle Dashboard
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Professional Drone Control & Tracking System
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
          {/* PRIMARY: Main Video Feed Section - Hero Section */}

          {/* PRIMARY: Main Video and Controls Section */}
          <Grid item xs={12}>
            <Card elevation={4} sx={{ mb: 2 }}>
              <CardContent sx={{ p: 2 }}>
                <Grid container spacing={2}>
                  {/* Control Panel - Sidebar */}
                  <Grid item xs={12} lg={3}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
                      {/* Primary Controls */}
                      <Card variant="outlined" sx={{ minHeight: 200 }}>
                        <CardContent>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                            <TrackChanges color="primary" />
                            <Typography variant="h6">Control Panel</Typography>
                          </Box>
                          <ActionButtons
                            isTracking={isTracking}
                            smartModeActive={smartModeActive}
                            handleTrackingToggle={handleTrackingToggle}
                            handleButtonClick={handleButtonClick}
                            handleToggleSmartMode={handleToggleSmartMode}
                          />
                        </CardContent>
                      </Card>

                      {/* Settings */}
                      <Card variant="outlined" sx={{ minHeight: 120 }}>
                        <CardContent>
                          <Typography variant="subtitle1" gutterBottom>Settings</Typography>
                          <FormControl variant="outlined" fullWidth size="small">
                            <InputLabel>Streaming Protocol</InputLabel>
                            <Select
                              value={streamingProtocol}
                              onChange={(e) => setStreamingProtocol(e.target.value)}
                              label="Streaming Protocol"
                            >
                              <MenuItem value="websocket">WebSocket</MenuItem>
                              <MenuItem value="http">HTTP</MenuItem>
                            </Select>
                          </FormControl>

                          {/* OSD Toggle Control */}
                          <OSDToggle />
                        </CardContent>
                      </Card>

                      {/* Active Profile Display */}
                      {currentProfile && currentProfile.active && (
                        <Card variant="outlined" sx={{ bgcolor: 'primary.light', color: 'primary.contrastText', minHeight: 100 }}>
                          <CardContent>
                            <Typography variant="subtitle2" gutterBottom>
                              Active Follower Profile
                            </Typography>
                            <Typography variant="body1" fontWeight="bold">
                              {currentProfile.display_name}
                            </Typography>
                            <Typography variant="caption" sx={{ opacity: 0.8 }}>
                              {currentProfile.description}
                            </Typography>
                          </CardContent>
                        </Card>
                      )}
                    </Box>
                  </Grid>

                  {/* Main Video Feed - Primary Focus */}
                  <Grid item xs={12} lg={9}>
                    <Card variant="outlined" sx={{ bgcolor: 'grey.50', minHeight: 400 }}>
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
              </CardContent>
            </Card>
          </Grid>

          {/* SECONDARY: System Status Cards Row - Below Video */}
          <Grid item xs={12}>
            <Grid container spacing={3} sx={{ minHeight: 200 }}>
              <Grid item xs={12} md={3}>
                <Box sx={{ height: '100%' }}>
                  <TrackerStatusCard />
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ height: '100%' }}>
                  <FollowerStatusCard followerData={followerData} />
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ height: '100%' }}>
                  <CircuitBreakerStatusCard />
                </Box>
              </Grid>
              <Grid item xs={12} md={3}>
                <Box sx={{ height: '100%' }}>
                  <SystemHealthCard
                    trackerStatus={trackerStatus}
                    isFollowing={isFollowing}
                    smartModeActive={smartModeActive}
                    circuitBreakerActive={circuitBreakerActive}
                  />
                </Box>
              </Grid>
            </Grid>
          </Grid>
          
          {/* TERTIARY: Quick Controls & Stats Row - Bottom */}
          <Grid item xs={12}>
            <Grid container spacing={2} sx={{ minHeight: 150 }}>
              <Grid item xs={12} sm={6} md={4}>
                <Box sx={{ height: '100%' }}>
                  <StreamingStats />
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <Box sx={{ height: '100%' }}>
                  <FollowerQuickControl />
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      System Navigation
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <Button 
                        variant="outlined" 
                        onClick={() => window.location.href = '/tracker'}
                        startIcon={<TrackChanges />}
                        size="small"
                      >
                        Tracker
                      </Button>
                      <Button 
                        variant="outlined"
                        onClick={() => window.location.href = '/follower'}
                        startIcon={<FlightTakeoff />}
                        size="small"
                      >
                        Follower
                      </Button>
                      <Button 
                        variant="outlined"
                        onClick={() => window.location.href = '/live-feed'}
                        startIcon={<LiveTv />}
                        size="small"
                      >
                        Live Feed
                      </Button>
                    </Box>
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