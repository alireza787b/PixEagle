// dashboard/src/hooks/useDefaultsSync.js
import { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

const EMPTY_COUNTS = { new: 0, changed: 0, removed: 0, total: 0 };

const toKey = (section, parameter) => `${section}.${parameter}`;

export const useDefaultsSync = () => {
  const [newParameters, setNewParameters] = useState([]);
  const [changedDefaults, setChangedDefaults] = useState([]);
  const [removedParameters, setRemovedParameters] = useState([]);
  const [counts, setCounts] = useState(EMPTY_COUNTS);
  const [meta, setMeta] = useState({
    baselineAvailable: false,
    baselineInitialized: false,
    baselineSavedAt: null,
    schemaVersion: 'unknown',
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [planning, setPlanning] = useState(false);
  const [applying, setApplying] = useState(false);

  const fetchSyncData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get(endpoints.configDefaultsSync);
      if (response.data.success) {
        setNewParameters(response.data.new_parameters || []);
        setChangedDefaults(response.data.changed_defaults || []);
        setRemovedParameters(response.data.removed_parameters || []);
        setCounts(response.data.counts || EMPTY_COUNTS);
        setMeta({
          baselineAvailable: Boolean(response.data.baseline_available),
          baselineInitialized: Boolean(response.data.baseline_initialized),
          baselineSavedAt: response.data.baseline_saved_at || null,
          schemaVersion: response.data.schema_version || 'unknown',
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSyncData();
  }, [fetchSyncData]);

  const buildOperationsFromSelections = useCallback((selection) => {
    const ops = [];

    (selection.selectedNew || []).forEach((key) => {
      const item = newParameters.find((p) => toKey(p.section, p.parameter) === key);
      if (item) {
        ops.push({
          op_type: 'ADD_NEW',
          section: item.section,
          parameter: item.parameter,
          value: item.default_value,
        });
      }
    });

    (selection.selectedChanged || []).forEach((key) => {
      const item = changedDefaults.find((p) => toKey(p.section, p.parameter) === key);
      if (item) {
        ops.push({
          op_type: 'ADOPT_DEFAULT',
          section: item.section,
          parameter: item.parameter,
        });
      }
    });

    (selection.selectedRemoved || []).forEach((key) => {
      const item = removedParameters.find((p) => toKey(p.section, p.parameter) === key);
      if (item) {
        ops.push({
          op_type: 'ARCHIVE_REMOVE',
          section: item.section,
          parameter: item.parameter,
        });
      }
    });

    return ops;
  }, [newParameters, changedDefaults, removedParameters]);

  const previewOperations = useCallback(async (operations) => {
    if (!operations || operations.length === 0) {
      return { success: false, error: 'No operations selected' };
    }

    setPlanning(true);
    try {
      const response = await axios.post(endpoints.configDefaultsSyncPlan, { operations });
      return { success: true, plan: response.data.plan };
    } catch (err) {
      return {
        success: false,
        error: err.response?.data?.detail || err.message,
        plan: err.response?.data?.plan,
      };
    } finally {
      setPlanning(false);
    }
  }, []);

  const applyOperations = useCallback(async (operations) => {
    if (!operations || operations.length === 0) {
      return { success: false, error: 'No operations selected' };
    }

    setApplying(true);
    try {
      const response = await axios.post(endpoints.configDefaultsSyncApply, { operations });
      await fetchSyncData();
      return { success: true, result: response.data };
    } catch (err) {
      return {
        success: false,
        error: err.response?.data?.detail || err.message,
        plan: err.response?.data?.plan,
      };
    } finally {
      setApplying(false);
    }
  }, [fetchSyncData]);

  return {
    newParameters,
    changedDefaults,
    removedParameters,
    counts,
    meta,
    loading,
    error,
    planning,
    applying,
    hasSyncItems: counts.total > 0,
    refresh: fetchSyncData,
    buildOperationsFromSelections,
    previewOperations,
    applyOperations,
  };
};

export default useDefaultsSync;
