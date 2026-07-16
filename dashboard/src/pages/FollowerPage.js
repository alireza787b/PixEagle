// dashboard/src/pages/FollowerPage.js
import React, { useState, useCallback } from 'react';
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
  ExpandMore,
  GpsFixed,
  Navigation,
  Speed,
  Timeline,
} from '@mui/icons-material';
import ScopePlot from '../components/ScopePlot';
import StaticPlot from '../components/StaticPlot';
import RawDataLog from '../components/RawDataLog';
import PollingStatusIndicator from '../components/PollingStatusIndicator';
import DynamicFieldDisplay from '../components/DynamicFieldDisplay';
import FollowerProfileSelector from '../components/FollowerProfileSelector';
import OperatorMetricStrip from '../components/OperatorMetricStrip';
import { useFollowerSchema, useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import {
  buildNoCacheRequestConfig,
  classifyFollowerPollingStatus,
  getPollingRequestTimeoutMs,
  isMissingFollowingTelemetryRoute,
  isMissingTrackingTelemetryRoute,
  normalizeFollowerStatus,
  normalizeFollowingTelemetry,
  normalizeTrackingTelemetry,
  usePollingSampleStatus,
  useSerialPolling,
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
const MAX_TELEMETRY_HISTORY = 300;
const MAX_RAW_DATA_ENTRIES = 600;

const appendBounded = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_TELEMETRY_HISTORY)
);

const appendBoundedRawData = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_RAW_DATA_ENTRIES)
);

const fetchFollowingTelemetrySnapshot = async (requestConfig) => {
  try {
    return await axios.get(endpoints.followingTelemetry, requestConfig);
  } catch (followingTelemetryError) {
    if (!isMissingFollowingTelemetryRoute(followingTelemetryError)) {
      throw followingTelemetryError;
    }
    return axios.get(endpoints.followerData, requestConfig);
  }
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

const FollowerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [followerData, setFollowerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [fetchError, setFetchError] = useState(null);
  const {
    status: pollingStatus,
    markSample,
    markUnavailable,
  } = usePollingSampleStatus(POLLING_RATE);

  const { schema, loading: schemaLoading, error: schemaError } = useFollowerSchema();
  const { currentProfile, loading: profileLoading, error: profileError } = useCurrentFollowerProfile();

  const fetchTelemetryData = useCallback(async (_options, { isCurrent }) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(POLLING_RATE),
    });
    try {
      const [trackerResult, followerResult] = await Promise.allSettled([
        fetchTrackingTelemetrySnapshot(requestConfig),
        fetchFollowingTelemetrySnapshot(requestConfig),
      ]);

      if (!isCurrent()) {
        return null;
      }

      if (trackerResult.status === 'rejected') {
        throw trackerResult.reason;
      }
      if (followerResult.status === 'rejected') {
        throw followerResult.reason;
      }

      const trackerResponse = trackerResult.value;
      const followerResponse = followerResult.value;
      if (trackerResponse.status !== 200 || followerResponse.status !== 200) {
        throw new Error(
          `Follower telemetry requests returned HTTP ${trackerResponse.status}/${followerResponse.status}.`,
        );
      }

      const normalizedTrackerData = normalizeTrackingTelemetry(trackerResponse.data || {});
      const normalizedFollowerData = normalizeFollowingTelemetry(followerResponse.data || {});
      setTrackerData((prevData) => appendBounded(prevData, normalizedTrackerData));
      setFollowerData((prevData) => appendBounded(prevData, normalizedFollowerData));
      setRawData((prevData) => appendBoundedRawData(
        prevData,
        {
          type: 'tracker',
          data: trackerResponse.data || {},
          normalized: normalizedTrackerData,
        },
        {
          type: 'follower',
          data: followerResponse.data || {},
          normalized: normalizedFollowerData,
        },
      ));
      setFetchError(null);
      markSample(
        classifyFollowerPollingStatus(normalizedFollowerData),
        normalizedFollowerData.timestamp,
      );
      return { trackerResponse, followerResponse };
    } catch (error) {
      if (!isCurrent()) {
        return null;
      }
      setFetchError(error);
      markUnavailable();
      return null;
    }
  }, [markSample, markUnavailable]);

  useSerialPolling(fetchTelemetryData, POLLING_RATE);

  const latestFollowerData = followerData[followerData.length - 1] || {};
  const latestTrackerData = trackerData[trackerData.length - 1] || {};
  const currentFieldValues = latestFollowerData.fields || {};
  const loading = schemaLoading || profileLoading;
  const profileName = currentProfile?.display_name || latestFollowerData.profile_name || latestFollowerData.manager_mode || 'Follower';
  const followerStatus = normalizeFollowerStatus(latestFollowerData, {
    pending: followerData.length === 0,
    error: fetchError,
    sampleStatus: pollingStatus,
  });

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 2 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 2 }}>
          Follower
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <CircularProgress size={24} />
          <Typography variant="body2" color="text.secondary">
            Loading follower schema and profile.
          </Typography>
        </Box>
      </Container>
    );
  }

  if (schemaError || profileError) {
    return (
      <Container maxWidth="xl" sx={{ py: 2 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 2 }}>
          Follower
        </Typography>
        <Alert severity="error">
          {schemaError || profileError}
        </Alert>
      </Container>
    );
  }

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
              Follower
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={followerStatus.chipLabel}
              color={followerStatus.color}
              size="small"
            />
            <PollingStatusIndicator status={pollingStatus} />
          </Stack>
        </Box>

        {(fetchError || followerStatus.state === 'degraded') && (
          <Alert severity={fetchError ? 'error' : 'warning'}>
            {fetchError
              ? 'Follower telemetry is unavailable.'
              : followerStatus.detail}
          </Alert>
        )}

        <OperatorMetricStrip
          items={[
            {
              icon: <Navigation fontSize="small" />,
              label: 'Profile',
              value: profileName,
              detail: formatLabel(currentProfile?.control_type || latestFollowerData.control_type),
              color: followerStatus.color === 'default' ? 'info' : followerStatus.color,
              muted: profileName === EMPTY_VALUE,
            },
            {
              icon: <Speed fontSize="small" />,
              label: 'Forward',
              value: formatOperatorValue(
                currentFieldValues.vel_body_fwd ?? latestFollowerData.vel_x,
                { unit: 'm/s' },
              ),
              detail: 'Body frame',
              color: 'primary',
            },
            {
              icon: <GpsFixed fontSize="small" />,
              label: 'Target Center',
              value: formatOperatorValue(latestTrackerData.center, { fieldType: 'position_2d' }),
              detail: 'Tracker input',
              color: 'secondary',
              muted: !latestTrackerData.center,
            },
            {
              icon: <Timeline fontSize="small" />,
              label: 'Sample Age',
              value: formatAgeSeconds(latestFollowerData.timestamp),
              detail: formatLabel(latestFollowerData.status || latestFollowerData.consumer_guidance),
              color: 'warning',
              muted: !latestFollowerData.timestamp,
            },
          ]}
        />

        <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 } }}>
          <FollowerProfileSelector />
        </Paper>

        <Box>
          <DynamicFieldDisplay
            schema={schema}
            currentProfile={currentProfile}
            fieldValues={currentFieldValues}
          />
        </Box>

        <ScopePlot title="Target And Command Geometry" trackerData={trackerData} followerData={followerData} />

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
              {currentProfile?.available_fields?.map((fieldName) => (
                <Grid item xs={12} md={6} lg={4} key={fieldName}>
                  <StaticPlot
                    title={formatLabel(fieldName)}
                    data={followerData}
                    dataKey={fieldName}
                  />
                </Grid>
              ))}
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
            <RawDataLog rawData={rawData} title="Follower Diagnostics Payloads" />
          </AccordionDetails>
        </Accordion>
      </Stack>
    </Container>
  );
};

export default FollowerPage;
