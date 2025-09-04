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
export const useCurrentTrackerStatus = (refreshInterval = 2000) => {
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
    
    // Get schema definition for current data type
    const currentTypeSchema = dataTypes[currentDataType?.toUpperCase()] || {};
    
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