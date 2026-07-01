// dashboard/src/hooks/useTrackerSchema.js
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';
import { trackerHasRuntimeOutput } from '../utils/trackerRuntimeState';

const asArray = (value) => (Array.isArray(value) ? value : []);

const asObject = (value) => (
  value && typeof value === 'object' && !Array.isArray(value) ? value : {}
);

const isObject = (value) => (
  value && typeof value === 'object' && !Array.isArray(value)
);

const legacyFallbackError = (message) => {
  const error = new Error(message);
  error.fallbackToLegacyTrackerCatalog = true;
  return error;
};

const shouldFallbackToLegacyTrackerCatalog = (error) => {
  if (error?.fallbackToLegacyTrackerCatalog) return true;

  const status = error?.response?.status;
  return status === 404 || status === 405 || status === 501;
};

const shouldFallbackToLegacyTrackerAction = shouldFallbackToLegacyTrackerCatalog;

export const TRACKER_COMPATIBILITY_FALLBACK_EVENT = 'pixeagle:tracker-compatibility-fallback';
export const TRACKER_COMPATIBILITY_FALLBACK_CLAIM_BOUNDARY = (
  'Dashboard observed that a typed tracker API endpoint was unavailable or unsupported and used a legacy compatibility endpoint. This is client-side telemetry only; it does not prove tracker runtime, PX4, SITL, HIL, field, or real-aircraft behavior.'
);
const MAX_TRACKER_COMPATIBILITY_FALLBACK_EVENTS = 50;
const trackerCompatibilityFallbackEvents = [];

const trackerFallbackReason = (error) => {
  if (!error) {
    return { status: null, message: 'unknown fallback reason' };
  }

  return {
    status: error.response?.status ?? null,
    message: error.message || error.response?.statusText || 'typed endpoint unavailable'
  };
};

export const clearTrackerCompatibilityFallbackEvents = () => {
  trackerCompatibilityFallbackEvents.length = 0;
};

export const getTrackerCompatibilityFallbackEvents = () => (
  trackerCompatibilityFallbackEvents.map((event) => ({
    ...event,
    legacy_endpoints: [...event.legacy_endpoints]
  }))
);

export const recordTrackerCompatibilityFallback = ({
  context,
  typedEndpoint,
  legacyEndpoints,
  error
}) => {
  const reason = trackerFallbackReason(error);
  const event = {
    event_type: 'tracker_api_compatibility_fallback',
    context,
    typed_endpoint: typedEndpoint,
    legacy_endpoints: asArray(legacyEndpoints),
    status: reason.status,
    message: reason.message,
    claim_boundary: TRACKER_COMPATIBILITY_FALLBACK_CLAIM_BOUNDARY,
    timestamp: Date.now() / 1000
  };

  trackerCompatibilityFallbackEvents.push(event);
  if (trackerCompatibilityFallbackEvents.length > MAX_TRACKER_COMPATIBILITY_FALLBACK_EVENTS) {
    trackerCompatibilityFallbackEvents.shift();
  }

  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn('PixEagle tracker compatibility fallback', event);
  }

  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    try {
      window.dispatchEvent(
        new CustomEvent(TRACKER_COMPATIBILITY_FALLBACK_EVENT, { detail: event })
      );
    } catch (dispatchError) {
      if (typeof console !== 'undefined' && typeof console.debug === 'function') {
        console.debug('Could not dispatch tracker compatibility fallback event', dispatchError);
      }
    }
  }

  return event;
};

const TRACKER_CATALOG_STATUSES = new Set(['available', 'degraded', 'unavailable']);
const TRACKER_CATALOG_GUIDANCE = new Set([
  'selectable',
  'operator_attention',
  'schema_manager_unavailable'
]);
const TRACKER_RUNTIME_STATUSES = new Set([
  'no_output',
  'visible_output',
  'active_usable',
  'not_usable',
  'stale_output',
  'unavailable'
]);
const TRACKER_RUNTIME_GUIDANCE = new Set([
  'no_output',
  'diagnostic_only',
  'usable',
  'not_usable',
  'stale',
  'unavailable'
]);

const malformedTypedTrackerCatalogError = (detail) => (
  new Error(`Malformed typed tracker catalog response: ${detail}.`)
);

const isFiniteNumber = (value) => (
  typeof value === 'number' && Number.isFinite(value)
);

const validateTypedTrackerCatalogPayload = (payload) => {
  if (!isObject(payload)) {
    throw malformedTypedTrackerCatalogError('expected a JSON object');
  }
  if (payload.source !== 'tracking_catalog') {
    throw malformedTypedTrackerCatalogError('missing tracking_catalog source');
  }
  if (!TRACKER_CATALOG_STATUSES.has(payload.status)) {
    throw malformedTypedTrackerCatalogError('missing or invalid status');
  }
  if (!TRACKER_CATALOG_GUIDANCE.has(payload.consumer_guidance)) {
    throw malformedTypedTrackerCatalogError('missing or invalid consumer_guidance');
  }
  if (!isObject(payload.runtime_status)) {
    throw malformedTypedTrackerCatalogError('missing runtime_status object');
  }
  if (!isFiniteNumber(payload.timestamp)) {
    throw malformedTypedTrackerCatalogError('missing or invalid timestamp');
  }
  if (payload.ui_trackers !== undefined && !Array.isArray(payload.ui_trackers)) {
    throw malformedTypedTrackerCatalogError('ui_trackers must be an array');
  }
  if (payload.tracker_types !== undefined && !isObject(payload.tracker_types)) {
    throw malformedTypedTrackerCatalogError('tracker_types must be an object');
  }

  const runtimeStatus = payload.runtime_status;
  if (runtimeStatus.source !== 'tracker_runtime') {
    throw malformedTypedTrackerCatalogError('missing tracker_runtime source');
  }
  if (!TRACKER_RUNTIME_STATUSES.has(runtimeStatus.status)) {
    throw malformedTypedTrackerCatalogError('missing or invalid runtime_status.status');
  }
  if (!TRACKER_RUNTIME_GUIDANCE.has(runtimeStatus.consumer_guidance)) {
    throw malformedTypedTrackerCatalogError('missing or invalid runtime_status.consumer_guidance');
  }
  [
    'has_output',
    'active_tracking',
    'usable_for_following',
    'data_is_stale'
  ].forEach((fieldName) => {
    if (typeof runtimeStatus[fieldName] !== 'boolean') {
      throw malformedTypedTrackerCatalogError(`runtime_status.${fieldName} must be boolean`);
    }
  });
  if (!isFiniteNumber(runtimeStatus.timestamp)) {
    throw malformedTypedTrackerCatalogError('missing or invalid runtime_status.timestamp');
  }
};

const normalizeTrackerEntry = (entry = {}, fallbackName = 'Tracker') => {
  const name = entry.name || fallbackName;
  const displayName = entry.display_name || name;
  const shortDescription = entry.short_description || entry.description || '';
  const suitableFor = asArray(entry.suitable_for);
  const capabilities = asArray(entry.capabilities);

  return {
    ...entry,
    name,
    display_name: displayName,
    short_description: shortDescription,
    description: entry.description || '',
    data_type: entry.data_type || null,
    smart_mode: Boolean(entry.smart_mode),
    available: entry.available !== false,
    unavailable_reason: entry.unavailable_reason || null,
    supported_schemas: asArray(entry.supported_schemas),
    capabilities,
    performance: asObject(entry.performance),
    suitable_for: suitableFor,
    icon: entry.icon || '🎯',
    performance_category: entry.performance_category || 'unknown',
    ui_metadata: {
      display_name: displayName,
      short_description: shortDescription,
      suitable_for: suitableFor,
      icon: entry.icon || '🎯',
      performance_category: entry.performance_category || 'unknown'
    }
  };
};

const findTrackerInfo = (trackerType, ...catalogs) => {
  if (!trackerType) return null;
  const normalizedType = trackerType.toLowerCase();

  for (const catalog of catalogs) {
    const entries = asObject(catalog);
    if (entries[trackerType]) return entries[trackerType];

    const match = Object.entries(entries).find(([key, value]) => {
      const names = [
        key,
        value?.name,
        value?.display_name
      ].filter(Boolean).map(item => String(item).toLowerCase());

      return names.some(name => (
        name === normalizedType ||
        name === `${normalizedType}tracker` ||
        name.startsWith(normalizedType) ||
        normalizedType.startsWith(name)
      ));
    });

    if (match) return match[1];
  }

  return null;
};

export const normalizeTrackerCatalogForLegacyConsumers = (catalog = {}) => {
  const uiTrackers = asArray(catalog.ui_trackers);
  const trackerTypes = asObject(catalog.tracker_types);
  const typeCatalog = {};

  Object.entries(trackerTypes).forEach(([key, entry]) => {
    typeCatalog[key] = normalizeTrackerEntry(
      { name: key, ...asObject(entry) },
      key
    );
  });

  const sourceEntries = uiTrackers.length > 0 ? uiTrackers : Object.values(typeCatalog);
  const availableTrackers = {};

  sourceEntries.forEach((entry, index) => {
    const normalized = normalizeTrackerEntry(asObject(entry), `tracker_${index}`);
    availableTrackers[normalized.name] = normalized;
  });

  const configuredTracker = catalog.configured_tracker || catalog.active_tracker || null;
  const activeTracker = catalog.active_tracker || null;
  const configuredInfo = findTrackerInfo(
    configuredTracker,
    availableTrackers,
    typeCatalog
  );
  const runtimeStatus = asObject(catalog.runtime_status);
  const healthIssues = asArray(catalog.health_issues);
  const expectedDataType = (
    configuredInfo?.data_type ||
    runtimeStatus.data_type ||
    'POSITION_2D'
  );

  return {
    availableTrackers: {
      available_trackers: availableTrackers,
      current_configured: configuredTracker,
      active_tracker: activeTracker,
      tracking_active: Boolean(catalog.tracking_active),
      smart_mode_active: Boolean(catalog.smart_mode_active),
      total_trackers: Object.keys(availableTrackers).length,
      source: 'api_v1_tracking_catalog',
      catalog_status: catalog.status || 'unavailable',
      consumer_guidance: catalog.consumer_guidance || 'operator_attention',
      health_issues: healthIssues,
      tracker_types: typeCatalog
    },
    currentConfig: {
      configured_tracker: configuredTracker,
      active_tracker: activeTracker,
      expected_data_type: expectedDataType,
      smart_mode_active: Boolean(catalog.smart_mode_active),
      tracking_started: Boolean(catalog.tracking_started),
      tracking_active: Boolean(catalog.tracking_active),
      catalog_status: catalog.status || 'unavailable',
      consumer_guidance: catalog.consumer_guidance || 'operator_attention',
      health_issues: healthIssues,
      runtime_status: runtimeStatus
    },
    currentTracker: {
      status: runtimeStatus.status || catalog.status || 'configured',
      active: Boolean(catalog.tracking_active),
      tracker_type: configuredTracker,
      active_tracker: activeTracker,
      display_name: configuredInfo?.display_name || configuredTracker || activeTracker || 'Tracker',
      icon: configuredInfo?.icon || configuredInfo?.ui_metadata?.icon || '🎯',
      short_description: configuredInfo?.short_description || configuredInfo?.ui_metadata?.short_description || '',
      description: configuredInfo?.description || '',
      performance_category: configuredInfo?.performance_category || configuredInfo?.ui_metadata?.performance_category || 'unknown',
      capabilities: asArray(configuredInfo?.capabilities),
      suitable_for: asArray(configuredInfo?.suitable_for || configuredInfo?.ui_metadata?.suitable_for),
      following_active: Boolean(runtimeStatus.following_active),
      smart_mode_active: Boolean(catalog.smart_mode_active),
      source: 'api_v1_tracking_catalog',
      catalog_status: catalog.status || 'unavailable',
      consumer_guidance: catalog.consumer_guidance || 'operator_attention',
      health_issues: healthIssues
    },
    rawCatalog: catalog
  };
};

const fetchTypedTrackerCatalog = async (config) => {
  const response = config
    ? await axios.get(endpoints.trackerCatalog, config)
    : await axios.get(endpoints.trackerCatalog);
  validateTypedTrackerCatalogPayload(response.data);

  const catalog = normalizeTrackerCatalogForLegacyConsumers(response.data);
  if (
    response.data.status === 'unavailable' &&
    Object.keys(catalog.availableTrackers.available_trackers).length === 0
  ) {
    throw legacyFallbackError('Typed tracker catalog unavailable with no entries.');
  }

  return catalog;
};

const postLegacyTrackerSwitch = (trackerType) => (
  axios.post(endpoints.trackerSwitch, {
    tracker_type: trackerType
  })
);

const postTrackerSwitchAction = async (trackerType, reason, metadata) => {
  try {
    return await axios.post(endpoints.trackerSwitchAction, {
      ...buildActionRequest(reason, metadata),
      tracker_type: trackerType
    });
  } catch (err) {
    if (!shouldFallbackToLegacyTrackerAction(err)) {
      throw err;
    }

    recordTrackerCompatibilityFallback({
      context: 'tracker_switch_action',
      typedEndpoint: endpoints.trackerSwitchAction,
      legacyEndpoints: [endpoints.trackerSwitch],
      error: err
    });
    return postLegacyTrackerSwitch(trackerType);
  }
};

const trackerSwitchSucceeded = (payload) => (
  payload?.status === 'success'
);

const trackerSwitchErrorText = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    return (
      trackerSwitchErrorText(value.message) ||
      trackerSwitchErrorText(value.detail) ||
      trackerSwitchErrorText(value.error) ||
      trackerSwitchErrorText(value.code)
    );
  }
  return null;
};

const trackerSwitchErrorMessage = (payload, fallback = 'Failed to switch tracker') => (
  trackerSwitchErrorText(payload?.error) ||
  trackerSwitchErrorText(payload?.detail) ||
  trackerSwitchErrorText(payload?.message) ||
  fallback
);

/**
 * Hook for fetching and managing tracker schema data
 * Provides complete YAML schema for tracker data types and validation rules
 */
export const useTrackerSchema = (refreshInterval = 10000) => {
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulSchema = useRef(null);

  const fetchSchema = useCallback(async () => {
    try {
      const response = await axios.get(endpoints.trackerSchema);
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulSchema.current)) {
        setSchema(response.data);
        lastSuccessfulSchema.current = response.data;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching tracker schema:', err);
      setError(err.message);
      // Keep previous successful data on error
      if (lastSuccessfulSchema.current) {
        setSchema(lastSuccessfulSchema.current);
      }
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSchema();
    
    const interval = setInterval(fetchSchema, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchSchema, refreshInterval]);

  return useMemo(() => ({ 
    schema, 
    loading, 
    error, 
    refetch: fetchSchema 
  }), [schema, loading, error, fetchSchema]);
};

/**
 * Hook for real-time tracker status and field data
 * Provides current tracker information with schema-driven field display
 */
export const useCurrentTrackerStatus = (refreshInterval = 1000) => {
  const [currentStatus, setCurrentStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulStatus = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchCurrentStatus = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    abortControllerRef.current = new AbortController();
    
    try {
      const response = await axios.get(endpoints.trackerCurrentStatus, {
        signal: abortControllerRef.current.signal
      });
      
      // Only update if data actually changed
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulStatus.current)) {
        setCurrentStatus(response.data);
        lastSuccessfulStatus.current = response.data;
      }
      
      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching current tracker status:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulStatus.current) {
          setCurrentStatus(lastSuccessfulStatus.current);
        }
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchCurrentStatus();
    
    const interval = setInterval(fetchCurrentStatus, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchCurrentStatus, refreshInterval]);

  return useMemo(() => ({ 
    currentStatus, 
    loading, 
    error, 
    refetch: fetchCurrentStatus 
  }), [currentStatus, loading, error, fetchCurrentStatus]);
};

/**
 * Hook for tracker data types and their field definitions
 * Provides schema-driven field information for UI display
 */
export const useTrackerDataTypes = (schema, currentStatus) => {
  return useMemo(() => {
    if (!schema || !currentStatus || !trackerHasRuntimeOutput(currentStatus)) {
      return { dataTypes: {}, currentDataType: null, availableFields: {} };
    }

    const dataTypes = schema.tracker_data_types || {};
    const currentDataType = currentStatus.data_type;
    const availableFields = currentStatus.fields || {};
    
    // Get schema definition for current data type (handle both cases)
    const dataTypeKey = currentDataType?.toUpperCase() || '';
    const currentTypeSchema = dataTypes[dataTypeKey] || dataTypes[currentDataType] || {};
    
    // Enhanced field information with schema metadata
    const enhancedFields = {};
    Object.entries(availableFields).forEach(([fieldName, fieldData]) => {
      const schemaValidation = currentTypeSchema.validation?.[fieldName] || {};
      
      enhancedFields[fieldName] = {
        ...fieldData,
        schema: {
          description: currentTypeSchema.description || `${currentDataType} tracking data`,
          validation: schemaValidation,
          required: currentTypeSchema.required_fields?.includes(fieldName) || false,
          optional: currentTypeSchema.optional_fields?.includes(fieldName) || false
        }
      };
    });
    
    return { 
      dataTypes, 
      currentDataType: currentTypeSchema,
      availableFields: enhancedFields,
      trackerType: currentStatus.tracker_type,
      smartMode: currentStatus.smart_mode
    };
  }, [schema, currentStatus]);
};

/**
 * Hook for tracker output data with real-time updates
 * Provides structured tracker output for plotting and analysis
 */
export const useTrackerOutput = (refreshInterval = 1000) => {
  const [output, setOutput] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulOutput = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchOutput = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    abortControllerRef.current = new AbortController();
    
    try {
      const response = await axios.get(endpoints.trackerOutput, {
        signal: abortControllerRef.current.signal
      });
      
      // Always update output data for real-time tracking
      setOutput(response.data);
      lastSuccessfulOutput.current = response.data;
      
      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching tracker output:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulOutput.current) {
          setOutput(lastSuccessfulOutput.current);
        }
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchOutput();
    
    const interval = setInterval(fetchOutput, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchOutput, refreshInterval]);

  return useMemo(() => ({ 
    output, 
    loading, 
    error, 
    refetch: fetchOutput 
  }), [output, loading, error, fetchOutput]);
};

/**
 * Hook for tracker selection and management
 * Provides available tracker types and current configuration
 */
export const useTrackerSelection = () => {
  const [availableTrackers, setAvailableTrackers] = useState({});
  const [currentConfig, setCurrentConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isChanging, setIsChanging] = useState(false);

  const fetchTrackerSelection = useCallback(async () => {
    try {
      const catalog = await fetchTypedTrackerCatalog();
      setAvailableTrackers(catalog.availableTrackers);
      setCurrentConfig(catalog.currentConfig);
      setError(null);
      setLoading(false);
      return catalog;
    } catch (err) {
      if (!shouldFallbackToLegacyTrackerCatalog(err)) {
        console.error('Error fetching typed tracker catalog:', err);
        setError(err.message);
        setLoading(false);
        return null;
      }

      recordTrackerCompatibilityFallback({
        context: 'tracker_selection_catalog',
        typedEndpoint: endpoints.trackerCatalog,
        legacyEndpoints: [
          endpoints.trackerAvailableTypes,
          endpoints.trackerCurrentConfig
        ],
        error: err
      });

      try {
        const [availableResponse, currentResponse] = await Promise.all([
          axios.get(endpoints.trackerAvailableTypes),
          axios.get(endpoints.trackerCurrentConfig)
        ]);
        setAvailableTrackers(availableResponse.data);
        setCurrentConfig(currentResponse.data);
        setError(null);
        setLoading(false);
        return {
          availableTrackers: availableResponse.data,
          currentConfig: currentResponse.data
        };
      } catch (legacyErr) {
        console.error('Error fetching legacy tracker config:', legacyErr);
        setError(legacyErr.message);
        setLoading(false);
        return null;
      }
    }
  }, []);

  const changeTrackerType = useCallback(async (trackerType) => {
    setIsChanging(true);
    try {
      const response = await postTrackerSwitchAction(
        trackerType,
        'switch_tracker',
        { ui: 'dashboard_tracker_selection' }
      );
      if (!trackerSwitchSucceeded(response.data)) {
        throw new Error(trackerSwitchErrorMessage(response.data));
      }
      
      // Refresh current config
      await fetchTrackerSelection();
      
      setIsChanging(false);
      return response.data;
    } catch (err) {
      console.error('Error changing tracker type:', err);
      setError(err.message);
      setIsChanging(false);
      throw err;
    }
  }, [fetchTrackerSelection]);

  useEffect(() => {
    fetchTrackerSelection();
    
    // Refresh every 5 seconds to stay in sync
    const interval = setInterval(() => {
      fetchTrackerSelection();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchTrackerSelection]);

  return useMemo(() => ({
    availableTrackers,
    currentConfig,
    loading,
    error,
    isChanging,
    changeTrackerType,
    refetch: fetchTrackerSelection
  }), [availableTrackers, currentConfig, loading, error, isChanging, changeTrackerType, fetchTrackerSelection]);
};

/**
 * Hook to fetch available UI-selectable trackers (NEW - mirrors follower pattern)
 * Uses /api/v1/tracking/catalog with legacy /api/tracker/available fallback
 * @param {number} refreshInterval - Polling interval in milliseconds (default: 10000)
 * @returns {Object} { trackers, loading, error, refetch }
 */
export const useAvailableTrackers = (refreshInterval = 10000) => {
  const [trackers, setTrackers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulTrackers = useRef(null);

  const fetchTrackers = useCallback(async () => {
    try {
      const catalog = await fetchTypedTrackerCatalog();
      // Only update if data actually changed
      if (JSON.stringify(catalog.availableTrackers) !== JSON.stringify(lastSuccessfulTrackers.current)) {
        setTrackers(catalog.availableTrackers);
        lastSuccessfulTrackers.current = catalog.availableTrackers;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      if (!shouldFallbackToLegacyTrackerCatalog(err)) {
        console.error('Error fetching typed tracker catalog:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulTrackers.current) {
          setTrackers(lastSuccessfulTrackers.current);
        }
        setLoading(false);
        return;
      }

      recordTrackerCompatibilityFallback({
        context: 'tracker_available_catalog',
        typedEndpoint: endpoints.trackerCatalog,
        legacyEndpoints: [endpoints.trackerAvailable],
        error: err
      });
      try {
        const response = await axios.get(endpoints.trackerAvailable);
        if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulTrackers.current)) {
          setTrackers(response.data);
          lastSuccessfulTrackers.current = response.data;
        }
        setError(null);
        setLoading(false);
      } catch (legacyErr) {
        console.error('Error fetching available trackers:', legacyErr);
        setError(legacyErr.message);
        // Keep previous successful data on error
        if (lastSuccessfulTrackers.current) {
          setTrackers(lastSuccessfulTrackers.current);
        }
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchTrackers();

    const interval = setInterval(fetchTrackers, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchTrackers, refreshInterval]);

  return useMemo(
    () => ({
      trackers,
      loading,
      error,
      refetch: fetchTrackers
    }),
    [trackers, loading, error, fetchTrackers]
  );
};

/**
 * Hook to fetch current tracker status and configuration (NEW - mirrors follower pattern)
 * Uses /api/v1/tracking/catalog with legacy /api/tracker/current fallback
 * @param {number} refreshInterval - Polling interval in milliseconds (default: 2000)
 * @returns {Object} { currentTracker, loading, error, refetch }
 */
export const useCurrentTracker = (refreshInterval = 2000) => {
  const [currentTracker, setCurrentTracker] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulTracker = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchCurrentTracker = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();

    try {
      const catalog = await fetchTypedTrackerCatalog({
        signal: abortControllerRef.current.signal
      });

      // Only update if data actually changed
      if (JSON.stringify(catalog.currentTracker) !== JSON.stringify(lastSuccessfulTracker.current)) {
        setCurrentTracker(catalog.currentTracker);
        lastSuccessfulTracker.current = catalog.currentTracker;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        if (!shouldFallbackToLegacyTrackerCatalog(err)) {
          console.error('Error fetching typed tracker catalog:', err);
          setError(err.message);
          // Keep previous successful data on error
          if (lastSuccessfulTracker.current) {
            setCurrentTracker(lastSuccessfulTracker.current);
          }
          setLoading(false);
          return;
        }

        recordTrackerCompatibilityFallback({
          context: 'tracker_current_catalog',
          typedEndpoint: endpoints.trackerCatalog,
          legacyEndpoints: [endpoints.trackerCurrent],
          error: err
        });

        try {
          const response = await axios.get(endpoints.trackerCurrent, {
            signal: abortControllerRef.current.signal
          });

          if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulTracker.current)) {
            setCurrentTracker(response.data);
            lastSuccessfulTracker.current = response.data;
          }

          setError(null);
          setLoading(false);
        } catch (legacyErr) {
          if (legacyErr.name !== 'CanceledError') {
            console.error('Error fetching current tracker:', legacyErr);
            setError(legacyErr.message);
            // Keep previous successful data on error
            if (lastSuccessfulTracker.current) {
              setCurrentTracker(lastSuccessfulTracker.current);
            }
            setLoading(false);
          }
        }
      }
    }
  }, []);

  useEffect(() => {
    fetchCurrentTracker();

    const interval = setInterval(fetchCurrentTracker, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchCurrentTracker, refreshInterval]);

  return useMemo(
    () => ({
      currentTracker,
      loading,
      error,
      refetch: fetchCurrentTracker
    }),
    [currentTracker, loading, error, fetchCurrentTracker]
  );
};

/**
 * Hook to switch between different tracker types (NEW - mirrors follower pattern)
 * Uses typed /api/v1/actions/tracker-switch with legacy switch fallback only
 * when the typed action is absent or unsupported.
 * @returns {Object} { switchTracker, switching, switchError }
 */
export const useSwitchTracker = () => {
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const switchTracker = useCallback(async (trackerType) => {
    setSwitching(true);
    setSwitchError(null);

    try {
      const response = await postTrackerSwitchAction(
        trackerType,
        'switch_tracker',
        { ui: 'dashboard_tracker_selector' }
      );
      const payload = response.data;
      const legacyResult = payload?.result?.legacy_result || payload;

      if (trackerSwitchSucceeded(payload)) {
        // Show info message if tracking needs to be restarted
        if (legacyResult.requires_restart) {
          setSwitchError(
            `Tracker switched to ${trackerType}. Stop tracking and restart to activate the new tracker.`
          );
        }

        setSwitching(false);
        return true;
      } else {
        setSwitchError(trackerSwitchErrorMessage(payload));
        setSwitching(false);
        return false;
      }
    } catch (err) {
      console.error('Error switching tracker:', err);
      const errorMsg = trackerSwitchErrorMessage(
        err.response?.data,
        err.message || 'Failed to switch tracker'
      );
      setSwitchError(errorMsg);
      setSwitching(false);
      return false;
    }
  }, []);

  return useMemo(
    () => ({
      switchTracker,
      switching,
      switchError
    }),
    [switchTracker, switching, switchError]
  );
};
