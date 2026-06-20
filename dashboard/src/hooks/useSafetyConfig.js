// dashboard/src/hooks/useSafetyConfig.js
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

/**
 * Hook to fetch safety limits for a specific follower.
 * Auto-refreshes when followerName changes.
 */
export const useSafetyLimits = (followerName, refreshInterval = 5000) => {
  const [limits, setLimits] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulLimits = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchLimits = useCallback(async () => {
    if (!followerName) {
      setLimits(null);
      setLoading(false);
      return;
    }

    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();

    try {
      const response = await axios.get(
        endpoints.safetyLimits(followerName),
        { signal: abortControllerRef.current.signal }
      );

      // Only update if data actually changed
      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulLimits.current)) {
        setLimits(response.data);
        lastSuccessfulLimits.current = response.data;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching safety limits:', err);
        setError(err.message);
        // Keep previous successful data on error
        if (lastSuccessfulLimits.current) {
          setLimits(lastSuccessfulLimits.current);
        }
        setLoading(false);
      }
    }
  }, [followerName]);

  useEffect(() => {
    setLoading(true);
    fetchLimits();

    const interval = setInterval(fetchLimits, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchLimits, refreshInterval]);

  return useMemo(() => ({
    limits,
    loading,
    error,
    refetch: fetchLimits
  }), [limits, loading, error, fetchLimits]);
};

/**
 * Hook to fetch complete safety configuration.
 * Note: Currently unused but kept for future admin/debug features.
 */
export const useSafetyConfig = (refreshInterval = 10000) => {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulConfig = useRef(null);
  const abortControllerRef = useRef(null);

  const fetchConfig = useCallback(async () => {
    // Cancel previous request if still pending
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();

    try {
      const response = await axios.get(endpoints.safetyConfig, {
        signal: abortControllerRef.current.signal
      });

      if (JSON.stringify(response.data) !== JSON.stringify(lastSuccessfulConfig.current)) {
        setConfig(response.data);
        lastSuccessfulConfig.current = response.data;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      if (err.name !== 'CanceledError') {
        console.error('Error fetching safety config:', err);
        setError(err.message);
        if (lastSuccessfulConfig.current) {
          setConfig(lastSuccessfulConfig.current);
        }
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchConfig();

    const interval = setInterval(fetchConfig, refreshInterval);
    return () => {
      clearInterval(interval);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchConfig, refreshInterval]);

  return useMemo(() => ({
    config,
    loading,
    error,
    refetch: fetchConfig
  }), [config, loading, error, fetchConfig]);
};
