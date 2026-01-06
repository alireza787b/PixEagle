// dashboard/src/hooks/useDefaultsSync.js
/**
 * Hook for syncing configuration with default values (v5.4.0+)
 *
 * Provides information about:
 * - New parameters in defaults that user doesn't have
 * - Changed default values between versions
 * - Removed parameters (in user config but not in schema)
 */

import { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

/**
 * Hook for syncing configuration with defaults.
 *
 * @returns {Object} Sync state and actions
 * @returns {Array} return.newParameters - Parameters in defaults but not in user config
 * @returns {Array} return.changedDefaults - Parameters where default value changed
 * @returns {Array} return.removedParameters - Parameters user has but no longer in schema
 * @returns {Object} return.counts - Count of each category and total
 * @returns {boolean} return.loading - Whether data is being fetched
 * @returns {string|null} return.error - Error message if any
 * @returns {Function} return.refresh - Refetch sync data
 * @returns {Function} return.acceptParameter - Accept a specific new parameter
 * @returns {Function} return.acceptAllNew - Accept all new parameters
 * @returns {Function} return.removeObsolete - Remove an obsolete parameter
 *
 * @example
 * const { newParameters, counts, acceptAllNew } = useDefaultsSync();
 */
export const useDefaultsSync = () => {
  const [newParameters, setNewParameters] = useState([]);
  const [changedDefaults, setChangedDefaults] = useState([]);
  const [removedParameters, setRemovedParameters] = useState([]);
  const [counts, setCounts] = useState({ new: 0, changed: 0, removed: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchSyncData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.configDefaultsSync);
      if (response.data.success) {
        setNewParameters(response.data.new_parameters || []);
        setChangedDefaults(response.data.changed_defaults || []);
        setRemovedParameters(response.data.removed_parameters || []);
        setCounts(response.data.counts || { new: 0, changed: 0, removed: 0, total: 0 });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchSyncData();
  }, [fetchSyncData]);

  /**
   * Accept a specific new parameter (add to current config with default value)
   */
  const acceptParameter = useCallback(async (section, parameter, value) => {
    try {
      const response = await axios.put(
        endpoints.configUpdateParameter(section, parameter),
        { value }
      );
      if (response.data.success) {
        // Remove from newParameters list
        setNewParameters(prev =>
          prev.filter(p => !(p.section === section && p.parameter === parameter))
        );
        setCounts(prev => ({
          ...prev,
          new: prev.new - 1,
          total: prev.total - 1,
        }));
        return { success: true };
      }
      return { success: false, error: response.data.error };
    } catch (err) {
      return { success: false, error: err.message };
    }
  }, []);

  /**
   * Accept all new parameters at once
   */
  const acceptAllNew = useCallback(async () => {
    const results = [];
    for (const param of newParameters) {
      const result = await acceptParameter(
        param.section,
        param.parameter,
        param.default_value
      );
      results.push({ ...param, ...result });
    }
    // Refresh to update state
    await fetchSyncData();
    return results;
  }, [newParameters, acceptParameter, fetchSyncData]);

  /**
   * Remove an obsolete parameter from current config
   * (Note: This would need a backend endpoint to delete a parameter,
   * for now we just track it as acknowledged)
   */
  const removeObsolete = useCallback((section, parameter) => {
    // Remove from removedParameters list (acknowledgement only for now)
    setRemovedParameters(prev =>
      prev.filter(p => !(p.section === section && p.parameter === parameter))
    );
    setCounts(prev => ({
      ...prev,
      removed: prev.removed - 1,
      total: prev.total - 1,
    }));
  }, []);

  /**
   * Check if there are any sync items available
   */
  const hasSyncItems = counts.total > 0;

  return {
    newParameters,
    changedDefaults,
    removedParameters,
    counts,
    loading,
    error,
    hasSyncItems,
    refresh: fetchSyncData,
    acceptParameter,
    acceptAllNew,
    removeObsolete,
  };
};

export default useDefaultsSync;
