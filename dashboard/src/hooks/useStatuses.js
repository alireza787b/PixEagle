//dashboard/src/hooks/useStatuses.js
import { useState, useEffect, useCallback, useRef } from 'react';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { getTrackerRuntimeState } from '../utils/trackerRuntimeState';

const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

export const buildNoCacheRequestConfig = ({ timeoutMs } = {}) => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
  ...(Number.isFinite(timeoutMs) && timeoutMs > 0 ? { timeout: timeoutMs } : {}),
});

export const normalizeTelemetryTimestamp = (timestamp) => {
  if (typeof timestamp === 'number' && Number.isFinite(timestamp)) {
    const timestampMs = Math.abs(timestamp) < 1000000000000
      ? timestamp * 1000
      : timestamp;
    return new Date(timestampMs).toISOString();
  }
  return timestamp;
};

const coerceFieldMap = (value) => (
  value && typeof value === 'object' && !Array.isArray(value) ? value : {}
);

const firstArrayValue = (...values) => {
  const arrayValue = values.find((value) => Array.isArray(value));
  return arrayValue || null;
};

const DEFAULT_POLLING_INTERVAL_MS = 2000;
const POLLING_STATUS_VALUES = new Set([
  'connecting',
  'active',
  'inactive',
  'stale',
  'degraded',
  'unavailable',
]);

const normalizedPollingInterval = (interval) => (
  Number.isFinite(interval) && interval > 0 ? interval : DEFAULT_POLLING_INTERVAL_MS
);

export const getPollingFreshnessDeadlines = (interval = DEFAULT_POLLING_INTERVAL_MS) => {
  const normalizedInterval = normalizedPollingInterval(interval);
  return {
    staleAfterMs: Math.max(normalizedInterval * 3, 1500),
    unavailableAfterMs: Math.max(normalizedInterval * 6, 3000),
  };
};

export const getPollingRequestTimeoutMs = (interval = DEFAULT_POLLING_INTERVAL_MS) => (
  Math.max(normalizedPollingInterval(interval) * 5, 2500)
);

const normalizedPollingStatus = (status) => (
  POLLING_STATUS_VALUES.has(status) ? status : 'unavailable'
);

const timestampToMilliseconds = (timestamp) => {
  if (typeof timestamp === 'number' && Number.isFinite(timestamp)) {
    return Math.abs(timestamp) < 1000000000000 ? timestamp * 1000 : timestamp;
  }
  if (typeof timestamp === 'string' && timestamp.trim()) {
    const parsed = Date.parse(timestamp);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

export const classifyTrackerPollingStatus = (sample) => {
  if (!sample || typeof sample !== 'object') {
    return 'unavailable';
  }

  const status = String(sample.status || '').toLowerCase();
  const guidance = String(sample.consumer_guidance || '').toLowerCase();
  if (status === 'unavailable' || guidance === 'unavailable') {
    return 'unavailable';
  }
  if (sample.data_is_stale === true || status === 'stale_output' || guidance === 'stale') {
    return 'stale';
  }
  if (status === 'not_usable' || guidance === 'not_usable') {
    return 'degraded';
  }
  if (
    status === 'no_output'
    || status === 'visible_output'
    || guidance === 'no_output'
    || guidance === 'diagnostic_only'
  ) {
    return 'inactive';
  }
  if (
    status === 'active_usable'
    || sample.active_tracking === true
    || sample.tracking_active === true
    || sample.tracker_started === true
  ) {
    return 'active';
  }
  return 'inactive';
};

export const classifyFollowerPollingStatus = (sample) => {
  if (!sample || typeof sample !== 'object') {
    return 'unavailable';
  }

  const status = String(sample.status || '').toLowerCase();
  const guidance = String(sample.consumer_guidance || '').toLowerCase();
  if (status === 'unavailable' || guidance === 'unavailable') {
    return 'unavailable';
  }
  if (status === 'degraded' || guidance === 'operator_attention') {
    return 'degraded';
  }
  if (
    status === 'inactive'
    || guidance === 'inactive'
    || sample.following_active === false
  ) {
    return 'inactive';
  }
  if (status === 'active' || guidance === 'following_active' || sample.following_active === true) {
    return 'active';
  }
  return 'unavailable';
};

export const usePollingSampleStatus = (interval = DEFAULT_POLLING_INTERVAL_MS) => {
  const [status, setStatus] = useState('connecting');
  const staleTimerRef = useRef(null);
  const unavailableTimerRef = useRef(null);
  const { staleAfterMs, unavailableAfterMs } = getPollingFreshnessDeadlines(interval);

  const clearFreshnessTimers = useCallback(() => {
    clearTimeout(staleTimerRef.current);
    clearTimeout(unavailableTimerRef.current);
    staleTimerRef.current = null;
    unavailableTimerRef.current = null;
  }, []);

  const markSample = useCallback((sampleStatus, timestamp = null) => {
    const now = Date.now();
    const timestampMs = timestampToMilliseconds(timestamp);
    const sampleAgeMs = timestampMs === null
      ? 0
      : Math.max(0, now - Math.min(timestampMs, now));
    let nextStatus = normalizedPollingStatus(sampleStatus);

    if (sampleAgeMs >= unavailableAfterMs) {
      nextStatus = 'unavailable';
    } else if (sampleAgeMs >= staleAfterMs && nextStatus !== 'unavailable') {
      nextStatus = 'stale';
    }

    clearFreshnessTimers();
    setStatus(nextStatus);

    if (nextStatus !== 'unavailable' && nextStatus !== 'stale') {
      staleTimerRef.current = setTimeout(() => {
        setStatus((currentStatus) => (
          currentStatus === 'unavailable' ? currentStatus : 'stale'
        ));
      }, staleAfterMs - sampleAgeMs);
    }
    if (nextStatus === 'unavailable') {
      return;
    }
    unavailableTimerRef.current = setTimeout(() => {
      setStatus('unavailable');
    }, unavailableAfterMs - sampleAgeMs);
  }, [clearFreshnessTimers, staleAfterMs, unavailableAfterMs]);

  const markUnavailable = useCallback(() => {
    clearFreshnessTimers();
    setStatus('unavailable');
  }, [clearFreshnessTimers]);

  useEffect(() => {
    setStatus('connecting');
    unavailableTimerRef.current = setTimeout(() => {
      setStatus('unavailable');
    }, unavailableAfterMs);

    return clearFreshnessTimers;
  }, [clearFreshnessTimers, unavailableAfterMs]);

  return {
    status,
    markSample,
    markUnavailable,
  };
};

export const useSerialPolling = (poll, interval = DEFAULT_POLLING_INTERVAL_MS) => {
  const pollRef = useRef(poll);
  const timerRef = useRef(null);
  const inFlightRef = useRef(null);
  const activeRef = useRef(false);
  const generationRef = useRef(0);
  const normalizedInterval = normalizedPollingInterval(interval);
  pollRef.current = poll;

  const refresh = useCallback((options = {}) => {
    if (!activeRef.current) {
      return Promise.resolve(null);
    }
    if (inFlightRef.current) {
      return inFlightRef.current;
    }

    const isCurrent = () => activeRef.current;
    let request;
    request = Promise.resolve()
      .then(() => pollRef.current(options, { isCurrent }))
      .finally(() => {
        if (inFlightRef.current === request) {
          inFlightRef.current = null;
        }
      });
    inFlightRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    activeRef.current = true;
    let firstRequest = true;

    const pollThenSchedule = async () => {
      try {
        await refresh({ suppressErrors: !firstRequest });
      } catch {
        // Poll callbacks normally own error reporting; keep the scheduler alive if one escapes.
      }
      firstRequest = false;

      if (generationRef.current === generation) {
        timerRef.current = setTimeout(pollThenSchedule, normalizedInterval);
      }
    };

    pollThenSchedule();

    return () => {
      if (generationRef.current === generation) {
        activeRef.current = false;
        generationRef.current = generation + 1;
      }
      clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [normalizedInterval, refresh]);

  return refresh;
};

export const useTrackerStatus = (interval = 2000) => {
  const [trackerStatus, setTrackerStatus] = useState(() => normalizeTrackerStatus(null, { pending: true }));
  const fetchTrackerStatus = useCallback(async ({ suppressErrors = false } = {}, { isCurrent }) => {
    try {
      const response = await axios.get(
        endpoints.trackerRuntimeStatus,
        buildNoCacheRequestConfig({ timeoutMs: getPollingRequestTimeoutMs(interval) }),
      );
      if (!isCurrent()) {
        return null;
      }
      const normalized = normalizeTrackerStatus(response.data);
      setTrackerStatus(normalized);
      return normalized;
    } catch (error) {
      if (!isCurrent()) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching tracker data:', error);
      }
      setTrackerStatus(normalizeTrackerStatus(null, { error }));
      return null;
    }
  }, [interval]);

  useSerialPolling(fetchTrackerStatus, interval);

  return trackerStatus;
};

export const normalizeCircuitBreakerActive = (status) => (
  status?.available === true && typeof status?.active === 'boolean'
    ? status.active
    : undefined
);

export const useCircuitBreakerStatus = (interval = 2000) => {
  const [active, setActive] = useState(undefined);
  const fetchCircuitBreakerStatus = useCallback(async (
    { suppressErrors = false } = {},
    { isCurrent },
  ) => {
    try {
      const response = await axios.get(
        endpoints.circuitBreakerStatus,
        buildNoCacheRequestConfig({
          timeoutMs: getPollingRequestTimeoutMs(interval),
        }),
      );
      if (!isCurrent()) return null;
      const normalized = normalizeCircuitBreakerActive(response.data);
      setActive(normalized);
      return normalized;
    } catch (error) {
      if (!isCurrent()) return null;
      if (!suppressErrors) {
        console.error('Error fetching circuit-breaker status:', error);
      }
      setActive(undefined);
      return null;
    }
  }, [interval]);

  const refresh = useSerialPolling(fetchCircuitBreakerStatus, interval);
  return { active, refresh };
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
  const followingReadiness = status?.following_readiness;
  const followingReadinessKnown = Boolean(
    followingReadiness
    && typeof followingReadiness === 'object'
    && typeof followingReadiness.usable_for_following === 'boolean'
  );
  const usableForFollowing = followingReadinessKnown
    ? followingReadiness.usable_for_following
    : runtimeState.usableForFollowing;

  return {
    raw: status || {},
    guidance: runtimeState.state,
    ...descriptor,
    detail: runtimeState.message,
    isTracking: runtimeState.activeTracking,
    activeTracking: runtimeState.activeTracking,
    hasOutput: runtimeState.hasOutput,
    usableForFollowing,
    followingReadinessKnown,
    followDisabledReason: usableForFollowing
      ? null
      : (followingReadiness?.reason || runtimeState.message),
    dataIsStale: runtimeState.dataIsStale,
    followLabel: usableForFollowing ? 'Follower Usable' : 'Not For Follow',
    followColor: usableForFollowing ? 'success' : (runtimeState.hasOutput ? 'warning' : 'default'),
    trackerType: status?.tracker_type || status?.configured_tracker || null,
    dataType: status?.data_type || null,
    timestamp: status?.timestamp || null,
    error: null,
  };
};

const FOLLOWER_GUIDANCE = {
  active: {
    label: 'Active',
    chipLabel: 'Following: Active',
    color: 'success',
    detail: 'Following is active.',
  },
  inactive: {
    label: 'Inactive',
    chipLabel: 'Following: Inactive',
    color: 'default',
    detail: 'Following is inactive.',
  },
  degraded: {
    label: 'Degraded',
    chipLabel: 'Following: Degraded',
    color: 'warning',
    detail: 'Following needs operator attention.',
  },
  stale: {
    label: 'Stale',
    chipLabel: 'Following: Stale',
    color: 'warning',
    detail: 'The latest following status sample is stale.',
  },
  connecting: {
    label: 'Checking',
    chipLabel: 'Following: Checking',
    color: 'info',
    detail: 'Waiting for the first following status sample.',
  },
  unavailable: {
    label: 'Unavailable',
    chipLabel: 'Following: Unavailable',
    color: 'error',
    detail: 'Following status is unavailable.',
  },
};

export const normalizeFollowerStatus = (
  status,
  { pending = false, error = null, sampleStatus = 'fresh' } = {},
) => {
  let state = 'inactive';

  if (error || sampleStatus === 'unavailable' || status?.status === 'unavailable') {
    state = 'unavailable';
  } else if (pending || sampleStatus === 'connecting') {
    state = 'connecting';
  } else if (sampleStatus === 'stale') {
    state = 'stale';
  } else if (status) {
    state = classifyFollowerPollingStatus(status);
  }

  const descriptor = FOLLOWER_GUIDANCE[state];
  return {
    raw: status || null,
    state,
    ...descriptor,
    detail: error?.message || status?.reason || descriptor.detail,
    followingActive: state === 'active' && Boolean(status?.following_active),
    reportedFollowingActive: Boolean(status?.following_active),
    healthIssues: Array.isArray(status?.health_issues) ? status.health_issues : [],
    error,
  };
};

export const resolveTrackerStatusPresentation = (status, sampleStatus = 'fresh') => {
  if (sampleStatus === 'connecting') {
    return normalizeTrackerStatus(null, { pending: true });
  }
  if (sampleStatus === 'unavailable') {
    return normalizeTrackerStatus(null, {
      error: new Error('Tracker telemetry sample is unavailable.'),
    });
  }
  if (sampleStatus === 'stale') {
    const normalized = normalizeTrackerStatus(status || {});
    return {
      ...normalized,
      guidance: 'stale_output',
      label: 'Stale Output',
      chipLabel: 'Tracking: Stale',
      navLabel: 'Stale',
      color: 'warning',
      detail: 'The latest tracker telemetry sample is stale.',
      isTracking: false,
      activeTracking: false,
      usableForFollowing: false,
      dataIsStale: true,
    };
  }
  return normalizeTrackerStatus(status || {});
};

const readFollowingActive = (data) => {
  if (data?.following_active === true) {
    return true;
  }
  if (classifyFollowerPollingStatus(data) === 'inactive') {
    return false;
  }
  return undefined;
};

const isMissingFollowingStatusRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const isMissingFollowingTelemetryRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const isMissingTrackingTelemetryRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const isMissingStreamingMediaHealthRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const normalizeTrackingTelemetry = (data) => {
  if (!data) {
    return {};
  }

  const explicitFields = coerceFieldMap(data.fields);
  const legacyTrackerData = coerceFieldMap(data.tracker_data);
  const fields = Object.keys(explicitFields).length > 0 ? explicitFields : legacyTrackerData;
  const center = firstArrayValue(
    data.center,
    fields.position_2d,
    fields.center,
    Array.isArray(fields.position_3d) ? fields.position_3d.slice(0, 2) : null,
  );
  const boundingBox = firstArrayValue(
    data.bounding_box,
    fields.normalized_bbox,
  );
  const activeTracking = Boolean(
    data.active_tracking ?? data.tracking_active ?? data.tracker_started
  );

  return {
    ...fields,
    ...data,
    fields,
    tracker_data: Object.keys(legacyTrackerData).length > 0 ? legacyTrackerData : fields,
    center,
    bounding_box: boundingBox,
    timestamp: normalizeTelemetryTimestamp(
      fields.last_measurement_timestamp ?? fields.timestamp ?? data.timestamp
    ),
    observed_at: normalizeTelemetryTimestamp(data.observed_at),
    active_tracking: activeTracking,
    tracking_active: activeTracking,
    tracker_started: Boolean(data.tracker_started ?? activeTracking),
    has_output: Boolean(data.has_output ?? fields.has_output ?? center ?? boundingBox),
    usable_for_following: Boolean(data.usable_for_following ?? fields.usable_for_following),
    data_is_stale: Boolean(data.data_is_stale ?? fields.data_is_stale),
  };
};

export const useFollowerStatus = (interval = 2000) => {
  const [isFollowing, setIsFollowing] = useState(undefined);
  const fetchFollowerStatus = useCallback(async ({ suppressErrors = false } = {}, { isCurrent }) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(interval),
    });
    try {
      let response;
      try {
        response = await axios.get(endpoints.followingStatus, requestConfig);
      } catch (followingStatusError) {
        if (!isMissingFollowingStatusRoute(followingStatusError)) {
          throw followingStatusError;
        }
        response = await axios.get(endpoints.followerData, requestConfig);
      }

      if (!isCurrent()) {
        return null;
      }
      const nextState = readFollowingActive(response.data || {});
      setIsFollowing(nextState);
      return nextState;
    } catch (error) {
      if (!isCurrent()) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching follower data:', error);
      }
      setIsFollowing(undefined);
      return null;
    }
  }, [interval]);

  useSerialPolling(fetchFollowerStatus, interval);

  return isFollowing;
};

export const normalizeFollowingTelemetry = (data) => {
  if (!data) {
    return {};
  }

  const explicitFields = coerceFieldMap(data.fields);
  const setpointFields = coerceFieldMap(data.setpoints);
  const fields = Object.keys(explicitFields).length > 0 ? explicitFields : setpointFields;
  const normalizedTimestamp = normalizeTelemetryTimestamp(data.timestamp);
  const legacyVelocityAliases = {
    ...(data.vel_x === undefined && fields.vel_body_fwd !== undefined
      ? { vel_x: fields.vel_body_fwd }
      : {}),
    ...(data.vel_y === undefined && fields.vel_body_right !== undefined
      ? { vel_y: fields.vel_body_right }
      : {}),
    ...(data.vel_z === undefined && fields.vel_body_down !== undefined
      ? { vel_z: fields.vel_body_down }
      : {}),
    ...(data.yaw_rate === undefined && fields.yawspeed_deg_s !== undefined
      ? { yaw_rate: fields.yawspeed_deg_s }
      : {}),
  };

  if (data.source !== 'following_telemetry') {
    return {
      ...fields,
      ...legacyVelocityAliases,
      ...data,
      fields,
      timestamp: normalizedTimestamp,
      execution_mode: String(
        data.execution_mode
          || data.command_publication?.execution_mode
          || 'PX4'
      ).toUpperCase(),
      command_preview: data.command_preview || {},
    };
  }

  const profile = data.profile || {};
  return {
    ...fields,
    ...legacyVelocityAliases,
    ...data,
    fields,
    timestamp: normalizedTimestamp,
    following_active: Boolean(data.following_active),
    profile_name: profile.display_name || profile.current_mode || profile.configured_mode || 'Unknown',
    manager_mode: profile.current_mode || profile.configured_mode || null,
    implementation_class: profile.follower_type || null,
    control_type: profile.control_type || data.control_type || null,
    available_fields: profile.available_fields || [],
    validation_status: Boolean(profile.profile_valid),
    circuit_breaker_active: data.circuit_breaker_active,
    target_loss_handler: data.target_loss_handler || null,
    safety_systems: data.safety_systems || null,
    performance: data.performance || null,
    execution_mode: String(
      data.execution_mode
        || data.command_publication?.execution_mode
        || 'PX4'
    ).toUpperCase(),
    commands_sent_to_px4: data.commands_sent_to_px4 === true,
    command_preview: data.command_preview || {},
  };
};

export const useFollowingTelemetry = (interval = 2000) => {
  const [followingTelemetry, setFollowingTelemetry] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchFollowingTelemetry = useCallback(async (
    { suppressErrors = false } = {},
    { isCurrent },
  ) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(interval),
    });
    try {
      let response;
      try {
        response = await axios.get(endpoints.followingTelemetry, requestConfig);
      } catch (followingTelemetryError) {
        if (!isMissingFollowingTelemetryRoute(followingTelemetryError)) {
          throw followingTelemetryError;
        }
        response = await axios.get(endpoints.followerData, requestConfig);
      }

      if (!isCurrent()) {
        return null;
      }
      const normalized = normalizeFollowingTelemetry(response.data || {});
      setFollowingTelemetry(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!isCurrent()) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching following telemetry:', fetchError);
      }
      setFollowingTelemetry({});
      setError(fetchError);
      return null;
    } finally {
      if (isCurrent()) {
        setLoading(false);
      }
    }
  }, [interval]);

  const refresh = useSerialPolling(fetchFollowingTelemetry, interval);

  return {
    followingTelemetry,
    refresh,
    loading,
    error,
  };
};

const STREAMING_GUIDANCE = {
  serving_media: {
    label: 'Active',
    chipLabel: 'Media: Active',
    color: 'success',
    detail: 'Backend media transports are serving local clients.',
  },
  idle: {
    label: 'Idle',
    chipLabel: 'Media: Idle',
    color: 'default',
    detail: 'No active backend media clients are connected.',
  },
  operator_attention: {
    label: 'Degraded',
    chipLabel: 'Media: Degraded',
    color: 'warning',
    detail: 'Backend media needs operator attention.',
  },
  unavailable: {
    label: 'Unavailable',
    chipLabel: 'Media: Unavailable',
    color: 'error',
    detail: 'Media-health status is unavailable.',
  },
  disabled: {
    label: 'Disabled',
    chipLabel: 'Media: Disabled',
    color: 'default',
    detail: 'Backend streaming is disabled in configuration.',
  },
  connecting: {
    label: 'Checking',
    chipLabel: 'Media: Checking',
    color: 'info',
    detail: 'Media-health request has not completed yet.',
  },
};

const STREAMING_TRANSPORT_LABELS = {
  http_mjpeg: 'HTTP MJPEG',
  websocket_jpeg: 'WebSocket',
  webrtc_signaling: 'WebRTC',
  gstreamer_udp_h264: 'GStreamer UDP',
};

const buildTransportMap = (transports) => (
  Array.isArray(transports)
    ? transports.reduce((acc, transport) => {
      if (transport?.name) {
        acc[transport.name] = transport;
      }
      return acc;
    }, {})
    : {}
);

const firstActiveTransportName = (transportsByName) => (
  [
    'websocket_jpeg',
    'webrtc_signaling',
    'http_mjpeg',
    'gstreamer_udp_h264',
  ].find((name) => transportsByName[name]?.status === 'active')
);

const qualityClientsFromWebSocketTransport = (transport) => {
  const clients = transport?.details?.clients;
  if (!Array.isArray(clients) || clients.length === 0) {
    return {};
  }
  return clients.reduce((acc, client, index) => {
    const id = client?.id || `websocket-${index + 1}`;
    acc[id] = {
      quality: client?.quality,
      frame_drops: client?.frame_drops,
      bandwidth_kbps: client?.bandwidth_kbps,
      last_frame_age_s: client?.last_frame_age_s,
    };
    return acc;
  }, {});
};

export const normalizeStreamingMediaHealth = (payload, { pending = false, error = null } = {}) => {
  if (pending) {
    const descriptor = STREAMING_GUIDANCE.connecting;
    return {
      raw: null,
      schemaVersion: 1,
      source: 'streaming_media',
      typed: true,
      status: 'connecting',
      consumerGuidance: 'connecting',
      ...descriptor,
      activeMethod: 'none',
      active_method: 'none',
      methodLabel: 'NONE',
      http_clients: 0,
      websocket_clients: 0,
      webrtc_clients: 0,
      totalClients: 0,
      adaptive_quality_enabled: false,
      quality_engine: {},
      config: {},
      transports: [],
      transportsByName: {},
      transportLabels: STREAMING_TRANSPORT_LABELS,
      frames: {
        source_available: false,
        latest_frame_stale: false,
        frames_sent: 0,
        frames_dropped: 0,
        total_bandwidth_mb: 0,
        cache_size: 0,
      },
      frames_sent: 0,
      frames_dropped: 0,
      total_bandwidth_mb: 0,
      cache_size: 0,
      healthIssues: [],
      claimBoundary: '',
      timestamp: null,
      error: null,
    };
  }

  if (error) {
    const descriptor = STREAMING_GUIDANCE.unavailable;
    return {
      ...normalizeStreamingMediaHealth(null, { pending: true }),
      raw: null,
      status: 'unavailable',
      consumerGuidance: 'unavailable',
      ...descriptor,
      error,
    };
  }

  const source = payload || {};
  const typed = source.source === 'streaming_media' || Array.isArray(source.transports);
  const transportsByName = buildTransportMap(source.transports);
  const frames = source.frames || {};
  const config = source.config || {};
  const activeTransportName = typed ? firstActiveTransportName(transportsByName) : null;
  const activeMethod = (
    typed
      ? (activeTransportName || 'none')
      : (source.active_method || source.activeMethod || 'none')
  );
  const httpClients = typed
    ? (transportsByName.http_mjpeg?.active_connections || 0)
    : (source.http_clients || 0);
  const websocketClients = typed
    ? (transportsByName.websocket_jpeg?.active_connections || 0)
    : (source.websocket_clients || 0);
  const webrtcClients = typed
    ? (transportsByName.webrtc_signaling?.active_connections || 0)
    : (source.webrtc_clients || 0);
  const totalClients = httpClients + websocketClients + webrtcClients;
  const normalizedQualityEngine = {
    ...(source.quality_engine || {}),
  };
  if (!normalizedQualityEngine.clients) {
    normalizedQualityEngine.clients = qualityClientsFromWebSocketTransport(
      transportsByName.websocket_jpeg
    );
  }
  const streamingEnabled = typed ? config.streaming_enabled !== false : source.enabled !== false;
  const sourceGuidance = source.consumer_guidance || (
    source.status === 'degraded'
      ? 'operator_attention'
      : totalClients > 0
        ? 'serving_media'
        : 'idle'
  );
  const consumerGuidance = streamingEnabled ? sourceGuidance : 'disabled';
  const descriptor = STREAMING_GUIDANCE[consumerGuidance] || STREAMING_GUIDANCE.unavailable;
  const normalizedFrames = {
    source_available: Boolean(frames.source_available),
    preferred_source: frames.preferred_source || null,
    latest_frame_id: frames.latest_frame_id ?? null,
    latest_frame_age_s: frames.latest_frame_age_s ?? null,
    latest_frame_stale: Boolean(frames.latest_frame_stale),
    stale_timeout_s: frames.stale_timeout_s ?? null,
    latest_frame_is_osd: frames.latest_frame_is_osd ?? null,
    publisher_client_count: frames.publisher_client_count || 0,
    frames_sent: frames.frames_sent ?? source.frames_sent ?? 0,
    frames_dropped: frames.frames_dropped ?? source.frames_dropped ?? 0,
    drop_ratio: frames.drop_ratio ?? source.drop_ratio ?? 0,
    total_bandwidth_mb: frames.total_bandwidth_mb ?? source.total_bandwidth_mb ?? 0,
    cache_size: frames.cache_size ?? source.cache_size ?? 0,
  };

  return {
    raw: source,
    schemaVersion: source.schema_version || 1,
    source: typed ? 'streaming_media' : 'legacy_streaming_status',
    typed,
    status: source.status || (totalClients > 0 ? 'active' : 'idle'),
    consumerGuidance,
    ...descriptor,
    activeMethod,
    active_method: activeMethod,
    methodLabel: String(activeMethod || 'none').toUpperCase(),
    http_clients: httpClients,
    websocket_clients: websocketClients,
    webrtc_clients: webrtcClients,
    totalClients,
    adaptive_quality_enabled: Boolean(
      config.adaptive_quality_enabled ?? source.adaptive_quality_enabled
    ),
    quality_engine: normalizedQualityEngine,
    config: {
      ...config,
      ...(source.config || {}),
      stream_width: config.stream_width ?? source.config?.stream_width,
      stream_height: config.stream_height ?? source.config?.stream_height,
      stream_fps: config.stream_fps ?? source.config?.stream_fps,
    },
    transports: Array.isArray(source.transports) ? source.transports : [],
    transportsByName,
    transportLabels: STREAMING_TRANSPORT_LABELS,
    frames: normalizedFrames,
    frames_sent: normalizedFrames.frames_sent,
    frames_dropped: normalizedFrames.frames_dropped,
    total_bandwidth_mb: normalizedFrames.total_bandwidth_mb,
    cache_size: normalizedFrames.cache_size,
    healthIssues: Array.isArray(source.health_issues) ? source.health_issues : [],
    claimBoundary: source.claim_boundary || '',
    timestamp: source.timestamp || null,
    error: null,
  };
};

export const useStreamingMediaHealth = (interval = 2000) => {
  const [streamingHealth, setStreamingHealth] = useState(null);
  const [streamingStatus, setStreamingStatus] = useState(() => (
    normalizeStreamingMediaHealth(null, { pending: true })
  ));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStreamingMediaHealth = useCallback(async (
    { suppressErrors = false } = {},
    { isCurrent },
  ) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(interval),
    });
    try {
      let response;
      try {
        response = await axios.get(endpoints.streamingMediaHealth, requestConfig);
      } catch (streamingMediaHealthError) {
        if (!isMissingStreamingMediaHealthRoute(streamingMediaHealthError)) {
          throw streamingMediaHealthError;
        }
        response = await axios.get(endpoints.streamingStatus, requestConfig);
      }

      if (!isCurrent()) {
        return null;
      }

      const raw = response.data || {};
      const normalized = normalizeStreamingMediaHealth(raw);
      setStreamingHealth(raw);
      setStreamingStatus(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!isCurrent()) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching streaming media health:', fetchError);
      }
      const unavailable = normalizeStreamingMediaHealth(null, { error: fetchError });
      setStreamingHealth(null);
      setStreamingStatus(unavailable);
      setError(fetchError);
      return null;
    } finally {
      if (isCurrent()) {
        setLoading(false);
      }
    }
  }, [interval]);

  const refresh = useSerialPolling(fetchStreamingMediaHealth, interval);

  return {
    streamingHealth,
    streamingStatus,
    refresh,
    loading,
    error,
  };
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

  const fetchTelemetryHealth = useCallback(async (
    { suppressErrors = false } = {},
    { isCurrent },
  ) => {
    try {
      const response = await axios.get(
        endpoints.telemetryHealth,
        buildNoCacheRequestConfig({ timeoutMs: getPollingRequestTimeoutMs(interval) }),
      );
      if (!isCurrent()) {
        return null;
      }
      const health = response.data || {};
      const normalized = normalizeTelemetryHealth(health);
      setTelemetryHealth(health);
      setTelemetryStatus(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!isCurrent()) {
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
      if (isCurrent()) {
        setLoading(false);
      }
    }
  }, [interval]);

  const refresh = useSerialPolling(fetchTelemetryHealth, interval);

  return {
    telemetryHealth,
    telemetryStatus,
    refresh,
    loading,
    error,
  };
};


const readSmartModeActive = (data) => {
  const value = data?.modes?.smart_mode_active ?? data?.smart_mode_active;
  return typeof value === 'boolean' ? value : undefined;
};

const readSmartModelName = (data) => {
  const value = (
    data?.subsystems?.smart_tracker_runtime?.model_name
    ?? data?.smart_tracker_runtime?.model_name
  );
  return typeof value === 'string' && value.trim() ? value.trim() : null;
};

const isMissingRuntimeStatusRoute = (fetchError) => (
  [404, 405, 501].includes(fetchError?.response?.status)
);

export const useSmartModeStatus = (interval = 2000) => {
  const [smartModeActive, setSmartModeActive] = useState(undefined);
  const [activeModelName, setActiveModelName] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchSmartModeStatus = useCallback(async (
    { suppressErrors = false } = {},
    { isCurrent },
  ) => {
    const requestConfig = buildNoCacheRequestConfig({
      timeoutMs: getPollingRequestTimeoutMs(interval),
    });
    try {
      let response;
      try {
        response = await axios.get(endpoints.runtimeStatus, requestConfig);
      } catch (runtimeStatusError) {
        if (!isMissingRuntimeStatusRoute(runtimeStatusError)) {
          throw runtimeStatusError;
        }
        response = await axios.get(endpoints.status, requestConfig);
      }

      if (!isCurrent()) {
        return null;
      }

      const nextState = readSmartModeActive(response.data || {});
      if (typeof nextState !== 'boolean') {
        throw new Error('Tracker mode is missing from the runtime status response');
      }
      setSmartModeActive(nextState);
      setActiveModelName(readSmartModelName(response.data || {}));
      setError(null);
      return nextState;
    } catch (fetchError) {
      if (!isCurrent()) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching smart mode status:', fetchError);
      }
      setSmartModeActive(undefined);
      setActiveModelName(null);
      setError(fetchError);
      return null;
    } finally {
      if (isCurrent()) {
        setLoading(false);
      }
    }
  }, [interval]);

  const refresh = useSerialPolling(fetchSmartModeStatus, interval);

  useEffect(() => {
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
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
    };
  }, [refresh]);

  return {
    smartModeActive,
    activeModelName,
    refresh,
    loading,
    error,
  };
};
