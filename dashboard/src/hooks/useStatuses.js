//dashboard/src/hooks/useStatuses.js
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { apiConfig } from '../services/apiEndpoints';

const API_URL = `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`;
const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const buildNoCacheRequestConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
});

export const useTrackerStatus = (interval = 2000) => {
  const [isTracking, setIsTracking] = useState(false);

  useEffect(() => {
    const fetchTrackerStatus = async () => {
      try {
        const response = await axios.get(`${API_URL}/telemetry/tracker_data`, buildNoCacheRequestConfig());
        const trackerData = response.data;

        if (trackerData.tracker_started) {
          setIsTracking(true);
        } else {
          setIsTracking(false);
        }
      } catch (error) {
        console.error('Error fetching tracker data:', error);
        console.log("URI Used is:", `${API_URL}/telemetry/tracker_data`);
        setIsTracking(false);
      }
    };

    const intervalId = setInterval(fetchTrackerStatus, interval);
    fetchTrackerStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return isTracking;
};

export const useFollowerStatus = (interval = 2000) => {
  const [isFollowing, setIsFollowing] = useState(false);

  useEffect(() => {
    const fetchFollowerStatus = async () => {
      try {
        const response = await axios.get(`${API_URL}/telemetry/follower_data`, buildNoCacheRequestConfig());
        const followerData = response.data;

        setIsFollowing(followerData.following_active);
      } catch (error) {
        console.error('Error fetching follower data:', error);
        setIsFollowing(false);
      }
    };

    const intervalId = setInterval(fetchFollowerStatus, interval);
    fetchFollowerStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return isFollowing;
};


export const useSmartModeStatus = (interval = 2000) => {
  const [smartModeActive, setSmartModeActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = useCallback(async ({ suppressErrors = false } = {}) => {
    try {
      const response = await axios.get(`${API_URL}/status`, buildNoCacheRequestConfig());
      const data = response.data || {};
      const nextState = Boolean(data.smart_mode_active);
      setSmartModeActive(nextState);
      setError(null);
      return nextState;
    } catch (fetchError) {
      if (!suppressErrors) {
        console.error('Error fetching smart mode status:', fetchError);
      }
      setError(fetchError);
      // Keep previous UI state on transient errors rather than forcing false.
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const intervalId = setInterval(() => {
      refresh({ suppressErrors: true });
    }, interval);

    refresh(); // Initial call

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        refresh({ suppressErrors: true });
      }
    };

    const handleWindowFocus = () => {
      refresh({ suppressErrors: true });
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleWindowFocus);
    }

    return () => {
      clearInterval(intervalId);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
    };
  }, [interval, refresh]);

  return {
    smartModeActive,
    refresh,
    loading,
    error,
  };
};
