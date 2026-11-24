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
import { apiFetch } from '../services/apiClient';

/**
 * Hook for recording status and control.
 *
 * @param {number} pollInterval - Polling interval in ms (default 2000)
 * @returns {Object} Recording state and actions
 */
export const useRecording = (pollInterval = 2000) => {
  const [recordingStatus, setRecordingStatus] = useState(null);
  const [storageStatus, setStorageStatus] = useState(null);
  const [recordingAvailable, setRecordingAvailable] = useState(null);
  const [recordingUnavailableReason, setRecordingUnavailableReason] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const mountedRef = useRef(true);

  const ensureActionSucceeded = useCallback((data) => {
    if (data && data.status === 'error') {
      throw new Error(data.message || data.detail || 'Recording request failed');
    }
    return data;
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await apiFetch(endpoints.recordingStatus);
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload?.detail || payload?.error || payload?.message || detail;
        } catch {
          detail = await response.text().catch(() => detail);
        }
        throw new Error(detail);
      }
      const data = await response.json();
      if (mountedRef.current) {
        const unavailable = data.available === false;
        setRecordingStatus(data.recording || null);
        setStorageStatus(data.storage || null);
        setRecordingAvailable(!unavailable);
        setRecordingUnavailableReason(
          unavailable
            ? data.reason || data.recording?.message || 'Recording subsystem unavailable'
            : null
        );
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
      const response = await apiFetch(endpoints.recordingStart, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = ensureActionSucceeded(await response.json());
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [ensureActionSucceeded, fetchStatus]);

  const pauseRecording = useCallback(async () => {
    try {
      const response = await apiFetch(endpoints.recordingPause, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = ensureActionSucceeded(await response.json());
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [ensureActionSucceeded, fetchStatus]);

  const resumeRecording = useCallback(async () => {
    try {
      const response = await apiFetch(endpoints.recordingResume, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = ensureActionSucceeded(await response.json());
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [ensureActionSucceeded, fetchStatus]);

  const stopRecording = useCallback(async () => {
    try {
      const response = await apiFetch(endpoints.recordingStop, { method: 'POST' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = ensureActionSucceeded(await response.json());
      await fetchStatus();
      return data;
    } catch (err) {
      throw err;
    }
  }, [ensureActionSucceeded, fetchStatus]);

  return {
    recordingStatus,
    storageStatus,
    recordingAvailable,
    recordingUnavailableReason,
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
  const [available, setAvailable] = useState(null);
  const [unavailableReason, setUnavailableReason] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchRecordings = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiFetch(endpoints.recordingsList);
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          detail = payload?.detail || payload?.error || payload?.message || detail;
        } catch {
          detail = await response.text().catch(() => detail);
        }
        throw new Error(detail);
      }
      const data = await response.json();
      const unavailable = data.available === false;
      setRecordings(data.recordings || []);
      setAvailable(!unavailable);
      setUnavailableReason(
        unavailable ? data.reason || 'Recording subsystem unavailable' : null
      );
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
      const response = await apiFetch(endpoints.recordingDelete(filename), {
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
    available,
    unavailableReason,
    loading,
    error,
    refresh: fetchRecordings,
    deleteRecording,
    getDownloadUrl,
  };
};
