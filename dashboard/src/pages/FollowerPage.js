// dashboard/src/pages/FollowerPage.js
import React, { useState, useEffect } from 'react';
import { 
  Container, 
  Grid, 
  Typography, 
  CircularProgress, 
  Button, 
  Card, 
  CardContent, 
  Divider,
  Box,
  Alert
} from '@mui/material';
import { CSSTransition } from 'react-transition-group';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import PollingStatusIndicator from '../components/PollingStatusIndicator';
import DynamicFieldDisplay from '../components/DynamicFieldDisplay';
import FollowerProfileSelector from '../components/FollowerProfileSelector';
import { useFollowerSchema, useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import axios from 'axios';

const POLLING_RATE = parseInt(process.env.REACT_APP_POLLING_RATE, 10);
const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

const FollowerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [followerData, setFollowerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [pollingStatus, setPollingStatus] = useState('idle');

  // Schema-aware hooks
  const { schema, loading: schemaLoading, error: schemaError } = useFollowerSchema();
  const { currentProfile, loading: profileLoading, error: profileError } = useCurrentFollowerProfile();

  const fetchTelemetryData = async () => {
    try {
      setPollingStatus('idle');
      const trackerResponse = await axios.get(`${API_URL}/telemetry/tracker_data`);
      const followerResponse = await axios.get(`${API_URL}/telemetry/follower_data`);
      
      if (trackerResponse.status === 200 && followerResponse.status === 200) {
        setTrackerData((prevData) => [...prevData, trackerResponse.data]);
        setFollowerData((prevData) => [...prevData, followerResponse.data]);
        setRawData((prevData) => [
          ...prevData,
          { type: 'tracker', data: trackerResponse.data },
          { type: 'follower', data: followerResponse.data },
        ]);
        setPollingStatus('success');
      }
    } catch (error) {
      setPollingStatus('error');
      console.error('Error fetching telemetry data:', error);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
      fetchTelemetryData();
    }, POLLING_RATE);

    return () => clearInterval(interval);
  }, []);

  const handleToggleRawData = () => {
    setShowRawData((prevShowRawData) => !prevShowRawData);
  };

  // Loading state
  if (schemaLoading || profileLoading) {
    return (
      <Container>
        <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <CircularProgress />
          <Typography variant="h6">Loading schema and profile data...</Typography>
        </Box>
      </Container>
    );
  }

  // Error state
  if (schemaError || profileError) {
    return (
      <Container>
        <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="h6">Error Loading Data</Typography>
          {schemaError && <Typography>Schema Error: {schemaError}</Typography>}
          {profileError && <Typography>Profile Error: {profileError}</Typography>}
        </Alert>
      </Container>
    );
  }

  const latestFollowerData = followerData[followerData.length - 1] || {};
  const currentFieldValues = latestFollowerData.fields || {};

  return (
    <Container>
      <Typography variant="h4" gutterBottom>
        Enhanced Follower Visualization
      </Typography>

      {/* Profile Management Section */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <FollowerProfileSelector />
        </CardContent>
      </Card>

      {/* Dynamic Field Display */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <DynamicFieldDisplay
            schema={schema}
            currentProfile={currentProfile}
            fieldValues={currentFieldValues}
          />
        </CardContent>
      </Card>

      {/* Traditional Plots Section */}
      <Typography variant="h5" gutterBottom sx={{ mt: 4 }}>
        Telemetry Plots
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <ScopePlot title="XY Plot" trackerData={trackerData} followerData={followerData} />
        </Grid>

        <Grid item xs={12} md={6}>
          <StaticPlot title="Center X vs Time" data={trackerData} dataKey="center.0" />
        </Grid>
        <Grid item xs={12} md={6}>
          <StaticPlot title="Center Y vs Time" data={trackerData} dataKey="center.1" />
        </Grid>

        {/* Dynamic field plots based on available fields */}
        {currentProfile && currentProfile.available_fields && 
          currentProfile.available_fields.map((fieldName) => (
            <Grid item xs={12} md={4} key={fieldName}>
              <StaticPlot 
                title={`${fieldName.replace('_', ' ').toUpperCase()} vs Time`} 
                data={followerData} 
                dataKey={fieldName} 
              />
            </Grid>
          ))
        }

        {/* Legacy Profile Information */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Legacy Profile Info: {latestFollowerData.profile_name || 'Unknown'}
              </Typography>
              <Divider style={{ marginBottom: '10px' }} />
              
              {/* Display all available field values */}
              {Object.entries(currentFieldValues).map(([fieldName, value]) => (
                <Typography key={fieldName} variant="body1">
                  {fieldName}: {typeof value === 'number' ? value.toFixed(3) : value}
                </Typography>
              ))}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12}>
          <Button variant="contained" color="primary" onClick={handleToggleRawData}>
            {showRawData ? 'Hide Raw Data Log' : 'Show Raw Data Log'}
          </Button>
          <CSSTransition in={showRawData} timeout={300} classNames="fade" unmountOnExit>
            <RawDataLog rawData={rawData} />
          </CSSTransition>
        </Grid>
      </Grid>

      <div style={{ marginTop: '20px' }}>
        <Typography variant="h6">Telemetry Status:</Typography>
        <PollingStatusIndicator status={pollingStatus} />
      </div>
    </Container>
  );
};

export default FollowerPage;