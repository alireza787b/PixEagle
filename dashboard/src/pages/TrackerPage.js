import React, { useState, useEffect } from 'react';
import { Container, Grid, Typography, CircularProgress, Button, Paper, Box } from '@mui/material';
import { CSSTransition } from 'react-transition-group';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import PollingStatusIndicator from '../components/PollingStatusIndicator';
import TrackerDataDisplay from '../components/TrackerDataDisplay';
import { useTrackerSchema, useCurrentTrackerStatus, useTrackerDataTypes, useTrackerOutput } from '../hooks/useTrackerSchema';
import axios from 'axios';

const POLLING_RATE = parseInt(process.env.REACT_APP_POLLING_RATE, 10);
const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

const TrackerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [pollingStatus, setPollingStatus] = useState('idle'); // idle, success, error
  
  // Schema-driven tracker hooks
  const { schema, loading: schemaLoading, error: schemaError } = useTrackerSchema();
  const { currentStatus, loading: statusLoading, error: statusError } = useCurrentTrackerStatus();
  const { output, loading: outputLoading, error: outputError } = useTrackerOutput();

  const fetchTrackerData = async () => {
    try {
      setPollingStatus('idle');
      // Use schema-driven endpoint instead of legacy telemetry endpoint
      const response = await axios.get(`${API_URL}/api/tracker/output`);
      if (response.status === 200) {
        console.log('Fetched Schema-Driven Tracker Data:', response.data);
        setTrackerData((prevData) => [...prevData, response.data]);
        setRawData((prevData) => [...prevData, { type: 'tracker_output', data: response.data }]);
        setPollingStatus('success');
      }
    } catch (error) {
      setPollingStatus('error');
      console.error('Error fetching schema-driven tracker data:', error);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
      fetchTrackerData();
    }, POLLING_RATE);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    console.log('Tracker Data State:', trackerData);
  }, [trackerData]);

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

  const lastData = trackerData[trackerData.length - 1];
  console.log('Last Data:', lastData);

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Tracker Visualization</Typography>
      <Grid container spacing={3}>
        {/* Schema-driven Tracker Data Display */}
        <Grid item xs={12} md={6}>
          <TrackerDataDisplay
            currentStatus={currentStatus}
            trackerData={output}
            schema={schema}
            loading={statusLoading || schemaLoading}
            error={statusError || schemaError}
            showSchema={true}
            compact={false}
          />
        </Grid>
        
        {/* Current Output Values */}
        <Grid item xs={12} md={6}>
          <Paper elevation={2} sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>Current Output</Typography>
            {outputLoading ? (
              <CircularProgress size={24} />
            ) : outputError ? (
              <Typography color="error">{outputError}</Typography>
            ) : output ? (
              <Box sx={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
                <pre>{JSON.stringify(output, null, 2)}</pre>
              </Box>
            ) : (
              <Typography color="text.secondary">No output data</Typography>
            )}
          </Paper>
        </Grid>
        
        <Grid item xs={12}>
          <ScopePlot title="XY Plot" trackerData={trackerData} />
        </Grid>
        <Grid item xs={12} md={6}>
          <StaticPlot title="Center X vs Time" data={trackerData} dataKey="center.0" />
        </Grid>
        <Grid item xs={12} md={6}>
          <StaticPlot title="Center Y vs Time" data={trackerData} dataKey="center.1" />
        </Grid>
        
        {/* Schema-driven tracker field plots */}
        {currentStatus && currentStatus.fields && Object.entries(currentStatus.fields).map(([fieldName, fieldData]) => {
          // Only plot numeric fields that are not arrays or are 2D positions
          const isNumeric = fieldData.type === 'float' || fieldData.type === 'int';
          const isPosition2D = fieldData.type === 'tuple' && Array.isArray(fieldData.value) && fieldData.value.length === 2;
          
          if (!isNumeric && !isPosition2D) return null;
          
          const plotTitle = `${fieldData.display_name || fieldName.replace('_', ' ')} vs Time`;
          
          return (
            <Grid item xs={12} md={6} key={fieldName}>
              <StaticPlot 
                title={plotTitle}
                data={output ? [output] : []} 
                dataKey={fieldName} 
              />
            </Grid>
          );
        })}
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
      <div style={{ marginTop: '20px' }}>
        <Typography variant="h6">Telemetry Status:</Typography>
        <PollingStatusIndicator status={pollingStatus} />
      </div>
    </Container>
  );
};

export default TrackerPage;
