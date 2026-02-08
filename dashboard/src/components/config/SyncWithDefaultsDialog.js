// dashboard/src/components/config/SyncWithDefaultsDialog.js
import React, { useEffect, useMemo, useState } from 'react';
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

import { useDefaultsSync } from '../../hooks/useDefaultsSync';

const EMPTY_SET = new Set();

const toKey = (section, parameter) => `${section}.${parameter}`;

const TabPanel = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
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
    const section = item.section || 'Uncategorized';
    if (!grouped[section]) {
      grouped[section] = [];
    }
    grouped[section].push(item);
  });
  return grouped;
};

const formatValue = (value) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'object') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

const SyncWithDefaultsDialog = ({ open, onClose, onMessage }) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'));
  const {
    newParameters,
    changedDefaults,
    removedParameters,
    counts,
    meta,
    loading,
    error,
    planning,
    applying,
    refresh,
    buildOperationsFromSelections,
    previewOperations,
    applyOperations,
  } = useDefaultsSync();

  const [tabIndex, setTabIndex] = useState(0);
  const [selectedNew, setSelectedNew] = useState(EMPTY_SET);
  const [selectedChanged, setSelectedChanged] = useState(EMPTY_SET);
  const [selectedRemoved, setSelectedRemoved] = useState(EMPTY_SET);
  const [planResult, setPlanResult] = useState(null);

  const groupedNew = useMemo(() => groupBySection(newParameters), [newParameters]);
  const groupedChanged = useMemo(() => groupBySection(changedDefaults), [changedDefaults]);
  const groupedRemoved = useMemo(() => groupBySection(removedParameters), [removedParameters]);

  useEffect(() => {
    if (!open) return;
    setSelectedNew(new Set(newParameters.map((item) => toKey(item.section, item.parameter))));
    setSelectedChanged(new Set());
    setSelectedRemoved(new Set(removedParameters.map((item) => toKey(item.section, item.parameter))));
    setPlanResult(null);
  }, [open, newParameters, removedParameters]);

  const totalSelected = selectedNew.size + selectedChanged.size + selectedRemoved.size;

  const setFromItems = (items) => new Set(items.map((item) => toKey(item.section, item.parameter)));

  const toggle = (setter, section, parameter) => {
    const key = toKey(section, parameter);
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
    setPlanResult(null);
  };

  const getSelectedOperations = () => buildOperationsFromSelections({
    selectedNew: Array.from(selectedNew),
    selectedChanged: Array.from(selectedChanged),
    selectedRemoved: Array.from(selectedRemoved),
  });

  const handlePreview = async () => {
    const operations = getSelectedOperations();
    if (operations.length === 0) {
      onMessage?.('Select at least one item before previewing', 'warning');
      return;
    }
    const result = await previewOperations(operations);
    if (!result.success) {
      onMessage?.(`Preview failed: ${result.error}`, 'error');
    }
    setPlanResult(result);
  };

  const handleApply = async () => {
    const operations = getSelectedOperations();
    if (operations.length === 0) {
      onMessage?.('Select at least one item to apply', 'warning');
      return;
    }

    const result = await applyOperations(operations);
    if (!result.success) {
      onMessage?.(`Apply failed: ${result.error}`, 'error');
      return;
    }

    const applied = result.result?.applied_count || 0;
    const skipped = result.result?.skipped_count || 0;
    onMessage?.(`Config sync applied (${applied} applied, ${skipped} skipped)`, 'success');
    setPlanResult(null);
  };

  const renderList = (grouped, selectedSet, setter, variant) => (
    <>
      <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
        <Button size="small" onClick={() => { setter(setFromItems(Object.values(grouped).flat())); setPlanResult(null); }}>
          Select All
        </Button>
        <Button size="small" onClick={() => { setter(new Set()); setPlanResult(null); }}>
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
              const key = toKey(item.section, item.parameter);
              const isSelected = selectedSet.has(key);
              return (
                <ListItem
                  key={key}
                  button
                  onClick={() => toggle(setter, item.section, item.parameter)}
                  sx={{ borderRadius: 1 }}
                >
                  <ListItemIcon>
                    <Checkbox checked={isSelected} size="small" />
                  </ListItemIcon>
                  <ListItemText
                    primary={
                      <Typography variant="body2" fontFamily="monospace">
                        {item.parameter}
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
                          <Chip size="small" variant="outlined" label={`Default: ${formatValue(item.default_value)}`} />
                        )}
                        {variant === 'changed' && (
                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                            <Chip size="small" variant="outlined" label={`Old: ${formatValue(item.old_default)}`} />
                            <Chip size="small" variant="outlined" label={`New: ${formatValue(item.new_default)}`} />
                            <Chip size="small" variant="outlined" label={`Current: ${formatValue(item.user_value)}`} />
                          </Box>
                        )}
                        {variant === 'removed' && (
                          <Chip size="small" variant="outlined" label={`Current: ${formatValue(item.current_value)}`} />
                        )}
                      </Box>
                    }
                  />
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
        onClose={onClose}
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
        <DialogContent sx={{ overflowX: 'auto', minWidth: 0 }}>
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
      onClose={onClose}
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
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Sync color="info" />
        Config Sync
        {counts.total > 0 && <Chip label={`${counts.total} items`} color="info" size="small" />}
      </DialogTitle>

      <DialogContent dividers sx={{ overflowX: 'auto', minWidth: 0 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Alert severity="info" sx={{ mb: 2 }}>
          Review changes, preview migration, then apply atomically. Your config values are never overwritten unless selected.
        </Alert>

        {meta.baselineInitialized && (
          <Alert severity="success" sx={{ mb: 2 }}>
            Defaults baseline initialized. Changed-default detection will be available for future upgrades.
          </Alert>
        )}

        {counts.total === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 1 }} />
            <Typography variant="h6" color="text.secondary">Configuration is in sync</Typography>
          </Box>
        ) : (
          <>
            <Tabs value={tabIndex} onChange={(e, v) => setTabIndex(v)} variant="fullWidth" sx={{ mb: 1 }}>
              <Tab
                disabled={counts.new === 0}
                label={<Badge badgeContent={counts.new} color="success"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Add fontSize="small" />New</Box></Badge>}
              />
              <Tab
                disabled={counts.changed === 0 && meta.baselineAvailable}
                label={<Badge badgeContent={counts.changed} color="warning"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Edit fontSize="small" />Changed</Box></Badge>}
              />
              <Tab
                disabled={counts.removed === 0}
                label={<Badge badgeContent={counts.removed} color="error"><Box sx={{ display: 'flex', gap: 0.5, pr: 1 }}><Delete fontSize="small" />Obsolete</Box></Badge>}
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
                  Changed-default tracking needs one baseline snapshot. It has been initialized now and will start reporting on future default updates.
                </Alert>
              ) : counts.changed === 0 ? (
                <Typography color="text.secondary">No default changes detected since baseline.</Typography>
              ) : (
                renderList(groupedChanged, selectedChanged, setSelectedChanged, 'changed')
              )}
            </TabPanel>

            <TabPanel value={tabIndex} index={2}>
              {counts.removed === 0 ? (
                <Typography color="text.secondary">No obsolete parameters detected.</Typography>
              ) : (
                <>
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    Selected obsolete keys will be archived under `_ARCHIVED_OBSOLETE` and removed from active config.
                  </Alert>
                  {renderList(groupedRemoved, selectedRemoved, setSelectedRemoved, 'removed')}
                </>
              )}
            </TabPanel>

            <Divider sx={{ my: 2 }} />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Chip label={`${totalSelected} selected`} color={totalSelected > 0 ? 'primary' : 'default'} />
              <Chip label={`Schema ${meta.schemaVersion}`} size="small" variant="outlined" />
              {meta.baselineSavedAt && (
                <Chip label={`Baseline: ${new Date(meta.baselineSavedAt).toLocaleString()}`} size="small" variant="outlined" />
              )}
            </Box>

            {planResult?.success && planResult.plan && (
              <Alert severity={planResult.plan.valid ? 'success' : 'error'} sx={{ mt: 1 }}>
                <Typography variant="body2">
                  Preview: {planResult.plan.summary.applicable} applicable, {planResult.plan.summary.skipped} skipped.
                </Typography>
                {planResult.plan.warnings?.length > 0 && (
                  <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                    Warnings: {planResult.plan.warnings.length}
                  </Typography>
                )}
                {planResult.plan.errors?.length > 0 && (
                  <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                    Errors: {planResult.plan.errors.map((e) => e.error).join(' | ')}
                  </Typography>
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
      </DialogContent>

      <DialogActions>
        <Button onClick={refresh} disabled={loading || planning || applying}>Refresh</Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose}>Close</Button>
        <Button
          variant="outlined"
          onClick={handlePreview}
          disabled={planning || applying || totalSelected === 0}
          startIcon={planning ? <CircularProgress size={16} /> : <Sync />}
        >
          Preview
        </Button>
        <Button
          variant="contained"
          onClick={handleApply}
          disabled={applying || planning || totalSelected === 0}
          startIcon={applying ? <CircularProgress size={16} /> : <Warning />}
        >
          Apply Selected
        </Button>
      </DialogActions>
    </Dialog>
  );
};

SyncWithDefaultsDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onMessage: PropTypes.func,
};

export default SyncWithDefaultsDialog;
