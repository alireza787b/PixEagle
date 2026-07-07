import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import ScienceIcon from '@mui/icons-material/Science';

import { endpoints } from '../services/apiEndpoints';
import { apiFetch } from '../services/apiClient';
import { useAuthSession } from '../context/AuthSessionContext';

const resultColor = (result) => {
  switch (result) {
    case 'pass':
      return 'success';
    case 'failed':
      return 'error';
    case 'incomplete':
      return 'warning';
    default:
      return 'default';
  }
};

const formatTimestamp = (value) => {
  if (!value) return 'Not available';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
};

const commandModeLabel = (command) => {
  if (command.starts_processes) return 'Starts PX4 only';
  if (command.writes_artifacts) return 'Writes evidence';
  return 'No side effects';
};

const breakableTextSx = {
  overflowWrap: 'anywhere',
  wordBreak: 'break-word',
};

const artifactPillSx = {
  px: 1,
  py: 0.5,
  borderRadius: 1,
  bgcolor: 'action.hover',
  maxWidth: '100%',
};

const FailureList = ({ label, items }) => {
  if (!items?.length) return null;
  return (
    <Alert severity="warning">
      <Stack spacing={0.5}>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>
          {label}
        </Typography>
        {items.map((item) => (
          <Typography key={item} variant="body2" sx={breakableTextSx}>
            {item}
          </Typography>
        ))}
      </Stack>
    </Alert>
  );
};

const ValidationPage = () => {
  const authSession = useAuthSession();
  const canReadValidation = authSession.hasScope('debug:read');
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusStale, setStatusStale] = useState(false);

  const latestRun = status?.latest_run || {};
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
      setStatus(await response.json());
      setStatusStale(false);
    } catch (err) {
      setError(err.message || 'Failed to load validation status.');
      setStatusStale(true);
    } finally {
      setLoading(false);
    }
  }, [canReadValidation]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  if (!canReadValidation) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Alert severity="warning">
          Validation status requires debug access.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Stack spacing={2.5}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
            <ScienceIcon color="primary" />
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                Validation
              </Typography>
              <Typography variant="body2" color="text.secondary">
                SIH Dev/Training evidence surface
              </Typography>
            </Box>
          </Box>
          <Button
            startIcon={<RefreshIcon />}
            onClick={fetchStatus}
            disabled={loading}
            variant="outlined"
            size="small"
          >
            Refresh
          </Button>
        </Box>

        {loading && <LinearProgress />}
        {error && <Alert severity="error">{error}</Alert>}
        {status && statusStale && (
          <Alert severity="warning">
            Showing the last loaded validation data because the latest refresh failed.
          </Alert>
        )}
        {status?.claim_boundary && (
          <Alert severity="info">
            {status.claim_boundary}
          </Alert>
        )}
        {status?.injections_enabled && (
          <Alert severity="warning">
            SITL injection routes are enabled in this backend process. Keep this
            mode only for an operator-approved validation stack.
          </Alert>
        )}

        {status && (
          <>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="overline" color="text.secondary">
                      Profile
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      Official PX4 SIH
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap', rowGap: 1 }}>
                      <Chip size="small" label={status.plan.level} color="primary" />
                      <Chip size="small" label={status.plan.routing_provider} />
                      <Chip
                        size="small"
                        label={status.injections_enabled ? 'Injections enabled' : 'Injections disabled'}
                        color={status.injections_enabled ? 'warning' : 'success'}
                      />
                    </Stack>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="overline" color="text.secondary">
                      Plan
                    </Typography>
                    <Typography variant="body1" sx={{ fontWeight: 700 }}>
                      {status.plan.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {status.plan.scenario_count} scenarios · {status.plan.evidence_artifact_count} evidence artifacts
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1, wordBreak: 'break-all' }}>
                      {status.plan.source}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardContent>
                    <Typography variant="overline" color="text.secondary">
                      Latest Evidence
                    </Typography>
                    {latestRun.available ? (
                      <>
                        <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap', rowGap: 1 }}>
                          <Chip
                            size="small"
                            label={latestRun.result || 'unknown'}
                            color={resultColor(latestRun.result)}
                          />
                          <Chip size="small" label={latestRun.mode || 'mode unknown'} />
                        </Stack>
                        <Typography variant="body2" sx={breakableTextSx}>
                          {latestRun.run_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                          Updated {formatTimestamp(latestRun.updated_at)}
                        </Typography>
                      </>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        No local SIH manifest found.
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
                Terminal Commands
              </Typography>
              <Grid container spacing={2}>
                {(status.commands || []).map((command) => (
                  <Grid item xs={12} md={4} key={command.mode}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Stack spacing={1.25}>
                          <Box>
                            <Typography variant="body1" sx={{ fontWeight: 700 }}>
                              {command.label}
                            </Typography>
                            <Stack direction="row" spacing={1} sx={{ mt: 0.75, flexWrap: 'wrap', rowGap: 1 }}>
                              <Chip
                                size="small"
                                label={commandModeLabel(command)}
                                color={command.starts_processes ? 'warning' : command.writes_artifacts ? 'info' : 'default'}
                              />
                              {command.requires_operator_stack && (
                                <Chip
                                  size="small"
                                  label="Requires prepared stack"
                                  color="warning"
                                  variant="outlined"
                                />
                              )}
                            </Stack>
                          </Box>
                          <Box
                            component="pre"
                            sx={{
                              m: 0,
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
                          <Typography variant="caption" color="text.secondary">
                            {command.claim_boundary}
                          </Typography>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>

            <Card>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Latest Manifest Details
                </Typography>
                <Divider sx={{ my: 1.5 }} />
                {latestRun.available ? (
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={4}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Result Reason
                      </Typography>
                      <Typography variant="body2">
                        {latestRun.result_reason || 'Not provided'}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Artifact Directory
                      </Typography>
                      <Typography variant="body2" sx={breakableTextSx}>
                        {latestRun.artifact_dir || 'Not available'}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Scenario Execution
                      </Typography>
                      <Typography variant="body2">
                        {latestRun.scenario_execution_enabled ? 'Enabled' : 'Disabled'}
                        {latestRun.control_actions_allowed ? ' · control actions allowed' : ''}
                      </Typography>
                    </Grid>
                    <Grid item xs={12}>
                      <Stack spacing={1}>
                        <Typography variant="caption" color="text.secondary">
                          Missing or Placeholder Artifacts ({latestRun.missing_or_placeholder_count || 0})
                        </Typography>
                        {missingPreview.length ? (
                          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
                            {missingPreview.map((artifact) => (
                              <Box key={artifact} sx={artifactPillSx}>
                                <Typography variant="caption" sx={breakableTextSx}>
                                  {artifact}
                                </Typography>
                              </Box>
                            ))}
                            {latestRun.missing_or_placeholder_truncated && (
                              <Chip size="small" label="more hidden" color="warning" />
                            )}
                          </Stack>
                        ) : (
                          <Typography variant="body2">None reported.</Typography>
                        )}
                      </Stack>
                    </Grid>
                    {!!latestRun.semantic_failures?.length && (
                      <Grid item xs={12} md={6}>
                        <FailureList
                          label="Semantic failures"
                          items={latestRun.semantic_failures}
                        />
                      </Grid>
                    )}
                    {!!latestRun.artifact_content_failures?.length && (
                      <Grid item xs={12} md={6}>
                        <FailureList
                          label="Artifact content failures"
                          items={latestRun.artifact_content_failures}
                        />
                      </Grid>
                    )}
                  </Grid>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Run `make sitl-sih-dry-run` to validate the plan, or use the
                    probe/PX4-only terminal commands after preparing the SIH stack.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </Stack>
    </Container>
  );
};

export default ValidationPage;
