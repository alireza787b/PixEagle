// dashboard/src/hooks/useDefaultsSync.js
import { useState, useCallback, useEffect, useRef } from 'react';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

export const CONFIG_SYNC_CONTRACT_VERSION = 2;

const EMPTY_COUNTS = { new: 0, changed: 0, retired: 0, extensions: 0, actionable: 0 };
const EMPTY_META = {
  baselineAvailable: false,
  baselineSavedAt: null,
  schemaVersion: 'unknown',
  retirementRegistryVersion: null,
};

const isCanonicalPath = (path) => (
  Array.isArray(path)
  && (path.length === 1 || path.length === 2)
  && path.every((part) => typeof part === 'string' && part.length > 0)
);

export const getConfigSyncItemPath = (item) => {
  if (isCanonicalPath(item?.path)) {
    return item.path;
  }
  return [];
};

export const getConfigSyncItemKey = (item) => {
  const path = getConfigSyncItemPath(item);
  return path.length > 0 ? JSON.stringify(path) : '';
};

const normalizedMessage = (value, fallback) => {
  if (typeof value === 'string' && value.trim()) return value;
  if (Array.isArray(value)) {
    const messages = value
      .map((entry) => normalizedMessage(entry, ''))
      .filter(Boolean);
    return messages.length > 0 ? messages.join('; ') : fallback;
  }
  if (value && typeof value === 'object') {
    return normalizedMessage(
      value.message || value.msg || value.error || value.detail,
      fallback
    );
  }
  return fallback;
};

const payloadError = (payload, operation) => {
  if (payload?.success !== true) {
    return normalizedMessage(
      payload?.error || payload?.detail,
      `${operation} was not successful`
    );
  }
  if (payload.contract_version !== CONFIG_SYNC_CONTRACT_VERSION) {
    const received = payload.contract_version ?? 'missing';
    return (
      `Unsupported Config Sync contract version ${received}; `
      + `this dashboard requires version ${CONFIG_SYNC_CONTRACT_VERSION}`
    );
  }
  return null;
};

const isNonNegativeInteger = (value) => Number.isInteger(value) && value >= 0;
const isPlanDigest = (value) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

const planShapeError = (plan) => {
  if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
    return 'Config Sync preview did not return a plan';
  }
  if (plan.contract_version !== CONFIG_SYNC_CONTRACT_VERSION) {
    return 'Config Sync preview returned an incompatible plan contract';
  }
  if (typeof plan.valid !== 'boolean' || !isPlanDigest(plan.plan_digest)) {
    return 'Config Sync preview returned invalid plan metadata';
  }
  if (
    !Array.isArray(plan.operations)
    || !Array.isArray(plan.warnings)
    || !Array.isArray(plan.errors)
    || plan.operations.some((operation) => !isCanonicalPath(operation?.path))
  ) {
    return 'Config Sync preview returned malformed operation details';
  }
  const summary = plan.summary;
  if (
    !summary
    || !isNonNegativeInteger(summary.requested)
    || !isNonNegativeInteger(summary.applicable)
    || !isNonNegativeInteger(summary.skipped)
    || summary.applicable + summary.skipped !== plan.operations.length
  ) {
    return 'Config Sync preview returned an invalid summary';
  }
  return null;
};

const applyShapeError = (payload) => {
  if (
    !isNonNegativeInteger(payload?.applied_count)
    || !isNonNegativeInteger(payload?.skipped_count)
    || !Array.isArray(payload?.applied_operations)
    || !Array.isArray(payload?.skipped_operations)
    || !isPlanDigest(payload?.plan_digest)
  ) {
    return 'Config Sync apply returned malformed result metadata';
  }
  if (
    payload.applied_count !== payload.applied_operations.length
    || payload.skipped_count !== payload.skipped_operations.length
    || [...payload.applied_operations, ...payload.skipped_operations].some(
      (operation) => !isCanonicalPath(operation?.path)
    )
  ) {
    return 'Config Sync apply counts do not match its operation lists';
  }
  return null;
};

const reportShapeError = (payload) => {
  const listFields = [
    'new_parameters',
    'changed_defaults',
    'registered_retirements',
    'unknown_extensions',
  ];
  if (listFields.some((field) => !Array.isArray(payload[field]))) {
    return 'Config Sync report is missing required item lists';
  }
  if (listFields.some((field) => payload[field].some(
    (item) => !isCanonicalPath(item?.path)
  ))) {
    return 'Config Sync report contains a non-canonical config path';
  }

  const countFields = ['new', 'changed', 'retired', 'extensions', 'actionable'];
  if (
    !payload.counts
    || countFields.some(
      (field) => !Number.isInteger(payload.counts[field]) || payload.counts[field] < 0
    )
  ) {
    return 'Config Sync report is missing valid counts';
  }

  const expectedCounts = {
    new: payload.new_parameters.length,
    changed: payload.changed_defaults.length,
    retired: payload.registered_retirements.length,
    extensions: payload.unknown_extensions.length,
  };
  if (
    payload.counts.new !== expectedCounts.new
    || payload.counts.changed !== expectedCounts.changed
    || payload.counts.retired !== expectedCounts.retired
    || payload.counts.extensions !== expectedCounts.extensions
    || payload.counts.actionable !== (
      expectedCounts.new + expectedCounts.changed + expectedCounts.retired
    )
  ) {
    return 'Config Sync report counts do not match its item lists';
  }
  return null;
};

const responseError = (err) => normalizedMessage(
  err.response?.data?.error || err.response?.data?.detail || err.message,
  'Config Sync request failed'
);

export const useDefaultsSync = () => {
  const [newParameters, setNewParameters] = useState([]);
  const [changedDefaults, setChangedDefaults] = useState([]);
  const [registeredRetirements, setRegisteredRetirements] = useState([]);
  const [unknownExtensions, setUnknownExtensions] = useState([]);
  const [counts, setCounts] = useState(EMPTY_COUNTS);
  const [meta, setMeta] = useState(EMPTY_META);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reportAvailable, setReportAvailable] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const fetchGenerationRef = useRef(0);

  const clearReport = useCallback(() => {
    setNewParameters([]);
    setChangedDefaults([]);
    setRegisteredRetirements([]);
    setUnknownExtensions([]);
    setCounts(EMPTY_COUNTS);
    setMeta(EMPTY_META);
    setReportAvailable(false);
  }, []);

  const fetchSyncData = useCallback(async () => {
    const generation = fetchGenerationRef.current + 1;
    fetchGenerationRef.current = generation;
    setLoading(true);
    setError(null);
    clearReport();
    try {
      const response = await axios.get(endpoints.configDefaultsSync);
      const contractError = payloadError(response.data, 'Config Sync report');
      const shapeError = contractError ? null : reportShapeError(response.data);
      if (generation !== fetchGenerationRef.current) return false;
      if (contractError || shapeError) {
        setError(contractError || shapeError);
        return false;
      }

      setNewParameters(response.data.new_parameters);
      setChangedDefaults(response.data.changed_defaults);
      setRegisteredRetirements(response.data.registered_retirements);
      setUnknownExtensions(response.data.unknown_extensions);
      setCounts(response.data.counts);
      setMeta({
        baselineAvailable: Boolean(response.data.baseline_available),
        baselineSavedAt: response.data.baseline_saved_at || null,
        schemaVersion: response.data.schema_version || 'unknown',
        retirementRegistryVersion: response.data.retirement_registry_version ?? null,
      });
      setReportAvailable(true);
      return true;
    } catch (err) {
      if (generation !== fetchGenerationRef.current) return false;
      setError(responseError(err));
      return false;
    } finally {
      if (generation === fetchGenerationRef.current) setLoading(false);
    }
  }, [clearReport]);

  useEffect(() => {
    fetchSyncData();
    return () => {
      fetchGenerationRef.current += 1;
    };
  }, [fetchSyncData]);

  const buildOperationsFromSelections = useCallback((selection) => {
    const ops = [];

    (selection.selectedNew || []).forEach((key) => {
      const item = newParameters.find((candidate) => getConfigSyncItemKey(candidate) === key);
      const path = getConfigSyncItemPath(item);
      if (path.length > 0) {
        ops.push({
          op_type: 'ADD_NEW',
          path: [...path],
        });
      }
    });

    (selection.selectedChanged || []).forEach((key) => {
      const item = changedDefaults.find((candidate) => getConfigSyncItemKey(candidate) === key);
      const path = getConfigSyncItemPath(item);
      if (path.length > 0) {
        ops.push({
          op_type: 'ADOPT_DEFAULT',
          path: [...path],
        });
      }
    });

    (selection.selectedRetired || []).forEach((key) => {
      const item = registeredRetirements.find(
        (candidate) => getConfigSyncItemKey(candidate) === key
      );
      const path = getConfigSyncItemPath(item);
      if (path.length > 0) {
        ops.push({
          op_type: 'REMOVE_RETIRED',
          path: [...path],
        });
      }
    });

    return ops;
  }, [newParameters, changedDefaults, registeredRetirements]);

  const previewOperations = useCallback(async (operations) => {
    if (!operations || operations.length === 0) {
      return { success: false, error: 'No operations selected' };
    }

    setPlanning(true);
    try {
      const response = await axios.post(endpoints.configDefaultsSyncPlan, {
        contract_version: CONFIG_SYNC_CONTRACT_VERSION,
        operations,
      });
      const contractError = payloadError(response.data, 'Config Sync preview');
      if (contractError) {
        return { success: false, error: contractError };
      }
      const shapeError = planShapeError(response.data.plan);
      if (shapeError) {
        return { success: false, error: shapeError };
      }
      return { success: true, plan: response.data.plan };
    } catch (err) {
      return {
        success: false,
        error: responseError(err),
        plan: err.response?.data?.plan,
      };
    } finally {
      setPlanning(false);
    }
  }, []);

  const applyOperations = useCallback(async (operations, planDigest) => {
    if (!operations || operations.length === 0 || !planDigest) {
      return { success: false, error: 'A current preview is required' };
    }

    setApplying(true);
    try {
      const response = await axios.post(endpoints.configDefaultsSyncApply, {
        contract_version: CONFIG_SYNC_CONTRACT_VERSION,
        operations,
        plan_digest: planDigest,
        confirm: true,
      });
      const contractError = payloadError(response.data, 'Config Sync apply');
      if (contractError) {
        return { success: false, error: contractError };
      }
      const shapeError = applyShapeError(response.data);
      if (shapeError) {
        return { success: false, error: shapeError };
      }
      await fetchSyncData();
      return { success: true, result: response.data };
    } catch (err) {
      return {
        success: false,
        error: responseError(err),
        plan: err.response?.data?.plan,
      };
    } finally {
      setApplying(false);
    }
  }, [fetchSyncData]);

  return {
    newParameters,
    changedDefaults,
    registeredRetirements,
    unknownExtensions,
    counts,
    meta,
    loading,
    error,
    reportAvailable,
    planning,
    applying,
    hasSyncItems: reportAvailable && counts.actionable > 0,
    refresh: fetchSyncData,
    buildOperationsFromSelections,
    previewOperations,
    applyOperations,
  };
};

export default useDefaultsSync;
