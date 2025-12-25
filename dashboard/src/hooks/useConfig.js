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
 * Hook for managing a single section's configuration
 */
export const useConfigSection = (sectionName) => {
  const [config, setConfig] = useState({});
  const [defaultConfig, setDefaultConfig] = useState({});
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pendingChanges, setPendingChanges] = useState({});
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

        if (response.data.reboot_required) {
          setRebootRequired(true);
        }

        return {
          success: true,
          saved: wasSaved,
          validation: response.data.validation,
          reboot_required: response.data.reboot_required
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
 * Hook for configuration search
 */
export const useConfigSearch = () => {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const search = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(`${endpoints.configSearch}?q=${encodeURIComponent(query)}`);
      if (response.data.success) {
        setResults(response.data.results);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const clearResults = useCallback(() => {
    setResults([]);
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

export default useConfigSection;
