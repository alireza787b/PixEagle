// dashboard/src/components/config/SyncWithDefaultsDialog.js
import React, { useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import {
  Alert,
  Badge,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Tab,
  Tabs,
  Typography,
  useMediaQuery,
} from '@mui/material';
import {
  Add,
  CheckCircle,
  Delete,
  Edit,
  Sync,
  Warning,
} from '@mui/icons-material';
import { useTheme } from '@mui/material/styles';

import {
  getConfigSyncItemKey,
  getConfigSyncItemPath,
} from '../../hooks/useDefaultsSync';

const EMPTY_SET = new Set();
const PLAN_DIGEST_PATTERN = /^[a-f0-9]{64}$/i;
const WRAPPING_CHIP_SX = {
  height: 'auto',
  maxWidth: '100%',
  '& .MuiChip-label': {
    display: 'block',
    py: 0.5,
    whiteSpace: 'normal',
    overflowWrap: 'anywhere',
  },
};

const TabPanel = ({ children, value, index }) => (
  <Box
    role="tabpanel"
    id={`config-sync-tabpanel-${index}`}
    aria-labelledby={`config-sync-tab-${index}`}
    hidden={value !== index}
    sx={{ pt: 2 }}
  >
    {value === index && children}
  </Box>
);

TabPanel.propTypes = {
  children: PropTypes.node,
  value: PropTypes.number.isRequired,
  index: PropTypes.number.isRequired,
};

const groupBySection = (items) => {
  const grouped = {};
  items.forEach((item) => {
    const path = getConfigSyncItemPath(item);
    const section = path.length === 1 ? 'Root' : (path[0] || 'Uncategorized');
    if (!grouped[section]) {
      grouped[section] = [];
    }
    grouped[section].push(item);
  });
  return grouped;
};

const itemDisplayName = (item) => {
  const path = getConfigSyncItemPath(item);
  if (path.length === 1) return path[0];
  if (path.length === 2) return path[1];
  return 'Unknown path';
};

const previewMessage = (entry, fallback) => (
  entry?.warning || entry?.error || entry?.message || fallback
);

const formatValue = (value) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

const SyncWithDefaultsDialog = ({
  open,
  onClose,
  onMessage,
  onRebootRequired,
  defaultsSync,
}) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'));
  const {
    newParameters,
    changedDefaults,
    registeredRetirements,
    unknownExtensions,
    counts,
    meta,
    loading,
    error,
    reportAvailable,
    planning,
    applying,
    refresh,
    buildOperationsFromSelections,
    previewOperations,
    applyOperations,
  } = defaultsSync;

  const [tabIndex, setTabIndex] = useState(0);
  const [selectedNew, setSelectedNew] = useState(EMPTY_SET);
  const [selectedChanged, setSelectedChanged] = useState(EMPTY_SET);
  const [selectedRetired, setSelectedRetired] = useState(EMPTY_SET);
  const [planResult, setPlanResult] = useState(null);
  const previewGenerationRef = useRef(0);

  const groupedNew = useMemo(() => groupBySection(newParameters), [newParameters]);
  const groupedChanged = useMemo(() => groupBySection(changedDefaults), [changedDefaults]);
  const groupedRetired = useMemo(
    () => groupBySection(registeredRetirements),
    [registeredRetirements]
  );

  const firstRelevantTab = useMemo(() => {
    if (counts.new > 0) return 0;
    if (counts.changed > 0) return 1;
    if (counts.retired > 0) return 2;
    return 0;
  }, [counts.new, counts.changed, counts.retired]);

  useEffect(() => {
    if (!open) return undefined;
    previewGenerationRef.current += 1;
    refresh();
    return undefined;
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    setSelectedNew(new Set(newParameters.map(getConfigSyncItemKey).filter(Boolean)));
    setSelectedChanged(new Set());
    setSelectedRetired(new Set());
    setPlanResult(null);
  }, [open, newParameters]);

  useEffect(() => {
    if (open && reportAvailable) {
      setTabIndex(firstRelevantTab);
    }
  }, [open, reportAvailable, firstRelevantTab]);

  const totalSelected = selectedNew.size + selectedChanged.size + selectedRetired.size;

  const setFromItems = (items) => new Set(items.map(getConfigSyncItemKey).filter(Boolean));

  const replaceSelection = (setter, nextSelection) => {
    setter(nextSelection);
    previewGenerationRef.current += 1;
    setPlanResult(null);
  };

  const toggle = (setter, item) => {
    const key = getConfigSyncItemKey(item);
    if (!key) return;
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    previewGenerationRef.current += 1;
    setPlanResult(null);
  };

  const selectedOperations = useMemo(
    () => buildOperationsFromSelections({
      selectedNew: Array.from(selectedNew),
      selectedChanged: Array.from(selectedChanged),
      selectedRetired: Array.from(selectedRetired),
    }),
    [
      buildOperationsFromSelections,
      selectedNew,
      selectedChanged,
      selectedRetired,
    ]
  );
  const selectedOperationsKey = useMemo(
    () => JSON.stringify(selectedOperations),
    [selectedOperations]
  );
  const previewMatchesSelection = planResult?.operationsKey === selectedOperationsKey;
  const currentPlanDigest = (
    planResult?.success
    && previewMatchesSelection
    && planResult.plan?.valid === true
    && PLAN_DIGEST_PATTERN.test(planResult.plan?.plan_digest || '')
  ) ? planResult.plan.plan_digest : null;

  const handlePreview = async () => {
    const operations = selectedOperations;
    if (operations.length === 0) {
      onMessage?.('Select at least one item before previewing', 'warning');
      return;
    }
    const operationsKey = selectedOperationsKey;
    const generation = previewGenerationRef.current + 1;
    previewGenerationRef.current = generation;
    const result = await previewOperations(operations);
    if (generation !== previewGenerationRef.current) return;
    if (!result.success) {
      onMessage?.(`Preview failed: ${result.error}`, 'error');
    }
    setPlanResult({ ...result, operationsKey });
  };

  const handleApply = async () => {
    const operations = selectedOperations;
    if (operations.length === 0) {
      onMessage?.('Select at least one item to apply', 'warning');
      return;
    }

    const result = await applyOperations(operations, currentPlanDigest);
    if (!result.success) {
      previewGenerationRef.current += 1;
      setPlanResult(null);
      onMessage?.(`Apply failed: ${result.error}`, 'error');
      await refresh();
      return;
    }

    const applied = result.result?.applied_count || 0;
    const skipped = result.result?.skipped_count || 0;
    onMessage?.(`Config sync applied (${applied} applied, ${skipped} skipped)`, 'success');
    setPlanResult(null);

    // Notify parent about parameters that require restart
    if (onRebootRequired) {
      const appliedOps = result.result?.applied_operations || [];
      appliedOps.forEach((op) => {
        if (op.reload_tier && op.reload_tier !== 'immediate') {
          const path = getConfigSyncItemPath(op);
          const section = path.length === 1 ? 'Root' : path[0];
          const parameter = path.length === 1 ? path[0] : path[1];
          onRebootRequired(section, parameter, op.reload_tier);
        }
      });
    }
  };

  const handleClose = (event, reason) => {
    if (planning || applying) return;
    onClose(event, reason);
  };

  const renderList = (grouped, selectedSet, setter, variant) => (
    <>
      <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
        <Button
          size="small"
          onClick={() => replaceSelection(
            setter,
            setFromItems(Object.values(grouped).flat())
          )}
        >
          Select All
        </Button>
        <Button size="small" onClick={() => replaceSelection(setter, new Set())}>
          Select None
        </Button>
        <Chip
          size="small"
          color={selectedSet.size > 0 ? 'primary' : 'default'}
          label={`${selectedSet.size} selected`}
        />
      </Box>

      <List dense>
        {Object.entries(grouped).map(([section, items]) => (
          <Box key={section} sx={{ mb: 1.5 }}>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>{section}</Typography>
            {items.map((item) => {
              const key = getConfigSyncItemKey(item);
              const isSelected = selectedSet.has(key);
              return (
                <ListItem key={key} disablePadding sx={{ borderRadius: 1 }}>
                  <ListItemButton
                    onClick={() => toggle(setter, item)}
                    selected={isSelected}
                    sx={{ borderRadius: 1, alignItems: 'flex-start', minWidth: 0 }}
                  >
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      <Checkbox
                        checked={isSelected}
                        size="small"
                        tabIndex={-1}
                        disableRipple
                        inputProps={{ 'aria-label': `Select ${getConfigSyncItemPath(item).join('.')}` }}
                      />
                    </ListItemIcon>
                    <ListItemText
                    secondaryTypographyProps={{ component: 'div' }}
                    sx={{ minWidth: 0, overflowWrap: 'anywhere' }}
                    primary={
                      <Typography variant="body2" fontFamily="monospace" sx={{ overflowWrap: 'anywhere' }}>
                        {itemDisplayName(item)}
                      </Typography>
                    }
                    secondary={
                      <Box>
                        {item.description && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                            {item.description}
                          </Typography>
                        )}
                        {variant === 'new' && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={`Default: ${formatValue(item.default_value)}`}
                            sx={WRAPPING_CHIP_SX}
                          />
                        )}
                        {variant === 'changed' && (
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            <Chip size="small" variant="outlined" label={`Old: ${formatValue(item.old_default)}`} sx={WRAPPING_CHIP_SX} />
                            <Chip size="small" variant="outlined" label={`New: ${formatValue(item.new_default)}`} sx={WRAPPING_CHIP_SX} />
                            <Chip
                              size="small"
                              variant="outlined"
                              label={item.matches_old_default ? 'Local: old default' : 'Local: customized'}
                              sx={WRAPPING_CHIP_SX}
                            />
                          </Box>
                        )}
                        {variant === 'retired' && (
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            <Chip size="small" variant="outlined" label={item.reason} sx={WRAPPING_CHIP_SX} />
                            {item.replacement && (
                              <Chip size="small" variant="outlined" label={`Use: ${item.replacement.join('.')}`} sx={WRAPPING_CHIP_SX} />
                            )}
                          </Box>
                        )}
                      </Box>
                    }
                    />
                  </ListItemButton>
                </ListItem>
              );
            })}
          </Box>
        ))}
      </List>
    </>
  );

  if (loading && open) {
    return (
      <Dialog
        open={open}
        onClose={handleClose}
        maxWidth={fullScreen ? false : 'lg'}
        fullWidth={!fullScreen}
        fullScreen={fullScreen}
        PaperProps={{
          sx: {
            width: fullScreen ? '100%' : 'min(1200px, 96vw)',
            maxWidth: '96vw',
            maxHeight: fullScreen ? '100vh' : '92vh',
            m: fullScreen ? 0 : 2,
            overflow: 'hidden'
          }
        }}
      >
        <DialogContent sx={{ overflowX: 'hidden', minWidth: 0 }}>
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
            <CircularProgress />
          </Box>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth={fullScreen ? false : 'lg'}
      fullWidth={!fullScreen}
      fullScreen={fullScreen}
      PaperProps={{
        sx: {
          width: fullScreen ? '100%' : 'min(1200px, 96vw)',
          maxWidth: '96vw',
          maxHeight: fullScreen ? '100vh' : '92vh',
          m: fullScreen ? 0 : 2,
          overflow: 'hidden'
        }
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Sync color="info" />
        Config Sync
        {counts.actionable > 0 && <Chip label={`${counts.actionable} actions`} color="info" size="small" />}
      </DialogTitle>

      <DialogContent dividers sx={{ overflowX: 'hidden', minWidth: 0 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {!reportAvailable ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Warning sx={{ fontSize: 56, color: 'warning.main', mb: 1 }} />
            <Typography variant="h6" color="text.secondary">
              Config migration status unavailable
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Refresh after the Config Sync v2 service is available.
            </Typography>
          </Box>
        ) : (
          <>
            <Alert severity="info" sx={{ mb: 2 }}>
              Review changes, preview migration, then apply through the guarded rollback transaction. Your config values are never overwritten unless selected.
            </Alert>

            {unknownExtensions.length > 0 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                {unknownExtensions.length} unmanaged extension path(s) are preserved and cannot be removed by this tool.
              </Alert>
            )}

            {counts.actionable === 0 ? (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                {meta.baselineAvailable ? (
                  <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 1 }} />
                ) : (
                  <Warning sx={{ fontSize: 56, color: 'warning.main', mb: 1 }} />
                )}
                <Typography variant="h6" color="text.secondary">
                  {meta.baselineAvailable
                    ? 'No config migration is required'
                    : 'No actionable migration detected'}
                </Typography>
                {!meta.baselineAvailable && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Changed-default comparison is unavailable until a pre-update baseline exists.
                  </Typography>
                )}
              </Box>
            ) : (
              <>
            <Tabs
              value={tabIndex}
              onChange={(e, v) => setTabIndex(v)}
              variant="fullWidth"
              aria-label="Config Sync categories"
              sx={{ mb: 1 }}
            >
              <Tab
                id="config-sync-tab-0"
                aria-controls="config-sync-tabpanel-0"
                disabled={counts.new === 0}
                label={<Badge badgeContent={counts.new} color="success"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Add fontSize="small" />New</Box></Badge>}
              />
              <Tab
                id="config-sync-tab-1"
                aria-controls="config-sync-tabpanel-1"
                disabled={counts.changed === 0 && meta.baselineAvailable}
                label={<Badge badgeContent={counts.changed} color="warning"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Edit fontSize="small" />Changed</Box></Badge>}
              />
              <Tab
                id="config-sync-tab-2"
                aria-controls="config-sync-tabpanel-2"
                disabled={counts.retired === 0}
                label={<Badge badgeContent={counts.retired} color="error"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Delete fontSize="small" />Retired</Box></Badge>}
              />
            </Tabs>

            <TabPanel value={tabIndex} index={0}>
              {counts.new === 0 ? (
                <Typography color="text.secondary">No new parameters detected.</Typography>
              ) : renderList(groupedNew, selectedNew, setSelectedNew, 'new')}
            </TabPanel>

            <TabPanel value={tabIndex} index={1}>
              {!meta.baselineAvailable ? (
                <Alert severity="info">
                  No pre-update defaults baseline is available, so changed-default comparison is unavailable. Initialize it with the documented setup command before the next source update.
                </Alert>
              ) : counts.changed === 0 ? (
                <Typography color="text.secondary">No default changes detected since baseline.</Typography>
              ) : (
                renderList(groupedChanged, selectedChanged, setSelectedChanged, 'changed')
              )}
            </TabPanel>

            <TabPanel value={tabIndex} index={2}>
              {counts.retired === 0 ? (
                <Typography color="text.secondary">No registered retirements are present.</Typography>
              ) : (
                <>
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    Retired keys are removed only after explicit selection and preview. The owner-only backup preserves rollback history.
                  </Alert>
                  {renderList(groupedRetired, selectedRetired, setSelectedRetired, 'retired')}
                </>
              )}
            </TabPanel>

            <Divider sx={{ my: 2 }} />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap', minWidth: 0 }}>
              <Chip label={`${totalSelected} selected`} color={totalSelected > 0 ? 'primary' : 'default'} sx={WRAPPING_CHIP_SX} />
              <Chip label={`Schema ${meta.schemaVersion}`} size="small" variant="outlined" sx={WRAPPING_CHIP_SX} />
              {meta.retirementRegistryVersion && (
                <Chip label={`Retirements v${meta.retirementRegistryVersion}`} size="small" variant="outlined" sx={WRAPPING_CHIP_SX} />
              )}
              {meta.baselineSavedAt && (
                <Chip label={`Baseline: ${new Date(meta.baselineSavedAt).toLocaleString()}`} size="small" variant="outlined" sx={WRAPPING_CHIP_SX} />
              )}
            </Box>

            {planResult?.success && planResult.plan && (
              <Alert
                severity={
                  !previewMatchesSelection
                    ? 'warning'
                    : (planResult.plan.valid
                      ? (planResult.plan.warnings?.length > 0 ? 'warning' : 'success')
                      : 'error')
                }
                sx={{ mt: 1 }}
              >
                {!previewMatchesSelection && (
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    Selection changed after this preview. Preview again before applying.
                  </Typography>
                )}
                <Typography variant="body2">
                  Preview: {planResult.plan.summary?.applicable ?? 0} applicable, {planResult.plan.summary?.skipped ?? 0} skipped.
                </Typography>
                {planResult.plan.warnings?.length > 0 && (
                  <Box component="ul" aria-label="Preview warnings" sx={{ mt: 0.5, mb: 0, pl: 2.5 }}>
                    {planResult.plan.warnings.map((warning, index) => (
                      <Typography component="li" variant="caption" key={`warning-${warning?.index ?? index}`}>
                        {previewMessage(warning, `Warning ${index + 1}`)}
                      </Typography>
                    ))}
                  </Box>
                )}
                {planResult.plan.errors?.length > 0 && (
                  <Box component="ul" aria-label="Preview errors" sx={{ mt: 0.5, mb: 0, pl: 2.5 }}>
                    {planResult.plan.errors.map((planError, index) => (
                      <Typography component="li" variant="caption" key={`error-${planError?.index ?? index}`}>
                        {previewMessage(planError, `Error ${index + 1}`)}
                      </Typography>
                    ))}
                  </Box>
                )}
              </Alert>
            )}

            {planResult && !planResult.success && (
              <Alert severity="error" sx={{ mt: 1 }}>
                {planResult.error || 'Could not generate migration preview.'}
              </Alert>
            )}
              </>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions
        data-testid="config-sync-actions"
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 1,
          overflowX: 'hidden',
          px: 2,
          py: 1.5,
          '& > :not(style) ~ :not(style)': { ml: 0 },
          '& .MuiButton-root': {
            flex: { xs: '1 1 calc(50% - 8px)', sm: '0 1 auto' },
            minWidth: 0,
            maxWidth: '100%',
            whiteSpace: 'normal',
          },
        }}
      >
        <Button
          onClick={refresh}
          disabled={loading || planning || applying}
          sx={{ mr: { sm: 'auto' } }}
        >
          Refresh
        </Button>
        <Button onClick={handleClose} disabled={planning || applying}>Close</Button>
        <Button
          variant="outlined"
          onClick={handlePreview}
          disabled={!reportAvailable || planning || applying || totalSelected === 0}
          startIcon={planning ? <CircularProgress size={16} /> : <Sync />}
        >
          Preview
        </Button>
        <Button
          variant="contained"
          onClick={handleApply}
          disabled={
            applying
            || planning
            || !reportAvailable
            || totalSelected === 0
            || !currentPlanDigest
          }
          startIcon={applying ? <CircularProgress size={16} /> : <Warning />}
        >
          Apply Previewed
        </Button>
      </DialogActions>
    </Dialog>
  );
};

SyncWithDefaultsDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onMessage: PropTypes.func,
  onRebootRequired: PropTypes.func,
  defaultsSync: PropTypes.shape({
    newParameters: PropTypes.array.isRequired,
    changedDefaults: PropTypes.array.isRequired,
    registeredRetirements: PropTypes.array.isRequired,
    unknownExtensions: PropTypes.array.isRequired,
    counts: PropTypes.object.isRequired,
    meta: PropTypes.object.isRequired,
    loading: PropTypes.bool.isRequired,
    error: PropTypes.string,
    reportAvailable: PropTypes.bool.isRequired,
    planning: PropTypes.bool.isRequired,
    applying: PropTypes.bool.isRequired,
    refresh: PropTypes.func.isRequired,
    buildOperationsFromSelections: PropTypes.func.isRequired,
    previewOperations: PropTypes.func.isRequired,
    applyOperations: PropTypes.func.isRequired,
  }).isRequired,
};

export default SyncWithDefaultsDialog;
