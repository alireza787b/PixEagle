import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import SystemUpdateAltIcon from '@mui/icons-material/SystemUpdateAlt';
import { Link } from 'react-router-dom';
import { apiFetchJson } from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';

const stages = {
  review_settings: 'Review settings before updating', queued: 'Starting update', downloading: 'Downloading release', preparing: 'Checking your settings',
  updating: 'Updating PixEagle', restarting: 'Restarting and checking PixEagle',
  restoring: 'Restoring the previous version', updated: 'Update complete',
  restored: 'Previous version restored', failed: 'Update stopped', recovery_required: 'Recovery required',
};
const finished = new Set(['updated', 'restored', 'failed', 'recovery_required', 'review_settings']);

function requestKey() {
  return Array.from(window.crypto.getRandomValues(new Uint8Array(16)),
    (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export default function SoftwareUpdatePage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [connectionLost, setConnectionLost] = useState(false);
  const fetching = useRef(false);
  const mounted = useRef(true);
  const key = useRef(null);
  const job = status?.job;
  const active = Boolean(job && !finished.has(job.stage));
  const load = useCallback(async (refresh = false) => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const data = await apiFetchJson(endpoints.softwareUpdate + (refresh ? '?refresh=true' : ''));
      if (mounted.current) {
        setStatus(data);
        setConnectionLost(false);
        setError('');
      }
    } catch (failure) {
      if (mounted.current) {
        setConnectionLost(!failure.response);
        if (failure.response) setError(failure.message || 'Could not read software update status.');
      }
    } finally {
      fetching.current = false;
    }
  }, []);
  useEffect(() => {
    mounted.current = true;
    load();
    return () => { mounted.current = false; };
  }, [load]);
  useEffect(() => {
    if (!active && !connectionLost) return undefined;
    const timer = setInterval(() => { setNow(Date.now()); load(); }, 2500);
    return () => clearInterval(timer);
  }, [active, connectionLost, load]);
  const install = async () => {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      key.current ??= requestKey();
      const next = await apiFetchJson(endpoints.installSoftwareUpdate, { method: 'POST',
        body: JSON.stringify({ commit: status.commit, review: status.review,
          confirm: true, save_edits: confirm, migration: job?.stage === 'review_settings' ? job.migration : null, idempotency_key: key.current }) });
      setStatus((old) => ({ ...old, job: next }));
      setNow(Date.now());
      setConfirm(false);
      key.current = null;
    } catch (failure) {
      await load();
      setError(failure.message || 'Could not start the update.');
    } finally {
      setBusy(false);
    }
  };
  const summary = { current: 'Up to date', ahead: 'Ahead of the latest stable release',
    different: 'Local revision differs from the stable release', available: 'Update available', unknown: 'Release unconfirmed' };
  return <Box sx={{ maxWidth: 680, mx: 'auto', p: { xs: 1, sm: 3 } }}>
    <Stack direction="row" alignItems="center" spacing={1} mb={2}>
      <SystemUpdateAltIcon color="primary" /><Typography variant="h5" component="h1">Software update</Typography>
    </Stack>
    <Card variant="outlined"><CardContent><Stack spacing={2}>
      {status && <>
        <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Typography variant="h6">PixEagle {status.installed}</Typography>
          <Chip size="small" label={summary[status.state]} />
        </Stack>
        {status.release && <Typography>Latest stable release · <strong>{status.release}</strong>
          {' · '}<Button component="a" href={status.notes} target="_blank" rel="noreferrer" size="small">Release notes</Button>
        </Typography>}
        <Typography variant="body2" color="text.secondary">{status.checked
          ? 'Last checked ' + new Date(status.checked * 1000).toLocaleString() : 'No successful release check yet'}</Typography>
        {status.error && <Alert severity="warning">{status.error}</Alert>}
      </>}
      {!status && !connectionLost && !error && <LinearProgress aria-label="Checking for updates" />}
      {connectionLost && <Alert severity="info">Waiting for PixEagle to reconnect…</Alert>}
      {job && <Box role="status">
        <Typography variant="subtitle1">{stages[job.stage]} · {job.release}</Typography>
        {active && <><LinearProgress sx={{ my: 1 }} />
          <Typography variant="caption">{Math.max(0, Math.floor(now / 1000 - job.started))} s elapsed</Typography></>}
        {job.stage === 'review_settings' && <Box component="ul" sx={{ pl: 3, overflowWrap: 'anywhere' }}>
          {job.settings_changes?.map((row) => <li key={row.path}>{row.path} · {JSON.stringify(row.before)} → {JSON.stringify(row.after)}</li>)}
        </Box>}
        {job.message && <Alert severity={job.stage === 'recovery_required' ? 'error' : 'warning'}>{job.message}</Alert>}
        {job.stash && <Typography variant="body2">Local edits saved · {job.stash.slice(0, 10)}</Typography>}
        {job.stage === 'updated' && job.settings_pending && <Button component={Link}
          to="/settings?review=defaults">Review settings changes</Button>}
        {job.stage === 'failed' && <Button component={Link} to="/settings">Open Settings</Button>}
        {job.stage === 'recovery_required' && <Button component="a"
          href="https://github.com/alireza787b/PixEagle/blob/main/docs/setup/dashboard-updates.md">Recovery guide</Button>}
      </Box>}
      {status?.state === 'available' && !active && <>
        {status.blocked && <Alert severity="info">{status.blocked}</Alert>}
        {!status.blocked && !status.error && <>
          <Typography variant="body2">PixEagle will restart. Your saved settings stay on this device.</Typography>
          {confirm && <Box>
            <Typography variant="subtitle2">Save these local edits before updating?</Typography>
            <Box component="ul" sx={{ maxHeight: 160, overflow: 'auto', overflowWrap: 'anywhere' }}>
              {status.changes.map((name) => <li key={name}>{name}</li>)}
            </Box>
            {status.changes.includes('configs/config_default.yaml') && <Typography variant="body2">
              Edited factory defaults will be backed up. Existing personal settings take priority.
            </Typography>}
          </Box>}
          <Stack direction="row" gap={1} flexWrap="wrap">
            <Button variant="contained" disabled={busy || connectionLost || !status.review}
              onClick={() => status.changes.length && !confirm ? setConfirm(true) : install()}>
              {confirm ? 'Back up edits and update' : job?.stage === 'review_settings' ? 'Apply reviewed settings and update' : 'Update to ' + status.release}</Button>
            {confirm && <Button onClick={() => setConfirm(false)}>Cancel</Button>}
          </Stack>
        </>}
      </>}
      {error && <Alert severity="error">{error}</Alert>}
      {!active && <Button sx={{ alignSelf: 'start' }} disabled={busy} onClick={async () => {
        setBusy(true); setConfirm(false); await load(true); setBusy(false);
      }}>Check now</Button>}
    </Stack></CardContent></Card>
  </Box>;
}
