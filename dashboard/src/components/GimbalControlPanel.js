import React, { useState } from 'react';
import { Alert, Box, Button, ButtonGroup, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Tooltip, Typography } from '@mui/material';
import useGimbalHold from '../hooks/useGimbalHold';

import {
  ArrowBack, ArrowForward, ArrowUpward, ArrowDownward, CenterFocusStrong,
  RotateLeft, RotateRight, Add, Remove, Stop, Close,
} from '@mui/icons-material';

const DIRECTION_PAD = [
  { label: 'Tilt up', operation: 'tilt', direction: -1, Icon: ArrowUpward, row: 1, column: 2 },
  { label: 'Pan left', operation: 'pan', direction: -1, Icon: ArrowBack, row: 2, column: 1 },
  { label: 'Center camera', operation: 'home', Icon: CenterFocusStrong, row: 2, column: 2 },
  { label: 'Pan right', operation: 'pan', direction: 1, Icon: ArrowForward, row: 2, column: 3 },
  { label: 'Tilt down', operation: 'tilt', direction: 1, Icon: ArrowDownward, row: 3, column: 2 },
];
const GROUP_LABEL = { color: 'text.secondary', textAlign: 'center', mb: 0.75 };

const TRACKING_LABELS = {
  target_selection: 'Ready',
  ready: 'Ready',
  tracking_active: 'Tracking',
  target_lost: 'Target lost',
  disabled: 'Disabled',
  unsupported: 'Unsupported',
  unknown: 'Unknown',
};
const REASON_LABELS = {
  camera_unavailable: 'Camera unavailable',
  stop_following_first: 'Stop following first',
  tracking_unsupported: 'Tracking unsupported',
  disabled: 'Disabled',
  application_shutting_down: 'PixEagle is shutting down',
};

export default function GimbalControlPanel({ control }) {
  if (!control.enabled) return null;
  // Polls preserve session choices; a different provider/settings contract resets them.
  const settingsKey = JSON.stringify([control.status.provider, control.status.motion_settings]);
  return <GimbalControlContent key={settingsKey} control={control} />;
}

function GimbalControlContent({ control }) {
  const { status, busy, error, canOperate, execute } = control;
  const settings = status.motion_settings;
  const defaults = settings ? {
    speed_deg_s: settings.default_speed_deg_s, duration_ms: settings.default_duration_ms,
  } : null;
  const [motion, setMotion] = useState(defaults);
  const [draft, setDraft] = useState(null);
  const matchingPreset = settings?.presets.find(preset => preset.speed_deg_s === motion.speed_deg_s
    && preset.duration_ms === motion.duration_ms);
  const validSpeed = draft && Number.isInteger(Number(draft.speed_deg_s)) && draft.speed_deg_s !== ''
    && Number(draft.speed_deg_s) >= settings.min_speed_deg_s && Number(draft.speed_deg_s) <= settings.max_speed_deg_s;
  const validDuration = draft && Number.isInteger(Number(draft.duration_ms)) && draft.duration_ms !== ''
    && Number(draft.duration_ms) >= settings.min_duration_ms && Number(draft.duration_ms) <= settings.max_duration_ms;
  const parametersFor = (operation, direction) => {
    const parameters = direction ? { direction } : {};
    if (motion && ['pan', 'tilt', 'roll'].includes(operation)) Object.assign(parameters, motion);
    return parameters;
  };
  const hold = useGimbalHold(control, parametersFor);
  const move = (operation, direction) => {
    hold.abort(operation !== 'stop');
    const parameters = parametersFor(operation, direction);
    void execute(operation, parameters).catch(() => {});
  };
  const has = operation => status.capabilities?.includes(operation);
  const actionButton = ({ label, operation, direction, Icon, row, column }) => {
    if (!has(operation)) return null;
    const active = direction && hold.activeKey === `${operation}:${direction}`;
    return (
      <Tooltip key={label} title={label} describeChild disableTouchListener>
        <span style={{ display: 'inline-flex', gridRow: row, gridColumn: column }}>
          <Button aria-label={label} variant={active ? 'contained' : 'outlined'}
            disabled={!canOperate(operation) && !active}
            sx={{ minWidth: 44, width: 44, height: 44, p: 0, borderRadius: 1.5,
              bgcolor: active ? undefined : 'background.paper',
              borderColor: active ? 'primary.main' : 'divider',
              color: active ? 'primary.contrastText' : 'text.primary',
              '&:hover': { borderColor: 'primary.main', bgcolor: active ? 'primary.dark' : 'action.hover' },
              touchAction: direction ? 'none' : 'manipulation', userSelect: 'none',
              '&.Mui-focusVisible': { outline: '2px solid', outlineColor: 'primary.main', outlineOffset: 3 } }}
            {...(direction ? hold.handlers(operation, direction) : { onClick: () => move(operation, direction) })}>
            <Icon fontSize="small" />
          </Button>
        </span>
      </Tooltip>
    );
  };
  return (
    <Box sx={{ p: 1.5 }} role="region" aria-label="External gimbal controls">
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2">Gimbal camera</Typography>
        <Chip size="small" label={status.connected ? (TRACKING_LABELS[status.tracking_state] || 'Unknown') : 'Disconnected'} />
        {busy && <CircularProgress size={14} aria-label="Sending command" />}
      </Stack>
      <Stack direction="row" spacing={1.5} useFlexGap flexWrap="wrap" alignItems="center" sx={{ mb: 1.5 }}>
        {has('set_mode') && (
          <ButtonGroup size="small" aria-label="Camera tracking mode">
            {[['classic', 'Classic Tracker'], ['smart', 'Smart Tracker']].map(([mode, label]) => (
              <Button key={mode} aria-label={label}
                sx={{ minHeight: 44, textTransform: 'none' }}
                variant={(status.selection_mode || 'classic') === mode ? 'contained' : 'outlined'}
                aria-pressed={(status.selection_mode || 'classic') === mode}
                disabled={!canOperate('set_mode')}
                onClick={() => { void execute('set_mode', { selection_mode: mode }).catch(() => {}); }}>
                {mode === 'classic' ? 'Classic' : 'Smart'}
              </Button>
            ))}
          </ButtonGroup>
        )}
        {settings && <TextField select size="small" label="Movement"
          SelectProps={{ native: true }} value={matchingPreset?.name || 'custom'}
          sx={{ minWidth: 126, '& .MuiInputBase-root': { minHeight: 44 } }}
          onChange={event => {
            hold.abort();
            if (event.target.value === 'adjust') setDraft({ ...motion });
            else {
              const preset = settings.presets.find(item => item.name === event.target.value);
              if (preset) setMotion({ speed_deg_s: preset.speed_deg_s, duration_ms: preset.duration_ms });
            }
          }}>
          {settings.presets.map(preset => <option key={preset.name} value={preset.name}>{preset.label}</option>)}
          {!matchingPreset && <option value="custom">Custom</option>}
          <option value="adjust">Adjust…</option>
        </TextField>}
      </Stack>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2 }}>
        {(has('pan') || has('tilt') || has('home')) && <Box role="group" aria-label="Pan and tilt">
          <Typography variant="caption" component="div" sx={GROUP_LABEL}>Pan / tilt</Typography>
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 44px)',
            gridTemplateRows: 'repeat(3, 44px)', gap: '6px',
            bgcolor: 'action.hover', borderRadius: '50%' }}>
            {DIRECTION_PAD.map(actionButton)}
          </Box>
        </Box>}
        {(has('roll') || has('zoom')) && <Stack spacing={1.5} alignItems="center">
          {has('roll') && <Box role="group" aria-label="Roll">
            <Typography variant="caption" component="div" sx={GROUP_LABEL}>Roll</Typography>
            <Stack direction="row" spacing={1}>
              {actionButton({ label: 'Roll −', operation: 'roll', direction: -1, Icon: RotateLeft })}
              {actionButton({ label: 'Roll +', operation: 'roll', direction: 1, Icon: RotateRight })}
            </Stack>
          </Box>}
          {has('zoom') && <Stack role="group" aria-label="Zoom" alignItems="center" spacing={0.25}>
            {actionButton({ label: 'Zoom in', operation: 'zoom', direction: 1, Icon: Add })}
            <Typography variant="caption" color="text.secondary">Zoom</Typography>
            {actionButton({ label: 'Zoom out', operation: 'zoom', direction: -1, Icon: Remove })}
          </Stack>}
        </Stack>}
        {(has('cancel') || has('stop')) && <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1}
          sx={{ borderTop: '1px solid', borderColor: 'divider', pt: 1.5, width: '100%' }}>
          {has('cancel') && <Button aria-label="Cancel target" startIcon={<Close />} variant="outlined"
            disabled={!canOperate('cancel')} sx={{ minHeight: 44, textTransform: 'none' }}
            onClick={() => move('cancel')}>Cancel target</Button>}
          {has('stop') && <Button aria-label="Stop camera" startIcon={<Stop />} variant="contained" color="warning"
            disabled={!canOperate('stop')} sx={{ minHeight: 44, textTransform: 'none', boxShadow: 'none' }}
            onClick={() => move('stop')}>Stop</Button>}
        </Stack>}
      </Box>
      {status.following_active && !error && !status.reason &&
        <Alert severity="info" sx={{ mt: 1 }}>Stop following before selecting a target or moving the camera.</Alert>}
      {settings && <Dialog open={draft !== null} onClose={() => setDraft(null)}
        fullWidth maxWidth="xs" aria-labelledby="gimbal-movement-title">
        <DialogTitle id="gimbal-movement-title">Adjust camera movement</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            A tap makes one timed step. Holding repeats steps until released.
            A step already sent may finish; Stop camera requests an early stop.
            Changes apply for this session; zoom speed is unchanged.
          </Typography>
          <Stack spacing={2} sx={{ pt: 0.5 }}>
            <TextField label="Speed (°/s)" type="number" value={draft?.speed_deg_s ?? ''}
              inputProps={{ min: settings.min_speed_deg_s, max: settings.max_speed_deg_s, step: 1 }}
              error={Boolean(draft && !validSpeed)}
              helperText={`${settings.min_speed_deg_s}–${settings.max_speed_deg_s} °/s, whole numbers`}
              onChange={event => setDraft(previous => ({ ...previous, speed_deg_s: event.target.value }))} />
            <TextField label="Pulse duration (ms)" type="number" value={draft?.duration_ms ?? ''}
              inputProps={{ min: settings.min_duration_ms, max: settings.max_duration_ms, step: 1 }}
              error={Boolean(draft && !validDuration)}
              helperText={`${settings.min_duration_ms}–${settings.max_duration_ms} ms, whole numbers`}
              onChange={event => setDraft(previous => ({ ...previous, duration_ms: event.target.value }))} />
            <Typography variant="body2" role="status">
              {validSpeed && validDuration
                ? `Estimated movement: ${Number((Number(draft.speed_deg_s) * Number(draft.duration_ms) / 1000).toFixed(2))}° per press. `
                : ''}
              This is a speed pulse, not exact positioning.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ flexWrap: 'wrap' }}>
          <Button onClick={() => setDraft(defaults)}>Reset to Normal</Button>
          <Button onClick={() => setDraft(null)}>Cancel</Button>
          <Button variant="contained" disabled={!validSpeed || !validDuration}
            onClick={() => {
              setMotion({ speed_deg_s: Number(draft.speed_deg_s), duration_ms: Number(draft.duration_ms) });
              setDraft(null);
            }}>Apply</Button>
        </DialogActions>
      </Dialog>}
      {(error || status.reason) && <Alert severity={error ? 'error' : 'info'} sx={{ mt: 1 }}>{error || REASON_LABELS[status.reason] || status.reason}</Alert>}
    </Box>
  );
}
