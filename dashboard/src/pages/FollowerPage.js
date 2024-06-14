import React from 'react';
import { Container, Grid, Typography, CircularProgress } from '@mui/material';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import useWebSocket from '../hooks/useWebSocket';

const WEBSOCKET_URL = `ws://${process.env.REACT_APP_WEBSOCKET_HOST}:${process.env.REACT_APP_WEBSOCKET_PORT}${process.env.REACT_APP_WEBSOCKET_PATH}`;

const FollowerPage = () => {
  const { trackerData, rawData } = useWebSocket(WEBSOCKET_URL);

  if (trackerData.length === 0) {
    return (
      <Container>
        <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
        <Typography variant="h6" gutterBottom>No data loaded yet</Typography>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Follower Visualization</Typography>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <ScopePlot title="XY Plot" trackerData={trackerData} />
        </Grid>
        <Grid item xs={12} md={6}>
          <StaticPlot title="Center X vs Time" trackerData={trackerData} dataKey="center[0]" />
        </Grid>
        <Grid item xs={12} md={6}>
          <StaticPlot title="Center Y vs Time" trackerData={trackerData} dataKey="center[1]" />
        </Grid>
        <Grid item xs={12}>
          <RawDataLog rawData={rawData} />
        </Grid>
      </Grid>
    </Container>
  );
};

export default FollowerPage;
