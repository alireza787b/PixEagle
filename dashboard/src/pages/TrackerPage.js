import React, { useState } from 'react';
import { Container, Grid, Typography, CircularProgress, Button } from '@mui/material';
import { CSSTransition } from 'react-transition-group';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import useWebSocket from '../hooks/useWebSocket';

const WEBSOCKET_URL = `ws://${process.env.REACT_APP_WEBSOCKET_HOST}:${process.env.REACT_APP_WEBSOCKET_PORT}${process.env.REACT_APP_WEBSOCKET_PATH}`;

const TrackerPage = () => {
  const { trackerData, rawData } = useWebSocket(WEBSOCKET_URL);
  const [showRawData, setShowRawData] = useState(false);

  const handleToggleRawData = () => {
    setShowRawData((prevShowRawData) => !prevShowRawData);
  };

  if (trackerData.length === 0) {
    return (
      <Container>
        <Typography variant="h4" gutterBottom>Tracker Visualization</Typography>
        <Typography variant="h6" gutterBottom>No data loaded yet</Typography>
        <CircularProgress />
      </Container>
    );
  }

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Tracker Visualization</Typography>
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
          <Button variant="contained" color="primary" onClick={handleToggleRawData}>
            {showRawData ? 'Hide Raw Data Log' : 'Show Raw Data Log'}
          </Button>
          <CSSTransition
            in={showRawData}
            timeout={300}
            classNames="fade"
            unmountOnExit
          >
            <RawDataLog rawData={rawData} />
          </CSSTransition>
        </Grid>
      </Grid>
    </Container>
  );
};

export default TrackerPage;
