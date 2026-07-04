import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Grid,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import {
  CropFree,
  ExpandMore,
  GpsFixed,
  Sensors,
  Timeline,
} from '@mui/icons-material';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import PollingStatusIndicator from '../components/PollingStatusIndicator';
import TrackerDataDisplay from '../components/TrackerDataDisplay';
import { useTrackerSchema, useCurrentTrackerStatus, useTrackerOutput } from '../hooks/useTrackerSchema';
import {
  buildNoCacheRequestConfig,
  isMissingTrackingTelemetryRoute,
  normalizeTrackingTelemetry,
} from '../hooks/useStatuses';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import {
  EMPTY_VALUE,
  formatAgeSeconds,
  formatLabel,
  formatOperatorValue,
} from '../utils/operatorFormat';

const POLLING_RATE = Number.parseInt(process.env.REACT_APP_POLLING_RATE, 10) || 1000;
const MAX_TELEMETRY_HISTORY = 120;
const MAX_RAW_DATA_ENTRIES = 200;

const appendBounded = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_TELEMETRY_HISTORY)
);

const appendBoundedRawData = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_RAW_DATA_ENTRIES)
);

const fetchTrackingTelemetrySnapshot = async () => {
  try {
    return await axios.get(endpoints.trackingTelemetry, buildNoCacheRequestConfig());
  } catch (trackingTelemetryError) {
    if (!isMissingTrackingTelemetryRoute(trackingTelemetryError)) {
      throw trackingTelemetryError;
    }
    return axios.get(endpoints.trackerData, buildNoCacheRequestConfig());
  }
};

const fieldValue = (fields, fieldName) => {
  const value = fields?.[fieldName];
  if (value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'value')) {
    return value.value;
  }
  return value;
};

const MetricTile = ({ icon, label, value, detail, color = 'primary' }) => (
  <Paper
    variant="outlined"
    sx={{
      p: 1.5,
      height: '100%',
      display: 'flex',
      gap: 1.25,
      alignItems: 'flex-start',
      minHeight: 104,
    }}
  >
    <Box sx={{ color: `${color}.main`, pt: 0.25 }}>
      {icon}
    </Box>
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase' }}>
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{
          fontFamily: 'monospace',
          fontSize: { xs: '1rem', sm: '1.1rem' },
          lineHeight: 1.25,
          overflowWrap: 'anywhere',
          color: value === EMPTY_VALUE ? 'text.secondary' : 'text.primary',
        }}
      >
        {value}
      </Typography>
      {detail && (
        <Typography variant="caption" color="text.secondary">
          {detail}
        </Typography>
      )}
    </Box>
  </Paper>
);

const TrackerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [pollingStatus, setPollingStatus] = useState('idle');
  const [fetchError, setFetchError] = useState(null);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const { schema, loading: schemaLoading, error: schemaError } = useTrackerSchema();
  const { currentStatus, loading: statusLoading, error: statusError } = useCurrentTrackerStatus();
  const { output, error: outputError } = useTrackerOutput();

  const fetchTrackerData = useCallback(async () => {
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    try {
      setPollingStatus('idle');
      const response = await fetchTrackingTelemetrySnapshot();

      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return;
      }

      if (response.status === 200) {
        const normalizedTrackerData = normalizeTrackingTelemetry(response.data || {});
        setTrackerData((prevData) => appendBounded(prevData, normalizedTrackerData));
        setRawData((prevData) => appendBoundedRawData(prevData, {
          type: 'tracking_telemetry',
          data: response.data || {},
          normalized: normalizedTrackerData,
        }));
        setFetchError(null);
        setPollingStatus('success');
      }
    } catch (error) {
      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return;
      }
      setFetchError(error);
      setPollingStatus('error');
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchTrackerData();
    const interval = setInterval(fetchTrackerData, POLLING_RATE);

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(interval);
    };
  }, [fetchTrackerData]);

  const latestTrackerData = trackerData[trackerData.length - 1] || {};
  const latestFields = latestTrackerData.fields || {};
  const currentFields = currentStatus?.fields || {};
  const center = latestTrackerData.center || fieldValue(currentFields, 'position_2d');
  const bbox = latestTrackerData.bounding_box || fieldValue(currentFields, 'normalized_bbox') || fieldValue(currentFields, 'bbox');
  const confidence = fieldValue(currentFields, 'confidence') ?? fieldValue(latestFields, 'confidence');
  const statusText = currentStatus?.status || latestTrackerData.status || latestTrackerData.consumer_guidance || 'checking';
  const timestamp = latestTrackerData.timestamp || currentStatus?.timestamp;

  const hasTelemetry = trackerData.length > 0;
  const topLevelError = fetchError || schemaError || statusError || outputError;

  return (
    <Container maxWidth="xl" sx={{ py: { xs: 1.5, md: 2 }, px: { xs: 1, sm: 2, md: 3 } }}>
      <Stack spacing={2}>
        <Box
          sx={{
            display: 'flex',
            alignItems: { xs: 'flex-start', sm: 'center' },
            justifyContent: 'space-between',
            flexDirection: { xs: 'column', sm: 'row' },
            gap: 1,
          }}
        >
          <Box>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              Tracker
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Target state, tracker health, and bounded diagnostics.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={formatLabel(statusText)}
              color={currentStatus?.active_tracking ? 'success' : hasTelemetry ? 'info' : 'default'}
              size="small"
            />
            <PollingStatusIndicator status={pollingStatus} />
          </Stack>
        </Box>

        {topLevelError && (
          <Alert severity={fetchError ? 'warning' : 'error'}>
            {fetchError ? 'Tracker telemetry polling is degraded.' : 'Tracker metadata is unavailable.'}
          </Alert>
        )}

        <Grid container rowSpacing={2} columnSpacing={{ xs: 0, sm: 2 }}>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<Sensors fontSize="small" />}
              label="Runtime"
              value={formatLabel(statusText) || EMPTY_VALUE}
              detail={currentStatus?.tracker_type || latestTrackerData.tracker_type || 'Tracker'}
              color={currentStatus?.active_tracking ? 'success' : 'info'}
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<GpsFixed fontSize="small" />}
              label="Target Center"
              value={formatOperatorValue(center, { fieldType: 'position_2d' })}
              detail="Normalized image coordinates"
              color="primary"
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<CropFree fontSize="small" />}
              label="Bounding Box"
              value={formatOperatorValue(bbox, { fieldType: 'bbox' })}
              detail="X, Y, W, H"
              color="secondary"
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<Timeline fontSize="small" />}
              label="Sample Age"
              value={formatAgeSeconds(timestamp)}
              detail={confidence !== undefined ? `Confidence ${formatOperatorValue(confidence, { fieldType: 'confidence' })}` : 'Latest telemetry sample'}
              color="warning"
            />
          </Grid>
        </Grid>

        {!hasTelemetry && (
          <Paper variant="outlined" sx={{ p: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <CircularProgress size={22} />
            <Typography variant="body2" color="text.secondary">
              Waiting for tracker telemetry.
            </Typography>
          </Paper>
        )}

        <Grid container rowSpacing={2} columnSpacing={{ xs: 0, sm: 2 }}>
          <Grid item xs={12} lg={5}>
            <TrackerDataDisplay
              currentStatus={currentStatus}
              trackerData={output}
              schema={schema}
              loading={statusLoading || schemaLoading}
              error={statusError || schemaError}
              showSchema={false}
              compact={false}
            />
          </Grid>
          <Grid item xs={12} lg={7}>
            <ScopePlot title="Target Geometry" trackerData={trackerData} />
          </Grid>
        </Grid>

        <Accordion defaultExpanded={false}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="subtitle1" fontWeight={700}>
              Trend Charts
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container rowSpacing={2} columnSpacing={{ xs: 0, sm: 2 }}>
              <Grid item xs={12} md={6}>
                <StaticPlot title="Center X" data={trackerData} dataKey="center.0" />
              </Grid>
              <Grid item xs={12} md={6}>
                <StaticPlot title="Center Y" data={trackerData} dataKey="center.1" />
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>

        <Accordion expanded={showRawData} onChange={() => setShowRawData((previous) => !previous)}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <Typography variant="subtitle1" fontWeight={700}>
                Diagnostics
              </Typography>
              <Chip label={`${rawData.length} samples`} size="small" variant="outlined" />
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Button size="small" variant="outlined" onClick={() => setRawData([])} disabled={rawData.length === 0}>
              Clear Samples
            </Button>
            <RawDataLog rawData={rawData} title="Tracker Diagnostics Payloads" />
          </AccordionDetails>
        </Accordion>
      </Stack>
    </Container>
  );
};

export default TrackerPage;
