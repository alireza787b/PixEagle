import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RefreshIcon from '@mui/icons-material/Refresh';
import ScienceIcon from '@mui/icons-material/Science';
import StopIcon from '@mui/icons-material/Stop';

import { endpoints } from '../services/apiEndpoints';
import { apiFetch, apiFetchJson } from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';
import { useAuthSession } from '../context/AuthSessionContext';

const breakableTextSx = {
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
};

const resultColor = (result) => ({
  pass: 'success',
  failed: 'error',
  incomplete: 'warning',
}[result] || 'default');

const readinessColor = (readiness) => ({
  ready: 'success',
  running: 'success',
  disabled: 'default',
  setup_required: 'warning',
  conflict: 'error',
  unavailable: 'error',
}[readiness] || 'default');

const readinessLabel = (readiness) => ({
  ready: 'Ready',
  running: 'Running',
  disabled: 'Disabled',
  setup_required: 'Setup required',
  conflict: 'Container conflict',
  unavailable: 'Unavailable',
}[readiness] || 'Unknown');

const reasonLabel = (reason) => ({
  docker_cli_missing: 'Docker CLI is not installed.',
  docker_daemon_unavailable: 'Docker daemon access is unavailable.',
  pinned_image_missing: 'The pinned PX4 image is not installed.',
  pinned_image_digest_mismatch: 'The installed PX4 image does not match the pinned digest.',
  container_name_owned_by_another_process: 'The managed container name is already in use.',
  container_inspect_failed: 'Docker could not inspect the managed container name.',
  container_inspect_invalid: 'Docker returned an invalid container inspection result.',
  control_activity_state_unavailable: 'PixEagle could not verify following and Offboard state.',
  following_or_offboard_active: 'Stop following and leave Offboard first.',
  durable_audit_unavailable: 'Durable security audit logging is unavailable.',
  px4_already_connected: 'PixEagle is already connected to a PX4 source.',
  px4_connection_state_unavailable: 'PixEagle could not prove that PX4 is disconnected.',
}[reason] || String(reason || 'unknown').replace(/_/g, ' '));

const px4ConnectionLabel = (connected) => {
  if (connected === true) return 'Connected';
  if (connected === false) return 'Disconnected';
  return 'Unknown';
};

const controlActivityLabel = (available, active) => {
  if (!available) return 'Unknown';
  return active ? 'Active' : 'Inactive';
};

const formatTimestamp = (value) => {
  if (!value) return 'Not available';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
};

const commandModeLabel = (command) => {
  if (command.starts_processes) return 'Starts PX4 only';
  if (command.writes_artifacts) return 'Writes evidence';
  return 'No side effects';
};

const StatusRow = ({ label, value, color = 'default', detail }) => (
  <Box sx={{ py: 1.1, borderBottom: 1, borderColor: 'divider', minWidth: 0 }}>
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={0.75}
      alignItems={{ xs: 'flex-start', sm: 'center' }}
      justifyContent="space-between"
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {label}
        </Typography>
        {detail && (
          <Typography variant="caption" color="text.secondary" sx={breakableTextSx}>
            {detail}
          </Typography>
        )}
      </Box>
      <Chip size="small" label={value} color={color} sx={{ flexShrink: 0 }} />
    </Stack>
  </Box>
);

const FailureList = ({ label, items }) => {
  if (!items?.length) return null;
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
        {label}
      </Typography>
      {items.map((item) => (
        <Typography key={item} variant="body2" sx={breakableTextSx}>
          {item}
        </Typography>
      ))}
    </Box>
  );
};

const ValidationPage = () => {
  const authSession = useAuthSession();
  const canReadValidation = authSession.hasScope('debug:read');
  const canManageValidation = authSession.hasScope('system:admin');
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusStale, setStatusStale] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  const latestRun = status?.latest_run || {};
  const lifecycle = status?.managed_lifecycle || {};
  const missingPreview = useMemo(
    () => latestRun.missing_or_placeholder_artifacts || [],
    [latestRun.missing_or_placeholder_artifacts]
  );

  const fetchStatus = useCallback(async () => {
    if (!canReadValidation) {
      setStatus(null);
      setStatusStale(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(endpoints.sitlValidationStatus);
      if (!response.ok) {
        throw new Error(`Validation status request failed (${response.status})`);
      }
      const payload = await response.json();
      if (!payload?.managed_lifecycle || payload.schema_version !== 3) {
        throw new Error('Validation status response is incompatible with this dashboard.');
      }
      setStatus(payload);
      setStatusStale(false);
    } catch (fetchError) {
      setError(fetchError.message || 'Failed to load validation status.');
      setStatusStale(true);
    } finally {
      setLoading(false);
    }
  }, [canReadValidation]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const confirmLifecycleAction = useCallback(async () => {
    if (!confirmation || actionPending) return;
    const operation = confirmation;
    const endpoint = operation === 'start'
      ? endpoints.managedSihStartAction
      : endpoints.managedSihStopAction;

    setActionPending(true);
    setActionMessage(null);
    try {
      const result = await apiFetchJson(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          ...buildActionRequest(`managed_sih_${operation}`, {
            ui: 'dashboard_validation_page',
            profile: 'official_px4_sih',
          }),
          ...(operation === 'start' ? { no_real_aircraft_confirmed: true } : {}),
        }),
      });
      if (result?.status !== 'success' || result?.accepted !== true) {
        throw new Error(result?.error || `Managed SIH ${operation} was not accepted.`);
      }
      setActionMessage({
        severity: 'success',
        text: operation === 'start' ? 'PX4 SIH started.' : 'PX4 SIH stopped.',
      });
      setConfirmation(null);
      await fetchStatus();
    } catch (actionError) {
      const message = actionError?.data?.detail?.message
        || actionError?.message
        || `Managed SIH ${operation} failed.`;
      setActionMessage({ severity: 'error', text: message });
    } finally {
      setActionPending(false);
    }
  }, [actionPending, confirmation, fetchStatus]);

  if (!canReadValidation) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Alert severity="warning">Validation status requires debug access.</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 2, md: 3 } }}>
      <Stack spacing={2.25}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
          <Stack direction="row" alignItems="center" spacing={1.25} sx={{ minWidth: 0 }}>
            <ScienceIcon color="primary" />
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                PX4 Validation
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Official PX4-only SIH training profile
              </Typography>
            </Box>
          </Stack>
          <Tooltip title="Refresh validation status">
            <span>
              <IconButton
                aria-label="Refresh validation status"
                onClick={fetchStatus}
                disabled={loading || actionPending}
              >
                <RefreshIcon />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>

        {loading && <LinearProgress />}
        {error && <Alert severity="error">{error}</Alert>}
        {statusStale && status && (
          <Alert severity="warning">Showing stale validation status.</Alert>
        )}
        {actionMessage && (
          <Alert severity={actionMessage.severity} onClose={() => setActionMessage(null)}>
            {actionMessage.text}
          </Alert>
        )}
        {status?.injections_enabled && (
          <Alert severity="warning">
            Validation injection routes are enabled in this backend process.
          </Alert>
        )}

        {status && (
          <>
            <Box sx={{ borderTop: 1, borderBottom: 1, borderColor: 'divider', py: 2 }}>
              <Stack
                direction={{ xs: 'column', md: 'row' }}
                spacing={2}
                alignItems={{ xs: 'stretch', md: 'center' }}
                justifyContent="space-between"
              >
                <Box sx={{ minWidth: 0 }}>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      PX4-only SIH
                    </Typography>
                    <Chip
                      size="small"
                      label={readinessLabel(lifecycle.readiness)}
                      color={readinessColor(lifecycle.readiness)}
                    />
                    <Chip size="small" label={status.plan.level} variant="outlined" />
                  </Stack>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, ...breakableTextSx }}>
                    {status.plan.px4_model} on {status.plan.px4_image}
                  </Typography>
                </Box>
                <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                  <Tooltip title={!canManageValidation ? 'System administrator scope is required.' : ''}>
                    <span>
                      <Button
                        variant="contained"
                        startIcon={<PlayArrowIcon />}
                        disabled={!lifecycle.start_available || !canManageValidation || actionPending}
                        onClick={() => setConfirmation('start')}
                      >
                        Start PX4 SIH
                      </Button>
                    </span>
                  </Tooltip>
                  <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<StopIcon />}
                    disabled={!lifecycle.stop_available || !canManageValidation || actionPending}
                    onClick={() => setConfirmation('stop')}
                  >
                    Stop PX4 SIH
                  </Button>
                </Stack>
              </Stack>
            </Box>

            {!lifecycle.feature_enabled && (
              <Alert severity="info">
                PX4-only SIH is opt-in. Enable{' '}
                <Box component="code">Debugging.ENABLE_MANAGED_SIH</Box> in Settings and
                apply the pending PixEagle restart.
              </Alert>
            )}

            <Grid container columnSpacing={4}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.25 }}>
                  Host readiness
                </Typography>
                <StatusRow
                  label="Docker daemon"
                  value={lifecycle.docker_daemon_accessible ? 'Available' : 'Unavailable'}
                  color={lifecycle.docker_daemon_accessible ? 'success' : 'warning'}
                  detail={lifecycle.docker_server_version || undefined}
                />
                <StatusRow
                  label="Pinned PX4 image"
                  value={lifecycle.image_available ? 'Verified' : 'Missing'}
                  color={lifecycle.image_available ? 'success' : 'warning'}
                />
                <StatusRow
                  label="Managed container"
                  value={lifecycle.container_state || 'unknown'}
                  color={lifecycle.container_state === 'conflict' ? 'error' : 'default'}
                  detail={lifecycle.container_id || lifecycle.container_name}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.25 }}>
                  PixEagle boundary
                </Typography>
                <StatusRow
                  label="PX4 connection"
                  value={px4ConnectionLabel(lifecycle.px4_connected)}
                  color={lifecycle.px4_connected === true ? 'success' : 'default'}
                  detail={lifecycle.system_address || undefined}
                />
                <StatusRow
                  label="Following / Offboard"
                  value={controlActivityLabel(
                    lifecycle.control_state_available,
                    lifecycle.control_active
                  )}
                  color={!lifecycle.control_state_available
                    ? 'warning'
                    : (lifecycle.control_active ? 'warning' : 'success')}
                />
                <StatusRow
                  label="MAVLink routing"
                  value="Externally supervised"
                  detail={status.plan.routing_provider}
                />
              </Grid>
            </Grid>

            {!!lifecycle.reasons?.length
              && (lifecycle.readiness !== 'running' || !lifecycle.stop_available) && (
              <Alert severity={lifecycle.readiness === 'conflict' ? 'error' : 'warning'}>
                <Stack spacing={0.25}>
                  {lifecycle.reasons.map((reason) => (
                    <Typography key={reason} variant="body2">
                      {reasonLabel(reason)}
                    </Typography>
                  ))}
                </Stack>
              </Alert>
            )}

            <Accordion disableGutters elevation={0} sx={{ borderTop: 1, borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Latest evidence
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {latestRun.available
                      ? `${latestRun.run_id} - ${latestRun.result || 'unknown'} - ${formatTimestamp(latestRun.updated_at)}`
                      : 'No local validation manifest'}
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {latestRun.available ? (
                  <Stack spacing={1.25}>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={latestRun.result || 'unknown'} color={resultColor(latestRun.result)} />
                      <Chip size="small" label={latestRun.mode || 'mode unknown'} variant="outlined" />
                      <Chip
                        size="small"
                        label={`${latestRun.missing_or_placeholder_count || 0} missing artifacts`}
                        color={latestRun.missing_or_placeholder_count ? 'warning' : 'success'}
                        variant="outlined"
                      />
                    </Stack>
                    <Typography variant="body2">{latestRun.result_reason || 'No result reason provided.'}</Typography>
                    <Typography variant="caption" color="text.secondary" sx={breakableTextSx}>
                      {latestRun.artifact_dir || 'Artifact directory unavailable'}
                    </Typography>
                    {!!missingPreview.length && (
                      <Box>
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                          Missing or placeholder artifacts
                        </Typography>
                        {missingPreview.map((artifact) => (
                          <Typography key={artifact} variant="body2" sx={breakableTextSx}>
                            {artifact}
                          </Typography>
                        ))}
                      </Box>
                    )}
                    <FailureList label="Semantic failures" items={latestRun.semantic_failures} />
                    <FailureList label="Artifact content failures" items={latestRun.artifact_content_failures} />
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No local evidence has been collected for this profile.
                  </Typography>
                )}
              </AccordionDetails>
            </Accordion>

            <Accordion disableGutters elevation={0} sx={{ borderTop: 1, borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                    Advanced terminal workflow
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Plan validation, prepared-stack probes, and evidence collection
                  </Typography>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2} divider={<Divider flexItem />}>
                  {(status.commands || []).map((command) => (
                    <Box key={command.mode} sx={{ minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                        <Typography variant="body2" sx={{ fontWeight: 700 }}>
                          {command.label}
                        </Typography>
                        <Chip size="small" label={commandModeLabel(command)} variant="outlined" />
                      </Stack>
                      <Box
                        component="pre"
                        sx={{
                          m: 0,
                          mt: 1,
                          p: 1.25,
                          borderRadius: 1,
                          bgcolor: 'action.hover',
                          fontFamily: 'monospace',
                          fontSize: 13,
                          whiteSpace: 'pre-wrap',
                          ...breakableTextSx,
                        }}
                      >
                        {command.command}
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.75, display: 'block' }}>
                        {command.claim_boundary}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </AccordionDetails>
            </Accordion>
          </>
        )}
      </Stack>

      <Dialog
        open={Boolean(confirmation)}
        onClose={actionPending ? undefined : () => setConfirmation(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {confirmation === 'start' ? 'Start PX4 SIH?' : 'Stop PX4 SIH?'}
        </DialogTitle>
        <DialogContent dividers>
          <Stack spacing={1.5}>
            {confirmation === 'start' && (
              <Alert severity="warning">
                Confirm that no real aircraft, HIL rig, or motor-enabled hardware is connected.
              </Alert>
            )}
            <Typography variant="body2">
              PixEagle will {confirmation} only its pinned, ownership-labeled PX4 SIH
              container. MAVLink routing and supporting services are not changed.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmation(null)} disabled={actionPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color={confirmation === 'stop' ? 'warning' : 'primary'}
            onClick={confirmLifecycleAction}
            disabled={actionPending}
          >
            {actionPending ? 'Applying...' : 'Confirm'}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ValidationPage;
