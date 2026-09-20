import { useCallback, useRef, useState } from 'react';
import { useSerialPolling } from './useStatuses';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';

export default function useGimbalControl(canExecuteActions) {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const busyRef = useRef(false);
  const poll = useCallback(async (_options, { isCurrent }) => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const data = await apiFetchJson(endpoints.gimbalControl, { cache: 'no-store', signal: controller.signal });
      if (isCurrent()) setStatus(data);
    } catch {
      // Retain enabled mode after a disconnect; never fall back to a local tracker.
      if (isCurrent()) setStatus(previous => previous && ({
        ...previous, available: false, connected: false,
        reason: 'Camera control status is unavailable.',
      }));
    } finally {
      clearTimeout(timeout);
    }
  }, []);
  const refresh = useSerialPolling(poll, 1000);
  const enabled = status?.enabled === true;
  const canOperate = operation => enabled && canExecuteActions
    && status?.capabilities?.includes(operation)
    && (operation === 'stop' || (
      status?.following_active === false && !busy
      && (operation === 'cancel' || (status?.available === true && status?.connected === true))
    ));

  const execute = async (operation, parameters = {}) => {
    if (!canOperate(operation) || (busyRef.current && operation !== 'stop')) {
      throw new Error('Camera control is currently unavailable.');
    }
    const ownsBusy = operation !== 'stop';
    if (ownsBusy) { busyRef.current = true; setBusy(true); }
    setError(null);
    try {
      const result = await apiFetchJson(endpoints.gimbalControlAction, {
        method: 'POST',
        body: JSON.stringify({
          ...buildActionRequest(`gimbal_${operation}`, { ui: 'dashboard_gimbal_control' }),
          operation, ...parameters,
        }),
      });
      if (result?.status === 'failure') {
        const failure = new Error(result.result?.message || result.result?.error || result.error || result.message || 'Camera command failed.');
        failure.interrupted = result.result?.reason === 'camera_control_interrupted';
        throw failure;
      }
      await refresh();
      return result;
    } catch (commandError) {
      if (!commandError.interrupted) setError(commandError.message || 'Camera command failed.');
      throw commandError;
    } finally {
      if (ownsBusy) { busyRef.current = false; setBusy(false); }
    }
  };
  return { status, enabled, busy, error, canOperate, execute };
}
