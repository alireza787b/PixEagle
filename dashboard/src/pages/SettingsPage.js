import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useBlocker, useBeforeUnload } from 'react-router-dom';
import {
  Alert, Box, Button, Collapse, Container, Dialog, DialogActions, DialogContent, DialogTitle,
  Divider, List, ListItemButton, ListItemIcon, ListItemText, ListSubheader, Menu, MenuItem, Paper,
  Stack, TextField, Typography,
} from '@mui/material';
import {
  ArrowForward, Checklist, ExpandLess, ExpandMore, FileDownload, FileUpload, GpsFixed, History, MoreHoriz, Navigation,
  Router, Settings, Shield, Tune, Undo, Videocam,
} from '@mui/icons-material';
import SectionEditor, { matchesSetting, settingLabel, touchControls } from '../components/config/SectionEditor';
import ExportDialog from '../components/config/ExportDialog';
import AuditLogDialog from '../components/config/AuditLogDialog';
import SyncWithDefaultsDialog from '../components/config/SyncWithDefaultsDialog';
import { useConfigSchema } from '../hooks/useConfig';
import { useDefaultsSync } from '../hooks/useDefaultsSync';
import { usePendingRestart } from '../context/PendingRestartContext';
import { apiFetchJson } from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';
import { endpoints } from '../services/apiEndpoints';
import { isPlainObject } from '../utils/configEditorSchemaUtils';
import { readConfigYaml } from '../utils/configImport';

const categoryIcons = {
  video: Videocam, tracking: GpsFixed, network: Router, follower: Navigation,
  safety: Shield, control: Tune,
};
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
  const savedRef = useRef(null);
  const [draft, setDraft] = useState({});
  const [section, setSection] = useState(() => window.location.hash.slice(1) || 'VideoSource');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState({});
  const [showDefaults, setShowDefaults] = useState(false);
  const [review, setReview] = useState(null);
  const [busy, setBusy] = useState(false);
  const operation = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [fieldIssue, setFieldIssue] = useState(null);
  const [backup, setBackup] = useState(null);
  const [imported, setImported] = useState(null);
  const fileInput = useRef(null);
  const [more, setMore] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [history, setHistory] = useState([]);
  const [applyStatus, setApplyStatus] = useState(null);

  const reload = useCallback(async () => {
    const data = await apiFetchJson(endpoints.configEditor);
    const previous = savedRef.current;
    if (previous && previous.revision !== data.revision) {
      // Preserve only the edited leaves when another client updates a sibling.
      setDraft((old) => Object.fromEntries(Object.entries(old).map(([key, entry]) => {
        if (entry.error) return [key, entry];
        const edits = leafEdits(atPath(previous.config, entry.path), entry.value, entry.path);
        const value = edits.reduce((latest, change) => restoreLeaf(
          latest, change.path.slice(entry.path.length), change.unset ? undefined : change.value
        ), atPath(data.config, entry.path));
        return [key, { ...entry, value }];
      })));
    }
    savedRef.current = data;
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
  const count = imported ? imported.count : pending.length + invalidCount;
  const hasUnsaved = Boolean(count || review || busy || imported);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => (
    hasUnsaved && currentLocation.pathname !== nextLocation.pathname
  ));
  useBeforeUnload(useCallback((event) => {
    if (!hasUnsaved) return;
    event.preventDefault();
    event.returnValue = '';
  }, [hasUnsaved]));

  const edit = (path, value, input) => {
    setFieldIssue(null);
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
    setImported(null);
    setReview(null);
    setFieldIssue(null);
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
      const path = err.data?.detail?.setting_path;
      if (Array.isArray(path) && path.length) {
        setFieldIssue({ path, message: errorText(err) });
        setSection(path[0]);
        setQuery('');
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

  const preview = async (input, importName = imported?.name) => {
    const body = { revision: saved.revision, ...input };
    let result;
    try {
      result = await send({ ...body, dry_run: true });
    } catch (err) {
      if (importName && err.data?.code === 'config_revision_stale') {
        setImported({ input, name: importName, count: imported?.count || 1 });
      }
      throw err;
    }
    if (importName) setImported({ input, name: importName, count: result.changes.length });
    setReview({ body, ...result, action: buildActionRequest('save_settings', { ui: 'settings' }) });
  };

  const undoReviewed = (path) => perform(async () => {
    if (imported) {
      const input = { ...imported.input, excluded_paths: [...(imported.input.excluded_paths || []), path] };
      await preview(input);
      return;
    }
    const parent = Object.values(draft).find((entry) => entry.path.every((key, index) => key === path[index]));
    if (!parent) return;
    const remaining = pending.filter((entry) => pathKey(entry.path) !== pathKey(path));
    const original = atPath(saved.config, path);
    edit(parent.path, restoreLeaf(parent.value, path.slice(parent.path.length), original));
    if (remaining.length) await preview({ edits: remaining });
    else setReview(null);
  });

  const chooseImport = () => {
    if (hasUnsaved) setDialog('importPending');
    else fileInput.current?.click();
  };

  const readImport = (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    perform(async () => {
      await preview({ import_values: await readConfigYaml(file) }, file.name);
    });
  };

  const reviewDraft = () => perform(() => preview(imported ? imported.input : { edits: pending }));

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
    setNotice(status?.restart_required || tiers.has('system_restart') ? 'Saved. Restart PixEagle to apply.'
      : tiers.has('tracker_restart') ? 'Saved. Apply the saved tracker settings.'
        : tiers.has('follower_restart') ? 'Saved. Restart the follower to use the new settings.'
          : tiers.size ? 'Saved. Apply the saved settings.' : 'Saved and verified.');
    setApplyStatus(native.status === 'fulfilled' ? native.value : null);
  };

  const save = () => perform(async () => {
    const result = await send({
      ...review.body, ...review.action, preview_token: review.preview_token, dry_run: false,
    });
    setDraft({});
    setImported(null);
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
    } else if (action === 'reconnect') {
      perform(async () => {
        const result = await apiFetchJson(endpoints.videoReconnect, { method: 'POST' });
        setNotice(result.message || 'Video reconnection requested.');
      });
    } else {
      setDialog(action);
    }
  };

  const sections = Object.entries(schema?.sections || {});
  const search = query.trim().toLowerCase();
  const categories = schema?.categories || {};
  const categoryLabel = (category) => settingLabel(category, categories[category]);
  const visible = sections.filter(([name, definition]) => !search || matchesSetting(name, definition, search)
    || categoryLabel(definition.category || 'other').toLowerCase().includes(search));
  const grouped = new Map();
  visible.forEach((row) => {
    const category = row[1].category || 'other';
    if (!grouped.has(category)) grouped.set(category, []);
    grouped.get(category).push(row);
  });
  const groups = [...grouped].sort(([first], [second]) =>
    (categories[first]?.order ?? Infinity) - (categories[second]?.order ?? Infinity)
    || categoryLabel(first).localeCompare(categoryLabel(second)));
  const activeSection = visible.some(([name]) => name === section) ? section : visible[0]?.[0];
  const writable = Boolean(!schemaLoading && schema && saved?.writable);
  const configReady = Boolean(saved && schema);
  const displayError = schemaError || error;
  const reviewTiers = [...new Set(review?.changes.map((change) => change.reload_tier) || [])];

  return <Container maxWidth="lg" sx={{ py: { xs: 1.5, md: 3 }, ...touchControls }}>
    <Paper variant="outlined" sx={{
      position: 'sticky', top: 0, zIndex: 2, mb: 2, p: { xs: 1.5, md: 2 },
      bgcolor: 'background.paper',
    }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Settings color="primary" />
        <Typography component="h1" variant="h5" sx={{ flexGrow: 1 }}>Settings</Typography>
        <input ref={fileInput} type="file" accept=".yaml,.yml" aria-label="Choose settings YAML"
          hidden onChange={readImport} />
        <Button startIcon={<FileUpload />} disabled={!writable || busy} onClick={chooseImport}>Import</Button>
        <Button startIcon={<MoreHoriz />} onClick={(event) => setMore(event.currentTarget)}>More</Button>
        <Button variant="contained" startIcon={<Checklist />}
          disabled={!writable || !count || busy || Boolean(invalidCount)}
          onClick={reviewDraft}>
          Review changes{count ? ` (${count})` : ''}
        </Button>
      </Stack>
      {Boolean(invalidCount) && <Typography color="error" variant="body2">Correct the highlighted values before reviewing.</Typography>}
      {busy && !review && <Typography role="status" variant="body2">Checking settings…</Typography>}
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
        <TextField fullWidth size="small" label="Search settings" value={query} onChange={(event) => {
          setQuery(event.target.value);
          setExpanded({});
        }} />
        <TextField select fullWidth size="small" label="Section" value={activeSection || ''}
          onChange={(event) => setSection(event.target.value)} sx={{ display: { md: 'none' }, mt: 1 }}>
          {groups.flatMap(([category, rows]) => [
            <ListSubheader key={category}>{categoryLabel(category)}</ListSubheader>,
            ...rows.map(([name, definition]) => <MenuItem value={name} key={name} sx={{ minHeight: 44 }}>
              {settingLabel(name, definition)}
            </MenuItem>),
          ])}
        </TextField>
        <List aria-label="Settings categories" disablePadding
          sx={{ display: { xs: 'none', md: 'block' }, maxHeight: '60vh', overflow: 'auto' }}>
          {groups.map(([category, rows]) => {
            const Icon = categoryIcons[category] || Settings;
            const open = expanded[category] ?? (Boolean(search) || rows.some(([name]) => name === activeSection));
            const id = `settings-category-${category}`;
            return <Box component="li" key={category}>
              <ListItemButton aria-expanded={open} aria-controls={id} sx={{ minHeight: 44 }}
                onClick={() => setExpanded((old) => ({ ...old, [category]: !open }))}>
                <ListItemIcon sx={{ minWidth: 34 }}><Icon fontSize="small" /></ListItemIcon>
                <ListItemText primary={categoryLabel(category)} />
                {open ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              </ListItemButton>
              <Collapse in={open} id={id}>
                <List disablePadding>
                  {rows.map(([name, definition]) => <ListItemButton key={name} selected={name === activeSection}
                    onClick={() => setSection(name)} sx={{ minHeight: 44, pl: 4 }}>
                    <ListItemText primary={settingLabel(name, definition)} />
                  </ListItemButton>)}
                </List>
              </Collapse>
            </Box>;
          })}
        </List>
      </Paper>
      {activeSection ? <SectionEditor
        key={activeSection} section={activeSection} schema={schema.sections[activeSection]}
        saved={saved.config[activeSection]} draft={draft} onEdit={edit} onUndo={undo}
        disabled={!writable || busy || Boolean(imported)}
        query={schema.sections[activeSection].category &&
          categoryLabel(schema.sections[activeSection].category).toLowerCase().includes(search) ? '' : search}
        showDefaults={showDefaults} fieldIssue={fieldIssue}
      /> : <Typography>No matching settings.</Typography>}
    </Box>}

    {imported && !review && <Alert severity="info" sx={{ my: 2 }}
      action={<Button disabled={busy} onClick={discard}>Discard import</Button>}>
      {imported.name} is waiting for review.
    </Alert>}
    <Dialog open={dialog === 'importPending'} onClose={() => setDialog(null)} PaperProps={{ sx: touchControls }}>
      <DialogTitle>You have unsaved settings</DialogTitle>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        <Button onClick={() => { setDialog(null); if (!invalidCount) reviewDraft(); }}>
          {invalidCount ? 'Keep editing' : 'Review existing edits'}
        </Button>
        <Button color="error" onClick={() => {
          discard();
          setDialog(null);
          fileInput.current?.click();
        }}>Discard edits and import</Button>
      </DialogActions>
    </Dialog>
    <Menu anchorEl={more} open={Boolean(more)} onClose={() => setMore(null)}>
      <MenuItem onClick={() => openMore('export')} disabled={!configReady}><FileDownload sx={{ mr: 1 }} />Export saved YAML</MenuItem>
      <MenuItem onClick={() => openMore('history')} disabled={!configReady || !!count}><History sx={{ mr: 1 }} />Backup history</MenuItem>
      <MenuItem onClick={() => openMore('audit')} disabled={!configReady}>Audit log</MenuItem>
      <MenuItem onClick={() => openMore('sync')} disabled={!writable || !!count}>Sync with defaults</MenuItem>
      <MenuItem onClick={() => { setMore(null); setShowDefaults(!showDefaults); }}>
        {showDefaults ? 'Hide default actions' : 'Show default actions'}
      </MenuItem>
      <MenuItem onClick={() => openMore('reconnect')} disabled={busy}>Reconnect video</MenuItem>
      <MenuItem onClick={() => openMore('discard')} disabled={!count || busy}>Discard all edits</MenuItem>
    </Menu>
    {dialog === 'audit' && <AuditLogDialog open onClose={() => setDialog(null)} />}
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
      onClose={busy ? undefined : imported ? discard : () => setReview(null)}>
      <DialogTitle>{review?.body.backup_id ? 'Review backup restore' : imported ? 'Review import' : 'Review changes'}</DialogTitle>
      <DialogContent dividers>
        {imported && <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>
          {imported.name} · Merge · Settings omitted from the file are kept.
        </Typography>}
        {Boolean(imported?.input.excluded_paths?.length) && <Button disabled={busy} onClick={() =>
          perform(() => preview({ ...imported.input, excluded_paths: [] }))
        }>Include omitted changes</Button>}
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {!review?.changes.length && <Typography>No changes to save.</Typography>}
        {Boolean(review?.changes.length) && <Stack gap={0.25} sx={{ mb: 2 }}>
          <Typography color="text.secondary" variant="body2">Saved → New</Typography>
          {reviewTiers.includes('system_restart')
            ? <Typography variant="caption">{reloadMessage.system_restart}</Typography>
            : reviewTiers.filter((tier) => reloadMessage[tier]).map((tier) => (
              <Typography key={tier} variant="caption">{reloadMessage[tier]}</Typography>
            ))}
        </Stack>}
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
                  aria-label={`${imported ? 'Omit' : 'Undo'} ${meta.label}`}
                  onClick={() => undoReviewed(change.path)} sx={{ ml: 'auto' }}>{imported ? 'Omit' : 'Undo'}</Button>}
              </Stack>
            </Stack>;
          })}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}>
        <Button disabled={busy} onClick={imported ? discard : () => setReview(null)}>
          {review?.body.backup_id || imported ? 'Cancel' : 'Keep editing'}
        </Button>
        {!review?.body.backup_id && !imported && <Button disabled={busy} onClick={() => { setReview(null); setDialog('discard'); }}>Discard all</Button>}
        <Button variant="contained" disabled={busy || !review?.changes.length} onClick={save}>
          {busy ? 'Working…' : 'Save changes'}
        </Button>
      </DialogActions>
    </Dialog>
  </Container>;
}
