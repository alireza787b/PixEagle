import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';

const STATUS_POLL_INTERVAL_MS = 5000;
const RECONNECT_INITIAL_DELAY_MS = 3000;
const RECONNECT_POLL_INTERVAL_MS = 1000;
const MAX_RECONNECT_ATTEMPTS = 30;

const PendingRestartContext = createContext(null);

const delay = (durationMs) => new Promise((resolve) => {
  setTimeout(resolve, durationMs);
});

const getErrorMessage = (error, fallback) => (
  error?.data?.detail?.message
  || error?.data?.detail
  || error?.message
  || fallback
);

export const isSystemRestartPending = (runtimeStatus) => (
  runtimeStatus?.restart_required === true
);

const validateRuntimeStatus = (runtimeStatus) => {
  if (
    !runtimeStatus
    || typeof runtimeStatus !== 'object'
    || typeof runtimeStatus.restart_required !== 'boolean'
    || typeof runtimeStatus.startup_snapshot_timestamp !== 'number'
    || !Array.isArray(runtimeStatus.pending_changes)
    || typeof runtimeStatus.restart_action?.available !== 'boolean'
  ) {
    throw new Error('Config runtime status response is malformed.');
  }
  return runtimeStatus;
};

export const PendingRestartProvider = ({
  children,
  statusPollIntervalMs = STATUS_POLL_INTERVAL_MS,
  reconnectInitialDelayMs = RECONNECT_INITIAL_DELAY_MS,
  reconnectPollIntervalMs = RECONNECT_POLL_INTERVAL_MS,
  maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS,
}) => {
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [error, setError] = useState(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadRuntimeStatus = useCallback(async () => {
    const nextStatus = validateRuntimeStatus(
      await apiFetchJson(endpoints.configRuntimeStatus)
    );
    if (mountedRef.current) {
      setRuntimeStatus(nextStatus);
    }
    return nextStatus;
  }, []);

  const refreshRuntimeStatus = useCallback(async () => {
    if (mountedRef.current) {
      setStatusLoading(true);
    }
    try {
      const nextStatus = await loadRuntimeStatus();
      if (mountedRef.current) {
        setError(null);
      }
      return nextStatus;
    } catch (statusError) {
      if (mountedRef.current) {
        setError(getErrorMessage(statusError, 'Unable to read config runtime status.'));
      }
      throw statusError;
    } finally {
      if (mountedRef.current) {
        setStatusLoading(false);
      }
    }
  }, [loadRuntimeStatus]);

  useEffect(() => {
    if (restarting) return undefined;

    refreshRuntimeStatus().catch(() => {});
    if (!Number.isFinite(statusPollIntervalMs) || statusPollIntervalMs <= 0) {
      return undefined;
    }

    const interval = setInterval(() => {
      refreshRuntimeStatus().catch(() => {});
    }, statusPollIntervalMs);
    return () => clearInterval(interval);
  }, [refreshRuntimeStatus, restarting, statusPollIntervalMs]);

  const pendingRestart = isSystemRestartPending(runtimeStatus);
  const statusUnavailable = runtimeStatus === null && Boolean(error);
  const restartActionAvailable = (
    pendingRestart
    && runtimeStatus?.restart_action?.available === true
  );

  const requestRestartConfirmation = useCallback(() => {
    setConfirmationOpen(true);
    refreshRuntimeStatus().catch(() => {});
  }, [refreshRuntimeStatus]);

  const closeRestartConfirmation = useCallback(() => {
    setConfirmationOpen(false);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const restartNow = useCallback(async () => {
    if (!restartActionAvailable || restarting) {
      return {
        success: false,
        error: 'System restart is not available for the current runtime.',
      };
    }

    setRestarting(true);
    setReconnectAttempt(0);
    setError(null);
    setConfirmationOpen(false);

    try {
      const priorStartupTimestamp = runtimeStatus.startup_snapshot_timestamp;
      const action = await apiFetchJson(endpoints.systemRestartAction, {
        method: 'POST',
        body: JSON.stringify(buildActionRequest(
          'apply_pending_config_restart',
          { ui: 'dashboard_pending_restart_banner' }
        )),
      });

      if (action?.status !== 'success' || action?.accepted !== true) {
        throw new Error(action?.error || 'System restart action was not accepted.');
      }

      await delay(reconnectInitialDelayMs);

      let lastReconnectError = null;
      for (let attempt = 1; attempt <= maxReconnectAttempts; attempt += 1) {
        if (!mountedRef.current) {
          return { success: false, error: 'Restart status polling was cancelled.' };
        }

        setReconnectAttempt(attempt);
        try {
          const nextStatus = await loadRuntimeStatus();
          if (nextStatus.startup_snapshot_timestamp !== priorStartupTimestamp) {
            if (mountedRef.current) {
              setRestarting(false);
              setReconnectAttempt(0);
              setError(null);
            }
            return { success: true, runtimeStatus: nextStatus };
          }
          lastReconnectError = new Error('Waiting for the restarted PixEagle process.');
        } catch (pollError) {
          lastReconnectError = pollError;
        }

        if (attempt < maxReconnectAttempts) {
          await delay(reconnectPollIntervalMs);
        }
      }

      throw new Error(getErrorMessage(
        lastReconnectError,
        'PixEagle did not reconnect within the expected time.'
      ));
    } catch (restartError) {
      const message = getErrorMessage(restartError, 'Failed to restart PixEagle.');
      if (mountedRef.current) {
        setRestarting(false);
        setReconnectAttempt(0);
        setError(message);
      }
      return { success: false, error: message };
    }
  }, [
    loadRuntimeStatus,
    maxReconnectAttempts,
    reconnectInitialDelayMs,
    reconnectPollIntervalMs,
    restartActionAvailable,
    restarting,
    runtimeStatus,
  ]);

  const value = useMemo(() => ({
    runtimeStatus,
    pendingRestart,
    restartActionAvailable,
    confirmationOpen,
    restarting,
    reconnectAttempt,
    error,
    statusLoading,
    statusUnavailable,
    refreshRuntimeStatus,
    requestRestartConfirmation,
    closeRestartConfirmation,
    restartNow,
    clearError,
  }), [
    runtimeStatus,
    pendingRestart,
    restartActionAvailable,
    confirmationOpen,
    restarting,
    reconnectAttempt,
    error,
    statusLoading,
    statusUnavailable,
    refreshRuntimeStatus,
    requestRestartConfirmation,
    closeRestartConfirmation,
    restartNow,
    clearError,
  ]);

  return (
    <PendingRestartContext.Provider value={value}>
      {children}
    </PendingRestartContext.Provider>
  );
};

export const usePendingRestart = () => {
  const context = useContext(PendingRestartContext);
  if (!context) {
    throw new Error('usePendingRestart must be used within PendingRestartProvider.');
  }
  return context;
};
