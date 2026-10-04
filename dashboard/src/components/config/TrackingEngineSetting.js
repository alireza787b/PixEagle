import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Paper, Select, Typography } from '@mui/material';
import axios from '../../services/apiClient';
import { endpoints } from '../../services/apiEndpoints';
import { buildActionRequest } from '../../services/actionRequests';
import { useAvailableTrackers, useCurrentTracker } from '../../hooks/useTrackerSchema';

const engineOf = (entry) => entry?.target_engine === 'camera' ? 'camera' : 'local';

const TrackingEngineSetting = () => {
  const { trackers, error: catalogError, refetch: refetchTrackers } = useAvailableTrackers();
  const { currentTracker, refetch: refetchCurrent } = useCurrentTracker();
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [savedEngine, setSavedEngine] = useState('');

  useEffect(() => {
    let active = true;
    const refreshSavedEngine = async () => {
      try {
        const response = await axios.get(endpoints.nativeTargetState);
        if (active) setSavedEngine(response.data?.saved_engine || '');
      } catch (_) {
        if (active) setSavedEngine('');
      }
    };
    refreshSavedEngine();
    const timer = setInterval(refreshSavedEngine, 4000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  const entries = useMemo(() => Object.values(trackers?.available_trackers || {}), [trackers]);
  const current = entries.find((entry) => (
    [entry.name, entry.request_tracker_type, entry.factory_key].includes(currentTracker?.tracker_type)
  ));
  const currentEngine = current ? engineOf(current) : '';
  const choice = selected || currentEngine;
  const saveNeeded = savedEngine && savedEngine !== currentEngine;
  const engines = ['local', 'camera'].map((id) => ({
    id,
    label: id === 'local' ? 'PixEagle' : 'Camera',
    candidate: entries.find((entry) => engineOf(entry) === id && !entry.smart_mode && entry.available)
      || (id === currentEngine && saveNeeded
        ? entries.find((entry) => engineOf(entry) === id && !entry.smart_mode) : null),
  }));

  const apply = async () => {
    const engine = engines.find((row) => row.id === choice);
    if (!engine?.candidate || busy || (choice === currentEngine && !saveNeeded)) return;
    setBusy(true);
    setNotice('');
    try {
      const [contextResponse, targetResponse] = await Promise.all([
        axios.get(endpoints.nativeIntegrationContext),
        axios.get(endpoints.nativeTargetState),
      ]);
      const context = contextResponse.data;
      const target = targetResponse.data;
      setSavedEngine(target?.saved_engine || '');
      if (!target?.allowed_actions?.includes('tracker_switch')) {
        throw new Error('Stop following and refresh the tracker before changing engines.');
      }
      const aircraftPresent = context?.command?.connected || context?.telemetry?.connected;
      if (aircraftPresent && !context?.association?.verified) {
        throw new Error('Verify the aircraft association before changing tracking engines.');
      }
      const response = await axios.post(endpoints.trackerSwitchAction, {
        ...buildActionRequest('switch_tracking_engine', { ui: 'dashboard_advanced_settings' }),
        tracker_type: engine.candidate.request_tracker_type || engine.candidate.name,
        persist: true,
        restore_engine_selection: true,
        native_context: {
          binding_mode: aircraftPresent ? 'vehicle' : 'companion_only',
          guard: target.guard,
        },
      });
      const result = response.data?.result?.legacy_result;
      if (response.data?.status !== 'success' || result?.saved !== true) {
        throw new Error(result?.message || 'PixEagle did not confirm the saved tracking engine.');
      }
      setSelected('');
      setNotice('Applied and saved. Select a new target to resume tracking.');
      await Promise.all([refetchTrackers(), refetchCurrent()]);
      const saved = await axios.get(endpoints.nativeTargetState);
      setSavedEngine(saved.data?.saved_engine || '');
    } catch (error) {
      setNotice(error?.response?.data?.detail?.message || error?.message || 'Tracking engine change failed.');
      await Promise.all([refetchTrackers(), refetchCurrent()]);
      try {
        const current = await axios.get(endpoints.nativeTargetState);
        setSavedEngine(current.data?.saved_engine || '');
      } catch (_) {
        setSavedEngine('');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
      <Typography variant="subtitle1">Tracking runs on</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Advanced setting. A change applies now and becomes the startup choice. Video input and camera controls are separate.
      </Typography>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel id="tracking-engine-label">Engine</InputLabel>
          <Select labelId="tracking-engine-label" label="Engine" value={choice} onChange={(event) => setSelected(event.target.value)}>
            {engines.map((engine) => (
              <MenuItem key={engine.id} value={engine.id} disabled={!engine.candidate}>
                {engine.label}{!engine.candidate ? ' (unavailable)' : ''}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button variant="outlined" disabled={busy || !choice || (choice === currentEngine && !saveNeeded) || !engines.find((row) => row.id === choice)?.candidate}
          onClick={apply}>
          {busy ? 'Applying…' : choice === currentEngine ? 'Retry save' : 'Apply and save'}
        </Button>
      </Box>
      {saveNeeded && <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>
        Current engine differs from the saved startup choice.
      </Typography>}
      {(notice || catalogError) && <Alert severity={catalogError ? 'warning' : notice.startsWith('Applied') ? 'success' : 'warning'} sx={{ mt: 1.5 }}>
        {notice || catalogError}
      </Alert>}
    </Paper>
  );
};

export default TrackingEngineSetting;
