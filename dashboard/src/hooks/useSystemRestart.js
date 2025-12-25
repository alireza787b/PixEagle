// dashboard/src/hooks/useSystemRestart.js
import { useState, useCallback, useEffect } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

const MAX_POLL_ATTEMPTS = 30; // 30 seconds timeout
const POLL_INTERVAL = 1000; // 1 second

/**
 * useSystemRestart - Hook for managing system restart operations
 *
 * Returns:
 * - restarting: boolean - whether restart is in progress
 * - error: string|null - error message if restart failed
 * - pollCount: number - current poll attempt count
 * - initiateRestart: function - starts the restart process
 * - clearError: function - clears the error state
 */
const useSystemRestart = ({ onSuccess, onError, reloadPageOnSuccess = true } = {}) => {
  const [restarting, setRestarting] = useState(false);
  const [error, setError] = useState(null);
  const [pollCount, setPollCount] = useState(0);

  const pollStatus = useCallback(async () => {
    try {
      const response = await axios.get(endpoints.systemStatus, {
        timeout: 2000
      });
      if (response.data.success) {
        return true;
      }
    } catch (err) {
      // Still restarting...
    }
    return false;
  }, []);

  useEffect(() => {
    let interval;
    if (restarting && pollCount > 0) {
      interval = setInterval(async () => {
        const isBack = await pollStatus();
        if (isBack) {
          setRestarting(false);
          setPollCount(0);
          onSuccess?.();
          if (reloadPageOnSuccess) {
            // Brief delay before reload to show success state
            setTimeout(() => {
              window.location.reload();
            }, 500);
          }
        } else if (pollCount < MAX_POLL_ATTEMPTS) {
          setPollCount(prev => prev + 1);
        } else {
          // Timeout
          const errorMsg = 'Backend did not come back within expected time. Please check manually.';
          setError(errorMsg);
          setRestarting(false);
          setPollCount(0);
          onError?.(errorMsg);
        }
      }, POLL_INTERVAL);
    }
    return () => clearInterval(interval);
  }, [restarting, pollCount, pollStatus, onSuccess, onError, reloadPageOnSuccess]);

  const initiateRestart = useCallback(async (reason = 'User requested restart') => {
    setRestarting(true);
    setError(null);
    setPollCount(0);

    try {
      const response = await axios.post(endpoints.systemRestart, { reason });

      if (response.data.success) {
        // Wait a bit for restart to initiate, then start polling
        setTimeout(() => {
          setPollCount(1);
        }, 3000);
        return { success: true };
      } else {
        throw new Error(response.data.message || 'Restart failed');
      }
    } catch (err) {
      const errorMsg = err.message || 'Failed to initiate restart';
      setError(errorMsg);
      setRestarting(false);
      onError?.(errorMsg);
      return { success: false, error: errorMsg };
    }
  }, [onError]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    restarting,
    error,
    pollCount,
    initiateRestart,
    clearError
  };
};

export default useSystemRestart;
