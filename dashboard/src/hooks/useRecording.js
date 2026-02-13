// dashboard/src/hooks/useRecording.js
/**
 * Custom hook for recording state management.
 *
 * Polls /api/recording/status at configurable interval and provides
 * start/pause/resume/stop actions. Follows the same polling pattern
 * as useStatuses.js and useTrackerSchema.js.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { endpoints } from '../services/apiEndpoints';

/**
 * Hook for recording status and control.
 *
 * @param {number} pollInterval - Polling interval in ms (default 2000)
 * @returns {Object} Recording state and actions
 */
export const useRecording = (pollInterval = 2000) => {
  const [recordingStatus, setRecordingStatus] = useState(null);
  const [storageStatus, setStorageStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(endpoints.recordingStatus);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (mountedRef.current) {
        setRecordingStatus(data.recording || null);
        setStorageStatus(data.storage || null);
        setError(null);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchStatus();
    const id = setInterval(fetchStatus, pollInterval);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
  }, [fetchStatus, pollInterval]);

  const startRecording = useCallback(async () => {
    try {
      const response = await fetch(endpoints.recordingStart, { method: 'POST' });
      const data = await response.json();
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [fetchStatus]);

  const pauseRecording = useCallback(async () => {
    try {
      const response = await fetch(endpoints.recordingPause, { method: 'POST' });
      const data = await response.json();
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [fetchStatus]);

  const resumeRecording = useCallback(async () => {
    try {
      const response = await fetch(endpoints.recordingResume, { method: 'POST' });
      const data = await response.json();
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [fetchStatus]);

  const stopRecording = useCallback(async () => {
    try {
      const response = await fetch(endpoints.recordingStop, { method: 'POST' });
      const data = await response.json();
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [fetchStatus]);

  return {
    recordingStatus,
    storageStatus,
    loading,
    error,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    refresh: fetchStatus,
  };
};

/**
 * Hook for recordings list management.
 *
 * @returns {Object} Recordings list and management actions
 */
export const useRecordingsList = () => {
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRecordings = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(endpoints.recordingsList);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setRecordings(data.recordings || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecordings();
  }, [fetchRecordings]);

  const deleteRecording = useCallback(async (filename) => {
    try {
      const response = await fetch(endpoints.recordingDelete(filename), {
        method: 'DELETE',
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      await fetchRecordings();
      return { status: 'success' };
    } catch (err) {
      throw err;
    }
  }, [fetchRecordings]);

  const getDownloadUrl = useCallback((filename) => {
    return endpoints.recordingDownload(filename);
  }, []);

  return {
    recordings,
    loading,
    error,
    refresh: fetchRecordings,
    deleteRecording,
    getDownloadUrl,
  };
};
