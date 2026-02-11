// dashboard/src/hooks/useConfig.js
import { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

/**
 * Hook for fetching configuration schema
 */
export const useConfigSchema = () => {
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const abortControllerRef = useRef(null);

  const fetchSchema = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.configSchema, {
        signal: abortControllerRef.current.signal
      });
      if (response.data.success) {
        setSchema(response.data.schema);
      }
    } catch (err) {
      if (!axios.isCancel(err)) {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSchema();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchSchema]);

  return { schema, loading, error, refetch: fetchSchema };
};

/**
 * Hook for fetching section list with metadata
 */
export const useConfigSections = () => {
  const [sections, setSections] = useState([]);
  const [categories, setCategories] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchSections = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [sectionsRes, categoriesRes] = await Promise.all([
        axios.get(endpoints.configSections),
        axios.get(endpoints.configCategories)
      ]);

      if (sectionsRes.data.success) {
        setSections(sectionsRes.data.sections);
      }
      if (categoriesRes.data.success) {
        setCategories(categoriesRes.data.categories);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSections();
  }, [fetchSections]);

  // Group sections by category
  const groupedSections = sections.reduce((acc, section) => {
    const category = section.category || 'other';
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(section);
    return acc;
  }, {});

  return { sections, categories, groupedSections, loading, error, refetch: fetchSections };
};

/**
 * Hook for managing a single section's configuration.
 *
 * Provides CRUD operations for configuration parameters within a section,
 * with support for hot-reload tiers and validation.
 *
 * @param {string} sectionName - The configuration section name (e.g., 'Tracker', 'Follower')
 * @returns {Object} Configuration state and methods
 * @returns {Object} return.config - Current configuration values
 * @returns {Object} return.defaultConfig - Default configuration values
 * @returns {Object} return.schema - Schema definitions for parameters
 * @returns {boolean} return.loading - Whether data is being fetched
 * @returns {string|null} return.error - Error message if any
 * @returns {Object} return.pendingChanges - Unsaved local changes
 * @returns {boolean} return.hasPendingChanges - Whether there are unsaved changes
 * @returns {boolean} return.rebootRequired - Whether any saved change requires system restart (deprecated: use reload_tier)
 * @returns {Function} return.updateParameter - Save a parameter value
 * @returns {Function} return.setLocalValue - Set local value without saving
 * @returns {Function} return.saveAllChanges - Save all pending changes
 * @returns {Function} return.revertParameter - Revert parameter to default
 * @returns {Function} return.revertSection - Revert entire section to defaults
 * @returns {Function} return.isModified - Check if parameter differs from default
 * @returns {Function} return.refetch - Re-fetch section data
 */
export const useConfigSection = (sectionName) => {
  const [config, setConfig] = useState({});
  const [defaultConfig, setDefaultConfig] = useState({});
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingChanges, setPendingChanges] = useState({});
  // Track if any saved change requires system restart (kept for backward compatibility)
  // Prefer using reload_tier from updateParameter response for granular control
  const [rebootRequired, setRebootRequired] = useState(false);

  const fetchSection = useCallback(async () => {
    if (!sectionName) return;

    setLoading(true);
    setError(null);

    try {
      const [configRes, defaultRes, schemaRes] = await Promise.all([
        axios.get(endpoints.configCurrentSection(sectionName)),
        axios.get(endpoints.configDefaultSection(sectionName)),
        axios.get(endpoints.configSectionSchema(sectionName))
      ]);

      if (configRes.data.success) {
        setConfig(configRes.data.config || {});
      }
      if (defaultRes.data.success) {
        setDefaultConfig(defaultRes.data.config || {});
      }
      if (schemaRes.data.success) {
        setSchema(schemaRes.data.schema);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [sectionName]);

  useEffect(() => {
    fetchSection();
    setPendingChanges({});
    setRebootRequired(false);
  }, [fetchSection, sectionName]);

  const updateParameter = useCallback(async (param, value) => {
    try {
      const response = await axios.put(
        endpoints.configUpdateParameter(sectionName, param),
        { value }
      );

      if (response.data.success) {
        // Check if the config was actually saved to disk
        const wasSaved = response.data.saved !== false;

        if (wasSaved) {
          setConfig(prev => ({ ...prev, [param]: value }));
          setPendingChanges(prev => {
            const updated = { ...prev };
            delete updated[param];
            return updated;
          });
        }

        // Track if any change requires system restart (legacy compatibility)
        if (response.data.reboot_required) {
          setRebootRequired(true);
        }

        return {
          success: true,
          saved: wasSaved,
          validation: response.data.validation,
          applied: response.data.applied,  // True if hot-reload was successful
          reload_tier: response.data.reload_tier,  // immediate, follower_restart, tracker_restart, system_restart
          reload_message: response.data.reload_message,
          reboot_required: response.data.reboot_required  // Legacy, use reload_tier instead
        };
      } else {
        return {
          success: false,
          saved: false,
          validation: response.data.validation,
          error: response.data.error
        };
      }
    } catch (err) {
      return { success: false, error: err.message };
    }
  }, [sectionName]);

  const setLocalValue = useCallback((param, value) => {
    setPendingChanges(prev => ({ ...prev, [param]: value }));
  }, []);

  const saveAllChanges = useCallback(async () => {
    const results = [];
    for (const [param, value] of Object.entries(pendingChanges)) {
      const result = await updateParameter(param, value);
      results.push({ param, ...result });
    }
    return results;
  }, [pendingChanges, updateParameter]);

  const revertParameter = useCallback(async (param) => {
    try {
      const response = await axios.post(
        endpoints.configRevertParameter(sectionName, param)
      );
      if (response.data.success) {
        setConfig(prev => ({ ...prev, [param]: response.data.default_value }));
        return true;
      }
      return false;
    } catch (err) {
      return false;
    }
  }, [sectionName]);

  const revertSection = useCallback(async () => {
    try {
      const response = await axios.post(
        endpoints.configRevertSection(sectionName)
      );
      if (response.data.success) {
        await fetchSection();
        return true;
      }
      return false;
    } catch (err) {
      return false;
    }
  }, [sectionName, fetchSection]);

  const isModified = useCallback((param) => {
    return config[param] !== defaultConfig[param];
  }, [config, defaultConfig]);

  const hasPendingChanges = Object.keys(pendingChanges).length > 0;

  return {
    config,
    defaultConfig,
    schema,
    loading,
    error,
    pendingChanges,
    hasPendingChanges,
    rebootRequired,
    updateParameter,
    setLocalValue,
    saveAllChanges,
    revertParameter,
    revertSection,
    isModified,
    refetch: fetchSection
  };
};

/**
 * Hook for configuration search with debounce and request cancellation
 */
export const useConfigSearch = () => {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const abortControllerRef = useRef(null);

  const search = useCallback((query) => {
    // Clear any pending debounce timer
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    if (!query || query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    // Show loading immediately for responsiveness
    setLoading(true);

    // Debounce the actual API call by 300ms
    debounceRef.current = setTimeout(async () => {
      // Cancel any in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      setError(null);

      try {
        const response = await axios.get(
          `${endpoints.configSearch}?q=${encodeURIComponent(query)}`,
          { signal: abortControllerRef.current.signal }
        );
        if (response.data.success) {
          setResults(response.data.results);
        }
      } catch (err) {
        if (!axios.isCancel(err)) {
          setError(err.message);
        }
      } finally {
        setLoading(false);
      }
    }, 300);
  }, []);

  const clearResults = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setResults([]);
    setLoading(false);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

  return { results, loading, error, search, clearResults };
};

/**
 * Hook for config diff/comparison
 */
export const useConfigDiff = () => {
  const [diff, setDiff] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDiff = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.configDiff);
      if (response.data.success) {
        setDiff(response.data.differences);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDiff();
  }, [fetchDiff]);

  return { diff, loading, error, refetch: fetchDiff };
};

/**
 * Hook for config backup history
 */
export const useConfigHistory = () => {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.configHistory);
      if (response.data.success) {
        setBackups(response.data.backups);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const restoreBackup = useCallback(async (backupId) => {
    try {
      const response = await axios.post(endpoints.configRestore(backupId));
      if (response.data.success) {
        await fetchHistory();
        return true;
      }
      return false;
    } catch (err) {
      return false;
    }
  }, [fetchHistory]);

  return { backups, loading, error, restoreBackup, refetch: fetchHistory };
};

/**
 * Hook for fetching current follower mode and effective limits (v5.0.0+)
 */
export const useCurrentFollowerMode = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchMode = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.currentFollowerMode);
      if (response.data.success) {
        setData(response.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMode();
  }, [fetchMode]);

  return {
    mode: data?.mode,
    modeUpper: data?.mode_upper,
    isActive: data?.is_active,
    effectiveLimits: data?.effective_limits,
    profileInfo: data?.profile_info,
    loading,
    error,
    refetch: fetchMode
  };
};

/**
 * Hook for fetching effective limits with resolution chain (v5.0.0+)
 */
export const useEffectiveLimits = (followerName) => {
  const [limits, setLimits] = useState({});
  const [availableFollowers, setAvailableFollowers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLimits = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.effectiveLimits(followerName));
      if (response.data.success) {
        setLimits(response.data.limits);
        setAvailableFollowers(response.data.available_followers || []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [followerName]);

  useEffect(() => {
    fetchLimits();
  }, [fetchLimits]);

  return { limits, availableFollowers, loading, error, refetch: fetchLimits };
};

/**
 * Hook for fetching relevant sections based on follower mode (v5.0.0+)
 */
export const useRelevantSections = (followerMode) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchSections = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.relevantSections(followerMode));
      if (response.data.success) {
        setData(response.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [followerMode]);

  useEffect(() => {
    fetchSections();
  }, [fetchSections]);

  return {
    activeSections: data?.active_sections || [],
    otherSections: data?.other_sections || [],
    modeSpecificSections: data?.mode_specific_sections || [],
    globalSections: data?.global_sections || [],
    currentMode: data?.current_mode,
    loading,
    error,
    refetch: fetchSections
  };
};

export default useConfigSection;
