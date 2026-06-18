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

export const buildNoCacheRequestConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
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

const readFollowingActive = (data) => Boolean(data?.following_active);

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
    timestamp: normalizeTelemetryTimestamp(data.timestamp ?? fields.timestamp),
    active_tracking: activeTracking,
    tracking_active: activeTracking,
    tracker_started: Boolean(data.tracker_started ?? activeTracking),
    has_output: Boolean(data.has_output ?? fields.has_output ?? center ?? boundingBox),
    usable_for_following: Boolean(data.usable_for_following ?? fields.usable_for_following),
    data_is_stale: Boolean(data.data_is_stale ?? fields.data_is_stale),
  };
};

export const useFollowerStatus = (interval = 2000) => {
  const [isFollowing, setIsFollowing] = useState(false);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  useEffect(() => {
    const fetchFollowerStatus = async () => {
      const requestId = requestSequenceRef.current + 1;
      requestSequenceRef.current = requestId;

      try {
        let response;
        try {
          response = await axios.get(endpoints.followingStatus, buildNoCacheRequestConfig());
        } catch (followingStatusError) {
          if (!isMissingFollowingStatusRoute(followingStatusError)) {
            throw followingStatusError;
          }
          response = await axios.get(endpoints.followerData, buildNoCacheRequestConfig());
        }

        if (!mountedRef.current || requestId !== requestSequenceRef.current) {
          return;
        }
        setIsFollowing(readFollowingActive(response.data || {}));
      } catch (error) {
        if (!mountedRef.current || requestId !== requestSequenceRef.current) {
          return;
        }
        console.error('Error fetching follower data:', error);
        setIsFollowing(false);
      }
    };

    mountedRef.current = true;
    const intervalId = setInterval(fetchFollowerStatus, interval);
    fetchFollowerStatus(); // Initial call

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(intervalId);
    };
  }, [interval]);

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
  };
};

export const useFollowingTelemetry = (interval = 2000) => {
  const [followingTelemetry, setFollowingTelemetry] = useState({});
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
        response = await axios.get(endpoints.followingTelemetry, buildNoCacheRequestConfig());
      } catch (followingTelemetryError) {
        if (!isMissingFollowingTelemetryRoute(followingTelemetryError)) {
          throw followingTelemetryError;
        }
        response = await axios.get(endpoints.followerData, buildNoCacheRequestConfig());
      }

      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return null;
      }
      const normalized = normalizeFollowingTelemetry(response.data || {});
      setFollowingTelemetry(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return null;
      }
      if (!suppressErrors) {
        console.error('Error fetching following telemetry:', fetchError);
      }
      setFollowingTelemetry({});
      setError(fetchError);
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

    refresh();

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(intervalId);
    };
  }, [interval, refresh]);

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
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);

  const refresh = useCallback(async ({ suppressErrors = false } = {}) => {
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;

    try {
      let response;
      try {
        response = await axios.get(endpoints.streamingMediaHealth, buildNoCacheRequestConfig());
      } catch (streamingMediaHealthError) {
        if (!isMissingStreamingMediaHealthRoute(streamingMediaHealthError)) {
          throw streamingMediaHealthError;
        }
        response = await axios.get(endpoints.streamingStatus, buildNoCacheRequestConfig());
      }

      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
        return null;
      }

      const raw = response.data || {};
      const normalized = normalizeStreamingMediaHealth(raw);
      setStreamingHealth(raw);
      setStreamingStatus(normalized);
      setError(null);
      return normalized;
    } catch (fetchError) {
      if (!mountedRef.current || requestId !== requestSequenceRef.current) {
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

    refresh();

    return () => {
      mountedRef.current = false;
      requestSequenceRef.current += 1;
      clearInterval(intervalId);
    };
  }, [interval, refresh]);

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
