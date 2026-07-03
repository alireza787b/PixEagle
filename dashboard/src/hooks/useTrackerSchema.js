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

const malformedTypedTrackingTelemetryError = (detail) => (
  new Error(`Malformed typed tracker telemetry response: ${detail}.`)
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
  if (!isObject(payload.data_type_schemas)) {
    throw malformedTypedTrackerCatalogError('missing data_type_schemas object');
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
    throw new Error('Typed tracker catalog unavailable with no entries.');
  }

  return catalog;
};

const normalizeTypedTrackerCatalogForSchema = (catalog = {}) => ({
  tracker_data_types: asObject(catalog.data_type_schemas),
  tracker_types: asObject(catalog.tracker_types),
  ui_trackers: asArray(catalog.ui_trackers),
  source: 'api_v1_tracking_catalog',
  catalog_status: catalog.status || 'unavailable',
  consumer_guidance: catalog.consumer_guidance || 'operator_attention',
  health_issues: asArray(catalog.health_issues),
  claim_boundary: catalog.claim_boundary,
  timestamp: catalog.timestamp
});

const validateTypedTrackingTelemetryPayload = (payload) => {
  if (!isObject(payload)) {
    throw malformedTypedTrackingTelemetryError('expected a JSON object');
  }
  if (payload.source !== 'tracking_telemetry') {
    throw malformedTypedTrackingTelemetryError('missing tracking_telemetry source');
  }
  if (!TRACKER_RUNTIME_STATUSES.has(payload.status)) {
    throw malformedTypedTrackingTelemetryError('missing or invalid status');
  }
  if (!TRACKER_RUNTIME_GUIDANCE.has(payload.consumer_guidance)) {
    throw malformedTypedTrackingTelemetryError('missing or invalid consumer_guidance');
  }
  [
    'has_output',
    'active_tracking',
    'usable_for_following',
    'data_is_stale'
  ].forEach((fieldName) => {
    if (typeof payload[fieldName] !== 'boolean') {
      throw malformedTypedTrackingTelemetryError(`${fieldName} must be boolean`);
    }
  });
  if (!isFiniteNumber(payload.timestamp)) {
    throw malformedTypedTrackingTelemetryError('missing or invalid timestamp');
  }
  if (payload.fields !== undefined && !isObject(payload.fields)) {
    throw malformedTypedTrackingTelemetryError('fields must be an object');
  }
  if (payload.tracker_data !== undefined && !isObject(payload.tracker_data)) {
    throw malformedTypedTrackingTelemetryError('tracker_data must be an object');
  }

  const runtimeStatus = payload.runtime_status;
  if (!isObject(runtimeStatus)) {
    throw malformedTypedTrackingTelemetryError('missing runtime_status object');
  }
  if (runtimeStatus.source !== 'tracker_runtime') {
    throw malformedTypedTrackingTelemetryError('missing tracker_runtime source');
  }
  if (!TRACKER_RUNTIME_STATUSES.has(runtimeStatus.status)) {
    throw malformedTypedTrackingTelemetryError('missing or invalid runtime_status.status');
  }
  if (!TRACKER_RUNTIME_GUIDANCE.has(runtimeStatus.consumer_guidance)) {
    throw malformedTypedTrackingTelemetryError('missing or invalid runtime_status.consumer_guidance');
  }
  [
    'has_output',
    'active_tracking',
    'usable_for_following',
    'data_is_stale'
  ].forEach((fieldName) => {
    if (typeof runtimeStatus[fieldName] !== 'boolean') {
      throw malformedTypedTrackingTelemetryError(`runtime_status.${fieldName} must be boolean`);
    }
  });
};

const normalizeTypedFieldType = (value) => {
  if (Array.isArray(value)) return 'list';
  if (value === null) return 'null';
  if (Number.isInteger(value)) return 'int';
  if (typeof value === 'number') return 'float';
  if (typeof value === 'string') return 'str';
  return typeof value;
};

const normalizeTypedTrackingFieldInfo = (fieldName, value) => {
  if (isObject(value) && Object.prototype.hasOwnProperty.call(value, 'value')) {
    return {
      ...value,
      display_name: value.display_name || fieldName.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase()),
      type: value.type || normalizeTypedFieldType(value.value)
    };
  }

  const displayName = fieldName.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());

  if (fieldName === 'angular' && Array.isArray(value) && value.length === 3) {
    return {
      value,
      type: 'angular_3d',
      display_name: 'Gimbal Angles (Y, P, R)',
      description: 'Gimbal yaw, pitch, roll angles in degrees',
      units: '\u00b0',
      format: 'tuple_3d',
      components: ['yaw', 'pitch', 'roll']
    };
  }

  if ((fieldName === 'position_2d' || fieldName === 'normalized_position') && Array.isArray(value) && value.length === 2) {
    return {
      value,
      type: 'position_2d',
      display_name: 'Target Position (X, Y)',
      description: 'Normalized 2D position coordinates',
      units: 'normalized',
      format: 'tuple_2d',
      components: ['x', 'y']
    };
  }

  if ((fieldName === 'bbox' || fieldName === 'normalized_bbox') && Array.isArray(value) && value.length === 4) {
    return {
      value,
      type: 'bbox',
      display_name: 'Bounding Box',
      description: 'Target bounding box coordinates',
      units: fieldName === 'normalized_bbox' ? 'normalized' : 'pixels',
      format: 'bbox',
      components: ['x', 'y', 'width', 'height']
    };
  }

  if (fieldName === 'confidence') {
    return {
      value,
      type: 'confidence',
      display_name: 'Tracking Confidence',
      description: 'Tracker confidence score',
      units: typeof value === 'number' ? '%' : '',
      format: 'percentage',
      range: typeof value === 'number' ? [0.0, 1.0] : null
    };
  }

  if (fieldName === 'velocity' && Array.isArray(value)) {
    return {
      value,
      type: 'velocity',
      display_name: 'Target Velocity',
      description: 'Target velocity vector',
      units: value.length === 2 ? 'px/s' : 'units/s',
      format: `tuple_${value.length}d`,
      components: value.length === 2 ? ['vx', 'vy'] : ['vx', 'vy', 'vz']
    };
  }

  if ((fieldName === 'tracking' || fieldName === 'tracking_status') && typeof value === 'string') {
    const upperValue = value.toUpperCase();
    return {
      value,
      type: 'tracking_status',
      display_name: 'Tracking Status',
      description: 'Current tracker or gimbal tracking state',
      format: 'status_string',
      status_color: upperValue.includes('ACTIVE')
        ? 'success'
        : upperValue.includes('SELECTION')
          ? 'warning'
          : 'error'
    };
  }

  if ((fieldName === 'system' || fieldName === 'coordinate_system') && typeof value === 'string') {
    return {
      value,
      type: 'coordinate_system',
      display_name: 'Coordinate System',
      description: 'Tracker coordinate reference system',
      format: 'system_string'
    };
  }

  if (Array.isArray(value)) {
    return {
      value,
      type: `list_${value.length}d`,
      display_name: displayName,
      description: `${value.length}-dimensional ${fieldName} data`,
      format: `list_${value.length}d`,
      components: value.map((_, index) => `component_${index}`)
    };
  }

  return {
    value,
    type: normalizeTypedFieldType(value),
    display_name: displayName,
    description: `${fieldName} field data`,
    format: normalizeTypedFieldType(value)
  };
};

const normalizeTypedTrackingTelemetryForStatus = (payload = {}) => {
  const runtimeStatus = asObject(payload.runtime_status);
  const fields = asObject(payload.fields);
  const trackerData = asObject(payload.tracker_data);
  const sourceFields = Object.keys(fields).length > 0 ? fields : trackerData;
  const rawData = asObject(sourceFields.raw_data);
  const dataType = runtimeStatus.data_type || sourceFields.data_type || null;
  const systemFields = new Set([
    'timestamp',
    'tracking_active',
    'tracker_id',
    'data_type',
    'metadata',
    'raw_data'
  ]);
  const normalizedFields = {};

  Object.entries(sourceFields).forEach(([fieldName, value]) => {
    if (!systemFields.has(fieldName) && value !== null && value !== undefined) {
      normalizedFields[fieldName] = normalizeTypedTrackingFieldInfo(fieldName, value);
    }
  });

  [
    'tracking',
    'tracking_status',
    'system',
    'coordinate_system',
    'yaw',
    'pitch',
    'roll',
    'provider',
    'protocol',
    'usable_for_following',
    'gimbal_tracking_active',
    'has_output',
    'data_is_stale',
    'freshness_reason',
    'connection_status'
  ].forEach((fieldName) => {
    if (rawData[fieldName] !== null && rawData[fieldName] !== undefined) {
      normalizedFields[fieldName] = normalizeTypedTrackingFieldInfo(fieldName, rawData[fieldName]);
    }
  });

  return {
    active: Boolean(payload.active_tracking),
    active_tracking: Boolean(payload.active_tracking),
    has_output: Boolean(payload.has_output),
    usable_for_following: Boolean(payload.usable_for_following),
    data_is_stale: Boolean(payload.data_is_stale),
    status: payload.status || runtimeStatus.status || 'unavailable',
    consumer_guidance: payload.consumer_guidance || runtimeStatus.consumer_guidance || 'unavailable',
    reason: payload.reason || runtimeStatus.reason || null,
    tracker_type: runtimeStatus.tracker_type || runtimeStatus.active_tracker || runtimeStatus.configured_tracker || runtimeStatus.tracker_id || null,
    data_type: dataType,
    fields: normalizedFields,
    raw_data: rawData,
    runtime_status: runtimeStatus,
    smart_mode: Boolean(runtimeStatus.smart_mode_active),
    inference: null,
    claim_boundary: runtimeStatus.claim_boundary || payload.claim_boundary,
    timestamp: payload.timestamp
  };
};

const fetchTypedTrackingTelemetry = async (config) => {
  const response = config
    ? await axios.get(endpoints.trackingTelemetry, config)
    : await axios.get(endpoints.trackingTelemetry);
  validateTypedTrackingTelemetryPayload(response.data);
  return response.data;
};

const postTrackerSwitchAction = async (trackerType, reason, metadata) => {
  return await axios.post(endpoints.trackerSwitchAction, {
    ...buildActionRequest(reason, metadata),
    tracker_type: trackerType
  });
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
      const catalog = await fetchTypedTrackerCatalog();
      const schemaPayload = normalizeTypedTrackerCatalogForSchema(catalog.rawCatalog);
      if (JSON.stringify(schemaPayload) !== JSON.stringify(lastSuccessfulSchema.current)) {
        setSchema(schemaPayload);
        lastSuccessfulSchema.current = schemaPayload;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching typed tracker schema metadata:', err);
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
      const telemetry = await fetchTypedTrackingTelemetry({
        signal: abortControllerRef.current.signal
      });
      const status = normalizeTypedTrackingTelemetryForStatus(telemetry);
      
      // Only update if data actually changed
      if (JSON.stringify(status) !== JSON.stringify(lastSuccessfulStatus.current)) {
        setCurrentStatus(status);
        lastSuccessfulStatus.current = status;
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
      const outputData = await fetchTypedTrackingTelemetry({
        signal: abortControllerRef.current.signal
      });
      
      // Always update output data for real-time tracking
      setOutput(outputData);
      lastSuccessfulOutput.current = outputData;
      
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
      console.error('Error fetching typed tracker catalog:', err);
      setError(err.message);
      setLoading(false);
      return null;
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
 * Uses /api/v1/tracking/catalog.
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
      console.error('Error fetching typed tracker catalog:', err);
      setError(err.message);
      // Keep previous successful data on error
      if (lastSuccessfulTrackers.current) {
        setTrackers(lastSuccessfulTrackers.current);
      }
      setLoading(false);
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
 * Uses /api/v1/tracking/catalog.
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
        console.error('Error fetching typed tracker catalog:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulTracker.current) {
          setCurrentTracker(lastSuccessfulTracker.current);
        }
        setLoading(false);
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
 * Uses typed /api/v1/actions/tracker-switch.
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
