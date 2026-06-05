//dashboard/src/hooks/useStatuses.js
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';
import { getTrackerRuntimeState } from '../utils/trackerRuntimeState';

const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const buildNoCacheRequestConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
});

export const useTrackerStatus = (interval = 2000) => {
  const [trackerStatus, setTrackerStatus] = useState(() => normalizeTrackerStatus(null, { pending: true }));
  const latestTrackerRequestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    const fetchTrackerStatus = async () => {
      const requestId = latestTrackerRequestIdRef.current + 1;
      latestTrackerRequestIdRef.current = requestId;

      try {
        const response = await axios.get(endpoints.trackerRuntimeStatus, buildNoCacheRequestConfig());
        if (cancelled || requestId !== latestTrackerRequestIdRef.current) {
          return;
        }
        setTrackerStatus(normalizeTrackerStatus(response.data));
      } catch (error) {
        if (cancelled || requestId !== latestTrackerRequestIdRef.current) {
          return;
        }
        console.error('Error fetching tracker data:', error);
        console.log("URI Used is:", endpoints.trackerRuntimeStatus);
        setTrackerStatus(normalizeTrackerStatus(null, { error }));
      }
    };

    const intervalId = setInterval(fetchTrackerStatus, interval);
    fetchTrackerStatus(); // Initial call

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [interval]);

  return trackerStatus;
};

const TRACKER_GUIDANCE = {
  active_usable: {
    label: 'Active',
    chipLabel: 'Tracking: Active',
    navLabel: 'Tracking',
    color: 'success',
  },
  visible_output: {
    label: 'Output Visible',
    chipLabel: 'Tracking: Visible',
    navLabel: 'Visible',
    color: 'info',
  },
  stale_output: {
    label: 'Stale Output',
    chipLabel: 'Tracking: Stale',
    navLabel: 'Stale',
    color: 'warning',
  },
  not_usable: {
    label: 'Not Usable',
    chipLabel: 'Tracking: Not Usable',
    navLabel: 'Blocked',
    color: 'warning',
  },
  no_output: {
    label: 'No Output',
    chipLabel: 'Tracking: No Output',
    navLabel: 'Idle',
    color: 'default',
  },
  pending: {
    label: 'Checking',
    chipLabel: 'Tracking: Checking',
    navLabel: 'Checking',
    color: 'info',
  },
  unavailable: {
    label: 'Unavailable',
    chipLabel: 'Tracking: Unavailable',
    navLabel: 'Unavailable',
    color: 'error',
  },
};

export const normalizeTrackerStatus = (status, { pending = false, error = null } = {}) => {
  if (pending) {
    const descriptor = TRACKER_GUIDANCE.pending;
    return {
      raw: null,
      guidance: 'pending',
      ...descriptor,
      detail: 'Tracker status request has not completed yet.',
      isTracking: false,
      activeTracking: false,
      hasOutput: false,
      usableForFollowing: false,
      dataIsStale: false,
      error: null,
    };
  }

  if (error) {
    const descriptor = TRACKER_GUIDANCE.unavailable;
    return {
      raw: null,
      guidance: 'unavailable',
      ...descriptor,
      detail: error?.message || 'Tracker status request failed.',
      isTracking: false,
      activeTracking: false,
      hasOutput: false,
      usableForFollowing: false,
      dataIsStale: false,
      error,
    };
  }

  const runtimeState = getTrackerRuntimeState(status);
  const descriptor = TRACKER_GUIDANCE[runtimeState.state] || TRACKER_GUIDANCE.no_output;

  return {
    raw: status || {},
    guidance: runtimeState.state,
    ...descriptor,
    detail: runtimeState.message,
    isTracking: runtimeState.activeTracking,
    activeTracking: runtimeState.activeTracking,
    hasOutput: runtimeState.hasOutput,
    usableForFollowing: runtimeState.usableForFollowing,
    dataIsStale: runtimeState.dataIsStale,
    followLabel: runtimeState.followLabel,
    followColor: runtimeState.followColor,
    trackerType: status?.tracker_type || status?.configured_tracker || null,
    dataType: status?.data_type || null,
    timestamp: status?.timestamp || null,
    error: null,
  };
};

export const useFollowerStatus = (interval = 2000) => {
  const [isFollowing, setIsFollowing] = useState(false);

  useEffect(() => {
    const fetchFollowerStatus = async () => {
      try {
        const response = await axios.get(endpoints.followerData, buildNoCacheRequestConfig());
        const followerData = response.data;

        setIsFollowing(followerData.following_active);
      } catch (error) {
        console.error('Error fetching follower data:', error);
        setIsFollowing(false);
      }
    };

    const intervalId = setInterval(fetchFollowerStatus, interval);
    fetchFollowerStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return isFollowing;
};

const TELEMETRY_GUIDANCE = {
  usable: {
    label: 'Usable',
    chipLabel: 'Telemetry: Usable',
    color: 'success',
    detail: 'Latest request and cached payload are fresh',
  },
  degraded_latest_request_failed: {
    label: 'Degraded',
    chipLabel: 'Telemetry: Degraded',
    color: 'warning',
    detail: 'Latest request failed while cached payload is still fresh',
  },
  stale: {
    label: 'Stale',
    chipLabel: 'Telemetry: Stale',
    color: 'warning',
    detail: 'Last successful MAVLink2REST sample is stale',
  },
  unavailable: {
    label: 'Unavailable',
    chipLabel: 'Telemetry: Unavailable',
    color: 'error',
    detail: 'No usable MAVLink2REST telemetry sample is available',
  },
  disabled: {
    label: 'Disabled',
    chipLabel: 'Telemetry: Disabled',
    color: 'default',
    detail: 'MAVLink telemetry polling is disabled',
  },
  connecting: {
    label: 'Connecting',
    chipLabel: 'Telemetry: Connecting',
    color: 'info',
    detail: 'MAVLink telemetry polling has not completed a sample yet',
  },
};

const formatOptionalValue = (value) => {
  if (value === null || value === undefined || value === '') {
    return 'N/A';
  }
  return String(value);
};

const INITIAL_TELEMETRY_HEALTH = {
  enabled: true,
  status: 'connecting',
  consumer_guidance: 'connecting',
  transport: {
    latest_request_ok: false,
    latest_request_result: 'not_attempted',
  },
  request_freshness: {
    fresh: false,
  },
  payload: {
    has_payload: false,
    fresh: false,
  },
};

export const normalizeTelemetryHealth = (health) => {
  const hasHealth = Boolean(health);
  const source = health || {};
  const transport = source.transport || {};
  const freshness = source.request_freshness || {};
  const payload = source.payload || {};
  const guidance = source.consumer_guidance || 'unavailable';
  const descriptor = TELEMETRY_GUIDANCE[guidance] || TELEMETRY_GUIDANCE.unavailable;
  const disabled = source.enabled === false || source.status === 'disabled' || guidance === 'disabled';
  const latestRequestOk = Boolean(transport.latest_request_ok);
  const requestFresh = disabled ? false : Boolean(freshness.fresh);
  const payloadFresh = disabled ? false : Boolean(payload.fresh);
  const enabled = hasHealth ? !disabled : false;
  const usableForFollowing = (
    enabled
    && guidance === 'usable'
    && latestRequestOk
    && requestFresh
    && payloadFresh
  );

  return {
    raw: source,
    schemaVersion: source.schema_version || 1,
    source: source.source || 'mavlink2rest',
    enabled,
    status: source.status || 'disconnected',
    guidance,
    label: descriptor.label,
    chipLabel: descriptor.chipLabel,
    color: descriptor.color,
    detail: descriptor.detail,
    usableForFollowing,
    transport: {
      state: transport.state || 'unknown',
      latestRequestOk,
      latestRequestResult: transport.latest_request_result || 'not_attempted',
      latestRequestAgeS: transport.latest_request_age_s ?? null,
      validationTimeoutActive: Boolean(transport.validation_timeout_active),
      lastError: transport.last_error || null,
      endpoint: transport.endpoint || null,
    },
    requestFreshness: {
      fresh: requestFresh,
      lastSuccessAgeS: freshness.last_success_age_s ?? null,
      staleTimeoutS: freshness.stale_timeout_s ?? null,
      lastSuccessMonotonicAvailable: Boolean(freshness.last_success_monotonic_available),
    },
    payload: {
      hasPayload: Boolean(payload.has_payload),
      fresh: payloadFresh,
      sampleCount: payload.sample_count || 0,
      availableKeys: Array.isArray(payload.available_keys) ? payload.available_keys : [],
      flightModeRaw: payload.flight_mode ?? null,
      flightModeLabel: formatOptionalValue(payload.flight_mode),
      armStatusRaw: payload.arm_status ?? null,
      armStatusLabel: formatOptionalValue(payload.arm_status),
      payloadAgeS: payload.payload_age_s ?? null,
    },
    claimBoundary: source.claim_boundary || '',
    timestamp: source.timestamp || null,
  };
};

export const useTelemetryHealth = (interval = 2000) => {
  const [telemetryHealth, setTelemetryHealth] = useState(null);
  const [telemetryStatus, setTelemetryStatus] = useState(() => normalizeTelemetryHealth(INITIAL_TELEMETRY_HEALTH));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const refresh = useCallback(async ({ suppressErrors = false } = {}) => {
    const requestSequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestSequence;

    try {
      const response = await axios.get(endpoints.telemetryHealth, buildNoCacheRequestConfig());
      if (!mountedRef.current || requestSequence !== requestSequenceRef.current) {
        return null;
      }
      const health = response.data || {};
      const normalized = normalizeTelemetryHealth(health);
      setTelemetryHealth(health);
      setTelemetryStatus(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!mountedRef.current || requestSequence !== requestSequenceRef.current) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching telemetry health:', fetchError);
      }
      const unavailableHealth = {
        enabled: false,
        status: 'disconnected',
        consumer_guidance: 'unavailable',
        transport: {
          latest_request_ok: false,
          latest_request_result: 'failure',
          last_error: fetchError?.message || 'Telemetry health request failed',
        },
        request_freshness: { fresh: false },
        payload: { has_payload: false, fresh: false },
      };
      const unavailable = normalizeTelemetryHealth(unavailableHealth);
      setTelemetryHealth(unavailableHealth);
      setTelemetryStatus(unavailable);
      setError(fetchError);
      return null;
    } finally {
      if (mountedRef.current && requestSequence === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const intervalId = setInterval(() => {
      refresh({ suppressErrors: true });
    }, interval);

    refresh();

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(intervalId);
    };
  }, [interval, refresh]);

  return {
    telemetryHealth,
    telemetryStatus,
    refresh,
    loading,
    error,
  };
};


const readSmartModeActive = (data) => Boolean(
  data?.modes?.smart_mode_active ?? data?.smart_mode_active
);

const isMissingRuntimeStatusRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const useSmartModeStatus = (interval = 2000) => {
  const [smartModeActive, setSmartModeActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const refresh = useCallback(async ({ suppressErrors = false } = {}) => {
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    try {
      let response;
      try {
        response = await axios.get(endpoints.runtimeStatus, buildNoCacheRequestConfig());
      } catch (runtimeStatusError) {
        if (!isMissingRuntimeStatusRoute(runtimeStatusError)) {
          throw runtimeStatusError;
        }
        response = await axios.get(endpoints.status, buildNoCacheRequestConfig());
      }

      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return null;
      }

      const nextState = readSmartModeActive(response.data || {});
      setSmartModeActive(nextState);
      setError(null);
      return nextState;
    } catch (fetchError) {
      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching smart mode status:', fetchError);
      }
      setError(fetchError);
      // Keep previous UI state on transient errors rather than forcing false.
      return null;
    } finally {
      if (mountedRef.current && requestId === requestSequenceRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const intervalId = setInterval(() => {
      refresh({ suppressErrors: true });
    }, interval);

    refresh(); // Initial call

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        refresh({ suppressErrors: true });
      }
    };

    const handleWindowFocus = () => {
      refresh({ suppressErrors: true });
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleWindowFocus);
    }

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(intervalId);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
    };
  }, [interval, refresh]);

  return {
    smartModeActive,
    refresh,
    loading,
    error,
  };
};
