import React, { useEffect, useRef, useState } from 'react';
import { Box, Button, Collapse, Stack, Typography } from '@mui/material';
import RestoreIcon from '@mui/icons-material/Restore';
import axios from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';
import { useAuthSession } from '../context/AuthSessionContext';

export const validSessionControls = (controls) => Array.isArray(controls) && controls.length <= 8
  && new Set(controls.map((control) => control.control_id)).size === controls.length
  && controls.every((control) => control.control_id && control.label && control.unit
    && ['minimum', 'step', 'value', 'revision'].every((field) => Number.isFinite(control[field]))
    && (control.maximum === null || Number.isFinite(control.maximum))
    && control.minimum >= 0 && control.step > 0 && control.value >= control.minimum
    && (control.maximum === null || control.value <= control.maximum) && Number.isInteger(control.revision) && control.revision >= 0
    && typeof control.available === 'boolean' && typeof control.increase_allowed === 'boolean');

const limitText = (reason) => ({
  descent_limited: 'Minimum altitude: descent limited',
  climb_limited: 'Maximum altitude: climb limited',
  target_recovery: 'Reacquiring: speed increases paused',
  slowing_down: 'Slowing toward the requested speed',
  guidance_limited: 'Guidance, ramp or limits reduce the command',
}[reason] || (reason ? 'Speed adjustment unavailable' : ''));

const controlContext = (snapshot, id) => {
  const control = snapshot?.session_controls?.find((item) => item.control_id === id);
  if (!control?.available || !snapshot.following_active) return null;
  return JSON.stringify([snapshot.instance_id, snapshot.runtime_id, snapshot.follow_session_id,
    snapshot.follow_aircraft_uid, snapshot.follow_connection_generation, id, control.revision]);
};

export const speedText = (value) => Number(value.toFixed(6)).toLocaleString('en', {
  minimumFractionDigits: 1, maximumFractionDigits: 6,
});

export default function FollowerSessionControls({ active }) {
  const { hasScope } = useAuthSession();
  const [status, setStatus] = useState(null);
  const [fresh, setFresh] = useState(false);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState('');
  const [expanded, setExpanded] = useState('');
  const operation = useRef(null);
  const currentStatus = useRef(null);
  const mutationPending = useRef(false);
  const pressed = useRef(null);

  useEffect(() => {
    if (!active) {
      setStatus(null);
      setFresh(false);
      setPending(false);
      setNotice('');
      return undefined;
    }
    let disposed = false;
    let timer;
    let reading = null;
    let mutation = null;
    let revision = 0;
    const read = async () => {
      if (disposed || reading || mutationPending.current || document.hidden) return;
      const controller = new AbortController();
      reading = controller;
      const capturedRevision = revision;
      try {
        const { data } = await axios.get(endpoints.nativeFollowing, { signal: controller.signal, timeout: 3000 });
        if (!disposed && capturedRevision === revision) {
          if (data?.source !== 'native_following_status' || !validSessionControls(data.session_controls ?? [])) {
            throw new Error('Invalid following controls');
          }
          currentStatus.current = data;
          setStatus(data);
          setFresh(true);
        }
      } catch (error) {
        if (!disposed && capturedRevision === revision) {
          currentStatus.current = null;
          setFresh(false);
        }
      } finally {
        reading = null;
      }
    };
    operation.current = async (controlId, direction, context) => {
      if (disposed || mutationPending.current || document.hidden) return;
      const snapshot = currentStatus.current;
      if (!context || context !== controlContext(snapshot, controlId)) return;
      const control = snapshot?.session_controls?.find((item) => item.control_id === controlId);
      if (!control?.available || !snapshot.following_active || (direction > 0 && !control.increase_allowed)) return;
      const reset = direction === 0;
      if (reset && (!control.reset_supported || !control.override_active)) return;
      const value = reset ? null : Math.max(control.minimum,
        Math.min(control.maximum ?? Infinity, control.value + direction * control.step));
      if (!reset && (!Number.isFinite(value) || value === control.value)) return;
      mutationPending.current = true;
      revision += 1;
      reading?.abort();
      setPending(true);
      setNotice('');
      mutation = new AbortController();
      try {
        const { data } = await axios.post(endpoints.followingControlAction, {
          ...buildActionRequest('adjust_following_speed'),
          instance_id: snapshot.instance_id, runtime_id: snapshot.runtime_id,
          follow_session_id: snapshot.follow_session_id,
          aircraft_uid: snapshot.follow_aircraft_uid,
          connection_generation: snapshot.follow_connection_generation,
          control_id: controlId, value, expected_revision: control.revision,
        }, { signal: mutation.signal, timeout: 5000 });
        if (data?.action_type !== 'following_control_set' || data.executed !== true || data.status !== 'success') {
          throw new Error('Adjustment was not acknowledged');
        }
      } catch (error) {
        if (!disposed) setNotice(error.response?.status === 409
          ? 'Speed or session changed. Review the current value and tap again.'
          : 'Adjustment was not confirmed. Refreshing status.');
      } finally {
        if (!disposed) {
          revision += 1;
          reading?.abort();
          mutationPending.current = false;
          currentStatus.current = null;
          setPending(false);
          setFresh(false);
          await read();
        }
      }
    };
    const visibility = () => {
      revision += 1;
      pressed.current = { cancelled: true };
      currentStatus.current = null;
      setFresh(false);
      reading?.abort();
      if (!document.hidden) read();
    };
    read();
    timer = setInterval(read, 1000);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      disposed = true;
      revision += 1;
      clearInterval(timer);
      reading?.abort();
      mutation?.abort();
      operation.current = null;
      mutationPending.current = false;
      currentStatus.current = null;
      pressed.current = null;
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [active]);

  const press = (id, direction) => {
    pressed.current = { id, direction, context: controlContext(currentStatus.current, id) };
  };
  const adjustmentHandlers = (id, direction) => ({
    onPointerDown: () => press(id, direction),
    onPointerCancel: () => { pressed.current = { cancelled: true }; },
    onBlur: () => {
      if (pressed.current?.id === id && pressed.current.direction === direction) pressed.current = { cancelled: true };
    },
    onKeyDown: (event) => {
      if (event.key === ' ' || event.key === 'Enter') {
        if (event.repeat) event.preventDefault();
        else press(id, direction);
      }
    },
    onClick: (event) => {
      const intent = pressed.current;
      pressed.current = null;
      // Assistive technology can activate a button without a preceding press.
      const context = intent?.id === id && intent.direction === direction ? intent.context
        : !intent && event.detail === 0 ? controlContext(currentStatus.current, id) : null;
      operation.current?.(id, direction, context);
    },
  });
  if (!active || !status?.following_active) return null;
  return <Box>
    {(status.session_controls || []).map((control) => {
      const disabled = !fresh || pending || !control.available || !hasScope('actions:execute');
      return <Box key={control.control_id} sx={{ mt: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" sx={{ flex: 1 }}>{control.label}</Typography>
          <Button variant="outlined" sx={{ minWidth: 44, minHeight: 44 }} disabled={disabled || control.value <= control.minimum}
            aria-label={`Decrease requested speed by ${control.step} ${control.unit}`}
            {...adjustmentHandlers(control.control_id, -1)}>−</Button>
          <Button sx={{ minHeight: 44 }} aria-label={`Requested 3D speed ${speedText(control.value)} ${control.unit}, this session. Show details`}
            aria-expanded={expanded === control.control_id}
            onClick={() => setExpanded(expanded === control.control_id ? '' : control.control_id)}>
            {speedText(control.value)} {control.unit}
          </Button>
          <Button variant="outlined" sx={{ minWidth: 44, minHeight: 44 }}
            disabled={disabled || !control.increase_allowed || (control.maximum !== null && control.value >= control.maximum)}
            aria-label={`Increase requested speed by ${control.step} ${control.unit}`}
            {...adjustmentHandlers(control.control_id, 1)}>+</Button>
          {control.reset_supported && <Button sx={{ minWidth: 44, minHeight: 44 }}
            color={control.override_active ? 'warning' : 'inherit'}
            disabled={disabled || !control.override_active}
            aria-label="Restore configured velocity limits"
            title="Restore saved velocity limits; keep or lower the requested speed"
            {...adjustmentHandlers(control.control_id, 0)}><RestoreIcon /></Button>}
        </Stack>
        <Collapse in={expanded === control.control_id}>
          <Typography variant="caption" component="p">3D request · this session.
            {control.reset_supported ? ` Velocity override ${control.override_active ? 'active' : 'inactive'}; configured ceiling ${control.configured_maximum} ${control.unit}. Altitude and rate protections remain unchanged.`
              : control.maximum === null ? ' No configured velocity ceiling.' : ` Maximum ${control.maximum} ${control.unit}.`}
            {' '}Zero stops translation; use Stop Following to end the session.
            {Number.isFinite(control.effective_command_magnitude)
              ? ` Command: ${control.effective_command_magnitude.toFixed(1)} ${control.unit}.` : ''}
          </Typography>
        </Collapse>
        <Typography variant="caption" role="status">{pending ? 'Updating…' : !fresh ? 'Refreshing…'
          : limitText(control.limiting_reason || control.reason_code)}</Typography>
      </Box>;
    })}
    {notice && <Typography variant="caption" role="status">{notice}</Typography>}
  </Box>;
}
