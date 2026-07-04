// dashboard/src/pages/LogsPage.js
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import ArticleIcon from '@mui/icons-material/Article';
import RefreshIcon from '@mui/icons-material/Refresh';

import { endpoints } from '../services/apiEndpoints';
import { apiFetch } from '../services/apiClient';
import { useAuthSession } from '../context/AuthSessionContext';

const LEVEL_OPTIONS = ['', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

const levelColor = (level) => {
  switch (level) {
    case 'CRITICAL':
    case 'ERROR':
      return 'error';
    case 'WARNING':
      return 'warning';
    case 'INFO':
      return 'info';
    case 'DEBUG':
      return 'default';
    default:
      return 'default';
  }
};

const formatBytes = (bytes) => {
  if (!bytes || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatTimestamp = (value) => {
  if (!value) return '--';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

const buildEntriesUrl = (runId, { component, level, limit, offset }) => {
  const params = new URLSearchParams();
  if (component) params.set('component', component);
  if (level) params.set('level', level);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return `${endpoints.logSessionEntries(runId)}?${params.toString()}`;
};

const LogsPage = () => {
  const authSession = useAuthSession();
  const canReadLogs = authSession.hasScope('debug:read');
  const [status, setStatus] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [component, setComponent] = useState('backend');
  const [level, setLevel] = useState('');
  const [limit, setLimit] = useState(200);
  const [offset, setOffset] = useState(0);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.run_id === selectedRunId) || null,
    [sessions, selectedRunId]
  );

  const componentOptions = useMemo(() => {
    const values = selectedSession?.components?.length ? selectedSession.components : ['backend'];
    return Array.from(new Set(values));
  }, [selectedSession]);

  const fetchSessions = useCallback(async () => {
    if (!canReadLogs) {
      setStatus(null);
      setSessions([]);
      setSelectedRunId('');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [statusResponse, sessionsResponse] = await Promise.all([
        apiFetch(endpoints.logsStatus),
        apiFetch(`${endpoints.logSessions}?limit=50`),
      ]);
      if (!statusResponse.ok) throw new Error(`Status request failed (${statusResponse.status})`);
      if (!sessionsResponse.ok) throw new Error(`Sessions request failed (${sessionsResponse.status})`);
      const statusPayload = await statusResponse.json();
      const sessionsPayload = await sessionsResponse.json();
      const nextSessions = sessionsPayload.sessions || [];
      setStatus(statusPayload);
      setSessions(nextSessions);
      setSelectedRunId((current) => {
        if (current && nextSessions.some((session) => session.run_id === current)) {
          return current;
        }
        return sessionsPayload.active_run_id || nextSessions[0]?.run_id || '';
      });
    } catch (err) {
      setError(err.message || 'Failed to load runtime log sessions.');
    } finally {
      setLoading(false);
    }
  }, [canReadLogs]);

  const fetchEntries = useCallback(async () => {
    if (!canReadLogs || !selectedRunId) {
      setEntries([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(
        buildEntriesUrl(selectedRunId, {
          component,
          level,
          limit,
          offset,
        })
      );
      if (!response.ok) throw new Error(`Log entry request failed (${response.status})`);
      const payload = await response.json();
      setEntries(payload.entries || []);
    } catch (err) {
      setError(err.message || 'Failed to load runtime log entries.');
    } finally {
      setLoading(false);
    }
  }, [canReadLogs, component, level, limit, offset, selectedRunId]);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  useEffect(() => {
    if (componentOptions.length && !componentOptions.includes(component)) {
      setComponent(componentOptions[0]);
    }
  }, [component, componentOptions]);

  const handleRefresh = () => {
    fetchSessions();
    fetchEntries();
  };

  return (
    <Box sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ mb: 3, flexWrap: 'wrap', rowGap: 1 }}
      >
        <ArticleIcon color="primary" />
        <Typography variant="h5" fontWeight={600}>
          Backend Runtime Logs
        </Typography>
        {status?.active_run_id && (
          <Chip
            label={status.active_run_id}
            size="small"
            variant="outlined"
            sx={{ maxWidth: { xs: '100%', sm: 360 }, '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' } }}
          />
        )}
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Refresh logs">
          <IconButton onClick={handleRefresh} size="small">
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Stack>

      {loading && <LinearProgress sx={{ mb: 2 }} />}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {!canReadLogs && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Runtime logs require debug read access. Use an admin/debug account or a local development session.
        </Alert>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={4}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                Active Session
              </Typography>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {status?.active_run_id || '--'}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                {status?.base_dir || '--'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                Sessions
              </Typography>
              <Typography variant="h5">{sessions.length}</Typography>
              <Typography variant="caption" color="text.secondary">
                Retained runtime sessions
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card variant="outlined" sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                Boundary
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Backend process logs only. They are evidence for PixEagle runtime behavior, not PX4/SITL/HIL/field proof.
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                Dashboard and sidecar capture are tracked as follow-up logging work.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <FormControl fullWidth size="small">
                <InputLabel id="log-session-select-label">Session</InputLabel>
                <Select
                  labelId="log-session-select-label"
                  value={selectedRunId}
                  label="Session"
                  onChange={(event) => {
                    setSelectedRunId(event.target.value);
                    setOffset(0);
                  }}
                >
                  {sessions.map((session) => (
                    <MenuItem key={session.run_id} value={session.run_id}>
                      {session.run_id}{session.active ? ' (active)' : ''}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel id="log-component-select-label">Component</InputLabel>
                <Select
                  labelId="log-component-select-label"
                  value={component}
                  label="Component"
                  onChange={(event) => {
                    setComponent(event.target.value);
                    setOffset(0);
                  }}
                >
                  {componentOptions.map((name) => (
                    <MenuItem key={name} value={name}>{name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel id="log-level-select-label">Minimum level</InputLabel>
                <Select
                  labelId="log-level-select-label"
                  value={level}
                  label="Minimum level"
                  onChange={(event) => {
                    setLevel(event.target.value);
                    setOffset(0);
                  }}
                >
                  {LEVEL_OPTIONS.map((name) => (
                    <MenuItem key={name || 'all'} value={name}>
                      {name || 'All'}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Limit"
                value={limit}
                inputProps={{ min: 1, max: 1000 }}
                onChange={(event) => setLimit(Number(event.target.value || 200))}
              />
            </Grid>
            <Grid item xs={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Offset"
                value={offset}
                inputProps={{ min: 0 }}
                onChange={(event) => setOffset(Number(event.target.value || 0))}
              />
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <TableContainer sx={{ maxHeight: { xs: '58vh', md: '64vh' } }}>
          <Table stickyHeader size="small" aria-label="runtime log entries">
            <TableHead>
              <TableRow>
                <TableCell sx={{ minWidth: 170 }}>Time</TableCell>
                <TableCell sx={{ minWidth: 96 }}>Level</TableCell>
                <TableCell sx={{ minWidth: 140 }}>Logger</TableCell>
                <TableCell>Message</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
                      No log entries match the current filter.
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : entries.map((entry, index) => (
                <TableRow key={`${entry.ts}-${entry.logger}-${entry.line}-${index}`} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {formatTimestamp(entry.ts)}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={entry.level}
                      size="small"
                      color={levelColor(entry.level)}
                      variant={entry.level === 'ERROR' || entry.level === 'CRITICAL' ? 'filled' : 'outlined'}
                    />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontSize: 12, wordBreak: 'break-word' }}>
                    {entry.logger}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    <Typography variant="body2">{entry.message}</Typography>
                    {entry.traceback && (
                      <Typography component="pre" variant="caption" sx={{ mt: 1, whiteSpace: 'pre-wrap' }}>
                        {entry.traceback}
                      </Typography>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {selectedSession && (
        <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} flexWrap="wrap">
          <Chip size="small" label={`Size ${formatBytes(selectedSession.size_bytes)}`} />
          <Chip size="small" label={`Modified ${formatTimestamp(selectedSession.modified_at)}`} />
          {selectedSession.components?.map((name) => (
            <Chip key={name} size="small" label={name} variant="outlined" />
          ))}
        </Stack>
      )}
    </Box>
  );
};

export default LogsPage;
