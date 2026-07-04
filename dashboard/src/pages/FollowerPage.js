// dashboard/src/pages/FollowerPage.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import { useFollowerSchema, useCurrentFollowerProfile } from '../hooks/useFollowerSchema';
import {
  buildNoCacheRequestConfig,
  isMissingFollowingTelemetryRoute,
  isMissingTrackingTelemetryRoute,
  normalizeFollowingTelemetry,
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
const MAX_TELEMETRY_HISTORY = 300;
const MAX_RAW_DATA_ENTRIES = 600;

const appendBounded = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_TELEMETRY_HISTORY)
);

const appendBoundedRawData = (previousData, ...newData) => (
  [...previousData, ...newData].slice(-MAX_RAW_DATA_ENTRIES)
);

const fetchFollowingTelemetrySnapshot = async () => {
  try {
    return await axios.get(endpoints.followingTelemetry, buildNoCacheRequestConfig());
  } catch (followingTelemetryError) {
    if (!isMissingFollowingTelemetryRoute(followingTelemetryError)) {
      throw followingTelemetryError;
    }
    return axios.get(endpoints.followerData, buildNoCacheRequestConfig());
  }
};

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

const FollowerPage = () => {
  const [trackerData, setTrackerData] = useState([]);
  const [followerData, setFollowerData] = useState([]);
  const [rawData, setRawData] = useState([]);
  const [showRawData, setShowRawData] = useState(false);
  const [pollingStatus, setPollingStatus] = useState('idle');
  const [fetchError, setFetchError] = useState(null);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const { schema, loading: schemaLoading, error: schemaError } = useFollowerSchema();
  const { currentProfile, loading: profileLoading, error: profileError } = useCurrentFollowerProfile();

  const fetchTelemetryData = useCallback(async () => {
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    try {
      const [trackerResponse, followerResponse] = await Promise.all([
        fetchTrackingTelemetrySnapshot(),
        fetchFollowingTelemetrySnapshot(),
      ]);

      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return;
      }
      
      if (trackerResponse.status === 200 && followerResponse.status === 200) {
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
    fetchTelemetryData();
    const interval = setInterval(fetchTelemetryData, POLLING_RATE);

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(interval);
    };
  }, [fetchTelemetryData]);

  const latestFollowerData = followerData[followerData.length - 1] || {};
  const latestTrackerData = trackerData[trackerData.length - 1] || {};
  const currentFieldValues = latestFollowerData.fields || {};
  const loading = schemaLoading || profileLoading;
  const profileName = currentProfile?.display_name || latestFollowerData.profile_name || latestFollowerData.manager_mode || 'Follower';
  const followingActive = Boolean(latestFollowerData.following_active);

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
            <Typography variant="body2" color="text.secondary">
              Command intent, target geometry, and bounded control diagnostics.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip
              label={followingActive ? 'Following Active' : 'Following Idle'}
              color={followingActive ? 'success' : 'default'}
              size="small"
            />
            <PollingStatusIndicator status={pollingStatus} />
          </Stack>
        </Box>

        {fetchError && (
          <Alert severity="warning">
            Follower telemetry polling is degraded.
          </Alert>
        )}

        <Grid container rowSpacing={2} columnSpacing={{ xs: 0, sm: 2 }}>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<Navigation fontSize="small" />}
              label="Profile"
              value={profileName}
              detail={formatLabel(currentProfile?.control_type || latestFollowerData.control_type)}
              color={followingActive ? 'success' : 'info'}
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<Speed fontSize="small" />}
              label="Forward"
              value={formatOperatorValue(currentFieldValues.vel_body_fwd ?? latestFollowerData.vel_x, { unit: 'm/s' })}
              detail="Body-frame forward command"
              color="primary"
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<GpsFixed fontSize="small" />}
              label="Target Center"
              value={formatOperatorValue(latestTrackerData.center, { fieldType: 'position_2d' })}
              detail="Tracker input to follower"
              color="secondary"
            />
          </Grid>
          <Grid item xs={12} sm={6} lg={3}>
            <MetricTile
              icon={<Timeline fontSize="small" />}
              label="Sample Age"
              value={formatAgeSeconds(latestFollowerData.timestamp)}
              detail={formatLabel(latestFollowerData.status || latestFollowerData.consumer_guidance)}
              color="warning"
            />
          </Grid>
        </Grid>

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
