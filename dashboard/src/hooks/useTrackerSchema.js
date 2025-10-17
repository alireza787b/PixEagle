// dashboard/src/hooks/useTrackerSchema.js
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';

const API_URL = `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`;

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
      const response = await axios.get(`${API_URL}/api/tracker/schema`);
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
      const response = await axios.get(`${API_URL}/api/tracker/current-status`, {
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
    if (!schema || !currentStatus || !currentStatus.active) {
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
      const response = await axios.get(`${API_URL}/api/tracker/output`, {
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

  const fetchAvailableTrackers = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/tracker/available-types`);
      setAvailableTrackers(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching available trackers:', err);
      setError(err.message);
    }
  }, []);

  const fetchCurrentConfig = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/tracker/current-config`);
      setCurrentConfig(response.data);
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching current tracker config:', err);
      setError(err.message);
      setLoading(false);
    }
  }, []);

  const changeTrackerType = useCallback(async (trackerType) => {
    setIsChanging(true);
    try {
      const response = await axios.post(`${API_URL}/api/tracker/set-type`, {
        tracker_type: trackerType
      });
      
      // Refresh current config
      await fetchCurrentConfig();
      await fetchAvailableTrackers();
      
      setIsChanging(false);
      return response.data;
    } catch (err) {
      console.error('Error changing tracker type:', err);
      setError(err.message);
      setIsChanging(false);
      throw err;
    }
  }, [fetchCurrentConfig, fetchAvailableTrackers]);

  useEffect(() => {
    Promise.all([fetchAvailableTrackers(), fetchCurrentConfig()]);
    
    // Refresh every 5 seconds to stay in sync
    const interval = setInterval(() => {
      fetchCurrentConfig();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [fetchAvailableTrackers, fetchCurrentConfig]);

  return useMemo(() => ({
    availableTrackers,
    currentConfig,
    loading,
    error,
    isChanging,
    changeTrackerType,
    refetch: () => Promise.all([fetchAvailableTrackers(), fetchCurrentConfig()])
  }), [availableTrackers, currentConfig, loading, error, isChanging, changeTrackerType, fetchAvailableTrackers, fetchCurrentConfig]);
};

/**
 * Hook to fetch available UI-selectable trackers (NEW - mirrors follower pattern)
 * Uses /api/tracker/available endpoint
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
      const response = await axios.get(`${API_URL}/api/tracker/available`);
      // Only update if data actually changed
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulTrackers.current)) {
        setTrackers(response.data);
        lastSuccessfulTrackers.current = response.data;
      }
      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching available trackers:', err);
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
 * Uses /api/tracker/current endpoint
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
      const response = await axios.get(`${API_URL}/api/tracker/current`, {
        signal: abortControllerRef.current.signal
      });

      // Only update if data actually changed
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulTracker.current)) {
        setCurrentTracker(response.data);
        lastSuccessfulTracker.current = response.data;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching current tracker:', err);
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
 * Uses /api/tracker/switch endpoint
 * @returns {Object} { switchTracker, switching, switchError }
 */
export const useSwitchTracker = () => {
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const switchTracker = useCallback(async (trackerType) => {
    setSwitching(true);
    setSwitchError(null);

    try {
      const response = await axios.post(`${API_URL}/api/tracker/switch`, {
        tracker_type: trackerType
      });

      if (response.data.status === 'success') {
        // Show info message if tracking needs to be restarted
        if (response.data.requires_restart) {
          setSwitchError(
            `Tracker switched to ${trackerType}. Stop tracking and restart to activate the new tracker.`
          );
        }

        setSwitching(false);
        return true;
      } else {
        setSwitchError(response.data.error || 'Failed to switch tracker');
        setSwitching(false);
        return false;
      }
    } catch (err) {
      console.error('Error switching tracker:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to switch tracker';
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