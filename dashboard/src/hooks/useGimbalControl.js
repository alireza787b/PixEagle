import { useCallback, useRef, useState } from 'react';
import { useSerialPolling } from './useStatuses';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';

export default function useGimbalControl(canExecuteActions) {
  const [status, setStatus] = useState(null);
  const statusRef = useRef(null);
  const permission = useRef(canExecuteActions);
  permission.current = canExecuteActions;
  const publishStatus = useCallback(next => {
    statusRef.current = typeof next === 'function' ? next(statusRef.current) : next;
    setStatus(statusRef.current);
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [stopping, setStopping] = useState(false);
  const pendingStops = useRef(0);
  const busyRef = useRef(false);
  const commandGeneration = useRef(0);
  const clientId = useRef(null);
  if (!clientId.current) clientId.current = window.crypto?.randomUUID?.() || `dashboard-${Date.now()}-${Math.random()}`;
  const captureContext = () => statusRef.current?.guard
    ? { guard: statusRef.current.guard, client_id: clientId.current } : null;
  const poll = useCallback(async (_options, { isCurrent }) => {
    const generation = commandGeneration.current;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    try {
      const data = await apiFetchJson(endpoints.gimbalControl, { cache: 'no-store', signal: controller.signal });
      if (isCurrent() && generation === commandGeneration.current) publishStatus(data);
    } catch {
      // Retain enabled mode after a disconnect; never fall back to a local tracker.
      if (isCurrent() && generation === commandGeneration.current) publishStatus(previous => previous && ({
        ...previous, available: false, connected: false,
        reason: 'Camera control status is unavailable.',
      }));
    } finally {
      clearTimeout(timeout);
    }
  }, [publishStatus]);
  const refresh = useSerialPolling(poll, 1000);
  const enabled = status?.enabled === true;
  const canOperate = operation => {
    const current = statusRef.current;
    const selectDuringFollow = operation === 'select' && current?.following_active === true
      && current?.reason === 'stop_following_first' && current?.connected === true;
    return current?.enabled === true && permission.current
      && current.capabilities?.includes(operation)
      && (operation === 'stop' || (
        !busyRef.current && pendingStops.current === 0
        && (selectDuringFollow || (current.following_active === false
          && (operation === 'cancel' || (current.available === true && current.connected === true))))
      ));
  };

  const execute = async (operation, parameters = {}, options = {}) => {
    const manual = ['manual_begin', 'manual_update'].includes(operation);
    if (!canOperate(operation) || ((busyRef.current || pendingStops.current > 0) && operation !== 'stop')) {
      throw new Error('Camera control is currently unavailable.');
    }
    if (operation !== 'manual_update') commandGeneration.current += 1;
    const generation = commandGeneration.current;
    const isCurrent = () => generation === commandGeneration.current && (options.isCurrent?.() ?? true);
    const ownsBusy = operation !== 'stop' && !manual;
    if (ownsBusy) { busyRef.current = true; setBusy(true); }
    if (operation === 'stop') { pendingStops.current += 1; setStopping(true); }
    if (!options.preserveError) setError(null);
    try {
      const result = await apiFetchJson(endpoints.gimbalControlAction, {
        method: 'POST',
        body: JSON.stringify({
          ...buildActionRequest(`gimbal_${operation}`, { ui: 'dashboard_gimbal_control' }),
          operation, ...parameters,
          ...(!['select', 'cancel', 'set_mode'].includes(operation) && statusRef.current?.guard
            ? { camera_context: parameters.camera_context || captureContext() } : {}),
        }),
      });
      if (result?.status === 'failure' || result?.result?.manual?.state === 'failed') {
        const failure = new Error(result.result?.message || result.result?.error || result.error || result.message || 'Camera command failed.');
        failure.interrupted = result.result?.reason === 'camera_control_interrupted';
        throw failure;
      }
      if (manual) {
        if (isCurrent() && result.result?.manual) {
          publishStatus(previous => previous && ({ ...previous, manual: result.result.manual }));
        }
      } else if (isCurrent()) {
        if (result.result?.camera_status) publishStatus(result.result.camera_status);
        else await refresh();
      }
      return result;
    } catch (commandError) {
      if (isCurrent() && !commandError.interrupted) setError(commandError.message || 'Camera command failed.');
      throw commandError;
    } finally {
      if (ownsBusy) { busyRef.current = false; setBusy(false); }
      if (operation === 'stop') { pendingStops.current -= 1; setStopping(pendingStops.current > 0); }
    }
  };
  return { status, enabled, busy: busy || stopping, error, canOperate, execute, captureContext };
}
