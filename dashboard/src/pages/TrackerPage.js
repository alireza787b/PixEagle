import React, { useCallback, useState } from 'react';
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
import OperatorMetricStrip from '../components/OperatorMetricStrip';
import { useTrackerSchema, useCurrentTrackerStatus, useTrackerOutput } from '../hooks/useTrackerSchema';
import {
  buildNoCacheRequestConfig,
  classifyTrackerPollingStatus,
  getPollingRequestTimeoutMs,
  isMissingTrackingTelemetryRoute,
  normalizeTrackingTelemetry,
  resolveTrackerStatusPresentation,
  usePollingSampleStatus,
  useSerialPolling,
} from '../hooks/useStatuses';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import {
  EMPTY_VALUE,
  formatAgeSeconds,
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

export const appendMeasuredTrackingTelemetry = (previousData, sample) => {
  const timestamp = sample?.timestamp;
  const hasGeometry = Boolean(sample?.center || sample?.bounding_box);
  if (
    sample?.data_is_stale === true
    || !Number.isFinite(timestamp)
    || !hasGeometry
  ) {
    return previousData;
  }
  const previousTimestamp = previousData[previousData.length - 1]?.timestamp;
  if (previousTimestamp === timestamp) {
    return previousData;
  }
  return appendBounded(previousData, sample);
};

const fetchTrackingTelemetrySnapshot = async (requestConfig) => {
  try {
    return await axios.get(endpoints.trackingTelemetry, requestConfig);
  } catch (trackingTelemetryError) {
    if (!isMissingTrackingTelemetryRoute(trackingTelemetryError)) {
      throw trackingTelemetryError;
    }
    return axios.get(endpoints.trackerData, requestConfig);
  }
};

const fieldValue = (fields, fieldName) => {
  const value = fields?.[fieldName];
  if (value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'value')) {
    return value.value;
  }
  return value;
};

const TrackerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [latestTrackerData, setLatestTrackerData] = useState(null);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const {
    status: pollingStatus,
    markSample,
    markUnavailable,
  } = usePollingSampleStatus(POLLING_RATE);

  const { schema, loading: schemaLoading, error: schemaError } = useTrackerSchema();
  const { currentStatus, loading: statusLoading, error: statusError } = useCurrentTrackerStatus();
  const { output, error: outputError } = useTrackerOutput();

  const fetchTrackerData = useCallback(async (_options, { isCurrent }) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(POLLING_RATE),
    });
    try {
      const response = await fetchTrackingTelemetrySnapshot(requestConfig);
      if (!isCurrent()) {
        return null;
      }

      if (response.status !== 200) {
        throw new Error(`Tracker telemetry request returned HTTP ${response.status}.`);
      }

      const normalizedTrackerData = normalizeTrackingTelemetry(response.data || {});
      setLatestTrackerData(normalizedTrackerData);
      setTrackerData((prevData) => (
        appendMeasuredTrackingTelemetry(prevData, normalizedTrackerData)
      ));
      setRawData((prevData) => appendBoundedRawData(prevData, {
        type: 'tracking_telemetry',
        data: response.data || {},
        normalized: normalizedTrackerData,
      }));
      setFetchError(null);
      markSample(
        classifyTrackerPollingStatus(normalizedTrackerData),
        normalizedTrackerData.timestamp,
      );
      return response;
    } catch (error) {
      if (!isCurrent()) {
        return null;
      }
      setFetchError(error);
      markUnavailable();
      return null;
    }
  }, [markSample, markUnavailable]);

  useSerialPolling(fetchTrackerData, POLLING_RATE);

  const latestTelemetry = latestTrackerData || {};
  const latestFields = latestTelemetry.fields || {};
  const currentFields = currentStatus?.fields || {};
  const center = latestTelemetry.center || fieldValue(currentFields, 'position_2d');
  const bbox = latestTelemetry.bounding_box || fieldValue(currentFields, 'normalized_bbox') || fieldValue(currentFields, 'bbox');
  const confidence = fieldValue(currentFields, 'confidence') ?? fieldValue(latestFields, 'confidence');
  const timestamp = latestTelemetry.timestamp || currentStatus?.timestamp;

  const hasTelemetry = latestTrackerData !== null;
  const trackerStatus = resolveTrackerStatusPresentation(
    hasTelemetry ? latestTelemetry : currentStatus,
    pollingStatus,
  );
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
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={trackerStatus.chipLabel}
              color={trackerStatus.color}
              size="small"
            />
            <PollingStatusIndicator status={pollingStatus} />
          </Stack>
        </Box>

        {topLevelError && (
          <Alert severity="error">
            {fetchError ? 'Tracker telemetry is unavailable.' : 'Tracker metadata is unavailable.'}
          </Alert>
        )}

        <OperatorMetricStrip
          items={[
            {
              icon: <Sensors fontSize="small" />,
              label: 'Runtime',
              value: trackerStatus.label || EMPTY_VALUE,
              detail: currentStatus?.tracker_type || latestTelemetry.tracker_type || 'Tracker',
              color: trackerStatus.color === 'default' ? 'info' : trackerStatus.color,
              muted: trackerStatus.guidance === 'pending',
            },
            {
              icon: <GpsFixed fontSize="small" />,
              label: 'Target Center',
              value: formatOperatorValue(center, { fieldType: 'position_2d' }),
              detail: 'Normalized X, Y',
              color: 'primary',
              muted: !center,
            },
            {
              icon: <CropFree fontSize="small" />,
              label: 'Bounding Box',
              value: formatOperatorValue(bbox, { fieldType: 'bbox' }),
              detail: 'X, Y, W, H',
              color: 'secondary',
              muted: !bbox,
            },
            {
              icon: <Timeline fontSize="small" />,
              label: 'Sample Age',
              value: formatAgeSeconds(timestamp),
              detail: confidence !== undefined
                ? `Confidence ${formatOperatorValue(confidence, { fieldType: 'confidence' })}`
                : 'Latest sample',
              color: 'warning',
              muted: !timestamp,
            },
          ]}
        />

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
