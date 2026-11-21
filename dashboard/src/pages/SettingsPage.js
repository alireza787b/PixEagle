import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useBeforeUnload } from 'react-router-dom';
import {
  Alert, Box, Button, Container, Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, List, ListItemButton, ListItemIcon, ListItemText, Menu, MenuItem, Paper,
  Stack, TextField, Typography,
} from '@mui/material';
import {
  ArrowForward, Checklist, FileDownload, GpsFixed, History, MoreHoriz, Navigation,
  Router, Settings, Shield, Tune, Undo, Videocam,
} from '@mui/icons-material';
import SectionEditor, { settingLabel, touchControls } from '../components/config/SectionEditor';
import ExportDialog from '../components/config/ExportDialog';
import SyncWithDefaultsDialog from '../components/config/SyncWithDefaultsDialog';
import { useConfigSchema } from '../hooks/useConfig';
import { useDefaultsSync } from '../hooks/useDefaultsSync';
import { usePendingRestart } from '../context/PendingRestartContext';
import { apiFetchJson } from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';
import { endpoints } from '../services/apiEndpoints';
import { isPlainObject } from '../utils/configEditorSchemaUtils';

const categoryIcons = {
  video: Videocam, tracking: GpsFixed, network: Router, follower: Navigation,
  safety: Shield, control: Tune,
};
const commonSections = ['VideoSource', 'Streaming', 'Tracking', 'Follower', 'Safety'];
const errorText = (error) => error?.data?.message || error?.message || 'The request failed.';
const pathKey = (path) => JSON.stringify(path);
const atPath = (value, path) => path.reduce((current, key) => current &&
  Object.hasOwn(current, key) ? current[key] : undefined, value);

function leafEdits(previous, value, path) {
  if (isPlainObject(value) && (isPlainObject(previous) || previous === undefined)) {
    const before = previous || {};
    return [...new Set([...Object.keys(before), ...Object.keys(value)])].flatMap((key) =>
      leafEdits(before[key], value[key], [...path, key]));
  }
  if (JSON.stringify(previous) === JSON.stringify(value)) return [];
  return value === undefined ? [{ path, unset: true }] : [{ path, value }];
}

function restoreLeaf(object, path, original) {
  if (!path.length) return original;
  const [key, ...rest] = path;
  const next = { ...object };
  const value = restoreLeaf(next[key], rest, original);
  if (value === undefined) delete next[key];
  else next[key] = value;
  return next;
}

function changeMetadata(schema, path) {
  const [section, ...keys] = path;
  const root = schema?.sections?.[section];
  const field = keys.reduce((node, key, index) => (
    (index === 0 ? node?.parameters?.[key] : node?.properties?.[key]) || node?.additional_properties
  ), root);
  return {
    label: settingLabel(path.at(-1), field),
    group: [settingLabel(section, root), ...keys.slice(0, -1).map((key) => settingLabel(key))].join(' / '),
    unit: field?.unit,
  };
}

function displayValue(value, unit, absent) {
  if (absent) return 'Not set';
  if (value === null) return 'Automatic';
  if (typeof value === 'boolean') return value ? 'On' : 'Off';
  if (typeof value === 'object') return JSON.stringify(value);
  return unit && typeof value === 'number' ? `${value} ${unit}` : String(value);
}

const reloadMessage = {
  follower_restart: 'Restart the follower to apply.',
  tracker_restart: 'Apply the saved tracker settings.',
  system_restart: 'Restart PixEagle to apply.',
};

export default function SettingsPage() {
  const { schema, loading: schemaLoading, error: schemaError } = useConfigSchema();
  const defaultsSync = useDefaultsSync();
  const { refreshRuntimeStatus, requestRestartConfirmation } = usePendingRestart();
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState({});
  const [section, setSection] = useState(() => window.location.hash.slice(1) || 'VideoSource');
  const [query, setQuery] = useState('');
  const [advanced, setAdvanced] = useState(() => Boolean(window.location.hash));
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const operation = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [backup, setBackup] = useState(null);
  const [more, setMore] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [history, setHistory] = useState([]);
  const [applyStatus, setApplyStatus] = useState(null);

  const reload = useCallback(async () => {
    const data = await apiFetchJson(endpoints.configEditor);
    setSaved(data);
    return data;
  }, []);

  useEffect(() => {
    reload().catch((err) => setError(errorText(err)));
  }, [reload]);

  const pending = useMemo(() => Object.values(draft).flatMap(({ path, value, error: invalid }) => (
    invalid ? [] : leafEdits(atPath(saved?.config, path), value, path)
  )), [draft, saved]);
  const invalidCount = Object.values(draft).filter((entry) => entry.error).length;
  const count = pending.length + invalidCount;
  const hasUnsaved = Boolean(count || review || busy);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => (
    hasUnsaved && currentLocation.pathname !== nextLocation.pathname
  ));
  useBeforeUnload(useCallback((event) => {
    if (!hasUnsaved) return;
    event.preventDefault();
    event.returnValue = '';
  }, [hasUnsaved]));

  const edit = (path, value, input) => {
    setDraft((old) => ({ ...old, [pathKey(path)]: { path, value, ...input } }));
    setNotice('');
  };

  const undo = (path) => {
    setDraft((old) => {
      const next = { ...old };
      delete next[pathKey(path)];
      return next;
    });
  };

  const discard = () => {
    setDraft({});
    setReview(null);
    setError('');
  };

  const perform = async (task) => {
    if (operation.current) return;
    operation.current = true;
    setBusy(true);
    setError('');
    try {
      await task();
    } catch (err) {
      if (['config_revision_stale', 'config_preview_stale'].includes(err.data?.code)) {
        setReview(null);
        await reload().catch(() => {});
      }
      setError(errorText(err));
    } finally {
      operation.current = false;
      setBusy(false);
    }
  };

  const send = async (body) => {
    const answer = await apiFetchJson(endpoints.configSaveAction, {
      method: 'POST', body: JSON.stringify(body),
    });
    if (!answer.accepted || !answer.result || (!body.dry_run && !answer.executed)) throw new Error(answer.error || 'PixEagle did not accept the change.');
    return answer.result;
  };

  const preview = async (input) => {
    const body = { revision: saved.revision, ...input };
    const result = await send({ ...body, dry_run: true });
    setReview({
      body, ...result,
      action: buildActionRequest('save_settings', { ui: 'settings' }),
    });
  };

  const undoReviewed = (path) => perform(async () => {
    const parent = Object.values(draft).find((entry) => entry.path.every((key, index) => key === path[index]));
    if (!parent) return;
    const remaining = pending.filter((entry) => pathKey(entry.path) !== pathKey(path));
    const original = atPath(saved.config, path);
    edit(parent.path, restoreLeaf(parent.value, path.slice(parent.path.length), original));
    if (remaining.length) await preview({ edits: remaining });
    else setReview(null);
  });

  const verify = async (revision) => {
    const active = await reload();
    if (active.revision !== revision) {
      setNotice('Saved. Settings changed again during verification. The latest saved values are shown.');
      setApplyStatus(null);
      return;
    }
    const [runtime, native] = await Promise.allSettled([
      refreshRuntimeStatus(), apiFetchJson(endpoints.nativeConfigStatus),
    ]);
    if (runtime.status === 'rejected') {
      setNotice('Saved and read back. Running status is temporarily unavailable.');
      return;
    }
    const status = runtime.value;
    const tiers = new Set([...(active.pending_changes || []), ...(native.value?.pending_changes || [])]
      .map((change) => change.reload_tier));
    setNotice(status?.restart_required ? 'Saved. Restart PixEagle to apply.'
      : tiers.has('tracker_restart') ? 'Saved. Apply the saved tracker settings.'
        : tiers.has('follower_restart') ? 'Saved. Restart the follower to use the new settings.'
          : 'Saved and verified.');
    setApplyStatus(native.status === 'fulfilled' ? native.value : null);
  };

  const save = () => perform(async () => {
    const result = await send({
      ...review.body, ...review.action, preview_token: review.preview_token, dry_run: false,
    });
    setDraft({});
    setReview(null);
    setBackup(result.backup_id ? { id: result.backup_id, revision: result.revision } : null);
    setNotice('Saved. Checking running settings…');
    try {
      await verify(result.revision);
    } catch {
      setNotice('Saved. Reload Settings to verify the current values.');
    }
  });

  const applyTracker = () => perform(async () => {
    const result = await apiFetchJson(endpoints.configApplyAction, {
      method: 'POST', body: JSON.stringify({
        ...buildActionRequest('apply_tracker_settings', { ui: 'settings' }),
        instance_id: applyStatus.instance_id, runtime_id: applyStatus.runtime_id,
        config_generation: applyStatus.config_generation, reload_tier: applyStatus.apply.reload_tier,
      }),
    });
    if (!result.executed) throw new Error(result.error || 'Tracker settings could not be applied.');
    await verify(saved.revision);
  });

  const reviewBackup = (id) => perform(async () => {
    setDialog(null);
    await preview({ backup_id: id });
  });

  const openMore = (action) => {
    setMore(null);
    if (action === 'history') {
      perform(async () => {
        const result = await apiFetchJson(endpoints.configHistory);
        setHistory(result.backups || []);
        setDialog(action);
      });
    } else {
      setDialog(action);
    }
  };

  const sections = Object.entries(schema?.sections || {});
  const search = query.trim().toLowerCase();
  const visible = sections.filter(([name, definition]) => search
    ? [name, settingLabel(name, definition), ...Object.entries(definition.parameters || {}).flatMap(
      ([key, field]) => [key, settingLabel(key, field), field.description]
    )].some((value) => value?.toLowerCase().includes(search))
    : advanced || commonSections.includes(name)
  );
  const activeSection = visible.some(([name]) => name === section) ? section : visible[0]?.[0];
  const writable = Boolean(!schemaLoading && schema && saved?.writable);
  const configReady = Boolean(saved && schema);
  const displayError = schemaError || error;

  return <Container maxWidth="lg" sx={{ py: { xs: 1.5, md: 3 }, ...touchControls }}>
    <Paper variant="outlined" sx={{
      position: 'sticky', top: 0, zIndex: 2, mb: 2, p: { xs: 1.5, md: 2 },
      bgcolor: 'background.paper',
    }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Settings color="primary" />
        <Typography component="h1" variant="h5" sx={{ flexGrow: 1 }}>Settings</Typography>
        <Button startIcon={<MoreHoriz />} onClick={(event) => setMore(event.currentTarget)}>More</Button>
        <Button variant="contained" startIcon={<Checklist />}
          disabled={!writable || !count || busy || Boolean(invalidCount)}
          onClick={() => perform(() => preview({ edits: pending }))}>
          Review changes{count ? ` (${count})` : ''}
        </Button>
      </Stack>
      {Boolean(invalidCount) && <Typography color="error" variant="body2">Correct the highlighted values before reviewing.</Typography>}
    </Paper>

    {displayError && !review && <Alert severity="error" sx={{ mb: 2 }}>{displayError}
      {!saved && <Button onClick={() => perform(reload)}>Retry</Button>}
    </Alert>}
    {notice && <Alert severity="success" role="status" sx={{ mb: 2 }} action={
      backup?.revision === saved?.revision && !count
        ? <Button color="inherit" disabled={busy || !writable} onClick={() => reviewBackup(backup.id)}>Undo last save</Button>
        : undefined
    }>{notice}</Alert>}
    {applyStatus?.system_restart?.available && !count && <Button onClick={requestRestartConfirmation}>Restart PixEagle</Button>}
    {applyStatus?.apply?.available && !count && <Button disabled={busy} onClick={applyTracker}>Apply saved settings</Button>}
    {!configReady && !displayError && <Typography role="status">Loading settings…</Typography>}
    {configReady && <Box sx={{
      display: 'grid', gridTemplateColumns: { xs: '1fr', md: '235px minmax(0, 1fr)' }, gap: 2, alignItems: 'start',
    }}>
      <Paper variant="outlined" sx={{ p: 1 }}>
        <TextField fullWidth size="small" label="Search settings" value={query} onChange={(event) => setQuery(event.target.value)} />
        <TextField select fullWidth size="small" label="Section" value={activeSection || ''}
          onChange={(event) => setSection(event.target.value)} sx={{ display: { md: 'none' }, mt: 1 }}>
          {visible.map(([name, definition]) => <MenuItem value={name} key={name}>{settingLabel(name, definition)}</MenuItem>)}
        </TextField>
        <List disablePadding sx={{ display: { xs: 'none', md: 'block' }, maxHeight: '60vh', overflow: 'auto' }}>
          {visible.map(([name, definition]) => {
            const Icon = categoryIcons[definition.category] || Settings;
            return <ListItemButton key={name} selected={name === activeSection} onClick={() => setSection(name)} sx={{ minHeight: 44 }}>
              <ListItemIcon sx={{ minWidth: 34 }}><Icon fontSize="small" /></ListItemIcon>
              <ListItemText primary={settingLabel(name, definition)} />
            </ListItemButton>;
          })}
        </List>
        <Button onClick={() => setAdvanced(!advanced)}>{advanced ? 'Common settings' : 'All settings'}</Button>
      </Paper>
      {activeSection ? <SectionEditor
        key={activeSection} section={activeSection} schema={schema.sections[activeSection]}
        saved={saved.config[activeSection]} draft={draft} onEdit={edit} onUndo={undo}
        disabled={!writable || busy} query={search} showDefaults={advanced}
      /> : <Typography>No matching settings.</Typography>}
    </Box>}

    <Menu anchorEl={more} open={Boolean(more)} onClose={() => setMore(null)}>
      <MenuItem onClick={() => openMore('export')} disabled={!configReady}><FileDownload sx={{ mr: 1 }} />Export saved YAML</MenuItem>
      <MenuItem onClick={() => openMore('history')} disabled={!configReady || !!count}><History sx={{ mr: 1 }} />Backup history</MenuItem>
      <MenuItem onClick={() => openMore('sync')} disabled={!writable || !!count}>Sync with defaults</MenuItem>
      <MenuItem onClick={() => openMore('discard')} disabled={!count || busy}>Discard all edits</MenuItem>
    </Menu>
    {dialog === 'export' && <ExportDialog open onClose={() => setDialog(null)} />}
    {dialog === 'sync' && <SyncWithDefaultsDialog open defaultsSync={defaultsSync}
      mutationsAllowed={writable} onMessage={setNotice} onRebootRequired={refreshRuntimeStatus}
      onClose={() => { setDialog(null); perform(reload); }} />}
    <Dialog open={dialog === 'history'} onClose={() => setDialog(null)} fullWidth maxWidth="sm" PaperProps={{ sx: touchControls }}>
      <DialogTitle>Backup history</DialogTitle>
      <DialogContent>
        {!history.length && <Typography>No backups available.</Typography>}
        {history.map((row) => <Stack key={row.id} direction="row" gap={1} alignItems="center" justifyContent="space-between" sx={{ my: 1 }}>
          <Typography>{new Date(row.timestamp * 1000).toLocaleString()}</Typography>
          <Button disabled={!writable || busy} onClick={() => reviewBackup(row.id)}>Review restore</Button>
        </Stack>)}
      </DialogContent>
      <DialogActions><Button onClick={() => setDialog(null)}>Close</Button></DialogActions>
    </Dialog>
    <Dialog open={dialog === 'discard' || blocker.state === 'blocked'} onClose={() => {
      setDialog(null);
      if (blocker.state === 'blocked') blocker.reset();
    }} PaperProps={{ sx: touchControls }}>
      <DialogTitle>Discard unsaved changes?</DialogTitle>
      <DialogActions>
        <Button onClick={() => {
          setDialog(null);
          if (blocker.state === 'blocked') blocker.reset();
        }}>Keep editing</Button>
        <Button color="error" disabled={busy} onClick={() => {
          discard();
          setDialog(null);
          if (blocker.state === 'blocked') blocker.proceed();
        }}>Discard changes</Button>
      </DialogActions>
    </Dialog>

    <Dialog open={Boolean(review)} fullWidth maxWidth="sm" PaperProps={{ sx: touchControls }}
      onClose={busy ? undefined : () => setReview(null)}>
      <DialogTitle>{review?.body.backup_id ? 'Review backup restore' : 'Review changes'}</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {!review?.changes.length && <Typography>No changes to save.</Typography>}
        <Stack divider={<Divider />} spacing={1.5}>
          {review?.changes.map((change) => {
            const meta = changeMetadata(schema, change.path);
            return <Stack key={pathKey(change.path)} gap={0.5}>
              <Typography variant="caption" color="text.secondary">{meta.group}</Typography>
              <Typography fontWeight={600}>{meta.label}</Typography>
              <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ overflowWrap: 'anywhere' }}>
                <Typography color="text.secondary">{displayValue(change.old_value, meta.unit, change.kind === 'added')}</Typography>
                <ArrowForward fontSize="small" aria-label="changed to" />
                <Typography fontWeight={600}>{displayValue(change.new_value, meta.unit, change.kind === 'removed')}</Typography>
                {!review.body.backup_id && <Button size="small" disabled={busy} startIcon={<Undo />}
                  aria-label={`Undo ${meta.label}`} onClick={() => undoReviewed(change.path)} sx={{ ml: 'auto' }}>Undo</Button>}
              </Stack>
              {reloadMessage[change.reload_tier] && <Typography variant="caption" color="text.secondary">
                {reloadMessage[change.reload_tier]}
              </Typography>}
            </Stack>;
          })}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        <Button disabled={busy} onClick={() => setReview(null)}>{review?.body.backup_id ? 'Cancel' : 'Keep editing'}</Button>
        {!review?.body.backup_id && <Button disabled={busy} onClick={() => { setReview(null); setDialog('discard'); }}>Discard all</Button>}
        <Button variant="contained" disabled={busy || !review?.changes.length} onClick={save}>
          {busy ? 'Working…' : 'Save changes'}
        </Button>
      </DialogActions>
    </Dialog>
  </Container>;
}
