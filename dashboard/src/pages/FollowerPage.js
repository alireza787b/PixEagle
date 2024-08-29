import React, { useState, useEffect } from 'react';
import { Container, Grid, Typography, CircularProgress, Button, Card, CardContent, Divider } from '@mui/material';
import { CSSTransition } from 'react-transition-group';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import PollingStatusIndicator from '../components/PollingStatusIndicator';
import axios from 'axios';

const POLLING_RATE = parseInt(process.env.REACT_APP_POLLING_RATE, 10);
const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

const FollowerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [followerData, setFollowerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [pollingStatus, setPollingStatus] = useState('idle'); // idle, success, error

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

  useEffect(() => {
    console.log('Telemetry Data State:', { trackerData, followerData });
  }, [trackerData, followerData]);

  const handleToggleRawData = () => {
    setShowRawData((prevShowRawData) => !prevShowRawData);
  };

  if (trackerData.length === 0 && followerData.length === 0) {
    return (
      <Container>
        <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
        <Typography variant="h6" gutterBottom>No data loaded yet</Typography>
        <CircularProgress />
      </Container>
    );
  }

  const latestFollowerData = followerData[followerData.length - 1] || {};

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
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
        <Grid item xs={12} md={4}>
          <StaticPlot title="Velocity X vs Time" data={followerData} dataKey="vel_x" />
        </Grid>
        <Grid item xs={12} md={4}>
          <StaticPlot title="Velocity Y vs Time" data={followerData} dataKey="vel_y" />
        </Grid>
        <Grid item xs={12} md={4}>
          <StaticPlot title="Velocity Z vs Time" data={followerData} dataKey="vel_z" />
        </Grid>
        {latestFollowerData.yaw_rate !== undefined && (
          <Grid item xs={12} md={4}>
            <StaticPlot title="Yaw Rate vs Time" data={followerData} dataKey="yaw_rate" />
          </Grid>
        )}

        {/* Profile Information Section */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Profile: {latestFollowerData.profile_name || 'Unknown'}</Typography>
              <Divider style={{ marginBottom: '10px' }} />
              <Typography variant="body1">Vel X: {latestFollowerData.vel_x || 'N/A'}</Typography>
              <Typography variant="body1">Vel Y: {latestFollowerData.vel_y || 'N/A'}</Typography>
              <Typography variant="body1">Vel Z: {latestFollowerData.vel_z || 'N/A'}</Typography>
              {latestFollowerData.yaw_rate !== undefined && (
                <Typography variant="body1">Yaw Rate: {latestFollowerData.yaw_rate}</Typography>
              )}
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
