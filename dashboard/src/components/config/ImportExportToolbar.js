// dashboard/src/components/config/ImportExportToolbar.js
/**
 * Organized 3-tier toolbar for config import/export operations (v5.4.0+)
 *
 * Layout organized by usage frequency:
 * - Tier 1 (Primary): View Changes, Sync Defaults
 * - Tier 2 (Secondary): Export/Import, History/Audit, Refresh
 * - Tier 3 (Destructive): Reset to Defaults
 */

import React, { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import {
  Box, Button, IconButton, Tooltip, Divider, Badge,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Typography, FormControlLabel, Checkbox, Alert, Chip,
  CircularProgress, Menu, MenuItem, ListItemIcon, ListItemText,
  Collapse, List, ListItem, ListItemText as MuiListItemText
} from '@mui/material';
import {
  FileUpload, FileDownload, History, Refresh,
  CompareArrows, WarningAmber, ReceiptLong, RestartAlt,
  Sync, MoreVert, ExpandMore, ExpandLess, ArrowForward
} from '@mui/icons-material';

import { alpha } from '@mui/material/styles';
import { useResponsive } from '../../hooks/useResponsive';
import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';
import BackupHistoryDialog from './BackupHistoryDialog';
import AuditLogDialog from './AuditLogDialog';
import { endpoints } from '../../services/apiEndpoints';

/**
 * ImportExportToolbar - Organized 3-tier toolbar for config operations
 *
 * Features:
 * - Tier 1 (Primary): View Changes, Sync Defaults (badges show counts)
 * - Tier 2 (Secondary): Export/Import, History/Audit, Refresh
 * - Tier 3 (Destructive): Reset to Defaults (right-aligned, warning color)
 */
const ImportExportToolbar = ({
  changesCount = 0,
  syncAvailableCount = 0,
  onRefresh,
  onMessage,
  onConfigImported,
  onViewChanges,
  onSyncDefaults,
}) => {
  const { isMobile } = useResponsive();
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetConfirmed, setResetConfirmed] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [moreMenuAnchor, setMoreMenuAnchor] = useState(null);

  // Reset dialog diff preview state (v5.4.1+)
  const [resetDiff, setResetDiff] = useState([]);
  const [resetDiffLoading, setResetDiffLoading] = useState(false);
  const [resetDiffExpanded, setResetDiffExpanded] = useState(false);

  // Fetch diff when reset dialog opens
  const fetchResetDiff = useCallback(async () => {
    setResetDiffLoading(true);
    try {
      const response = await fetch(endpoints.configDiff);
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setResetDiff(data.differences || []);
        }
      }
    } catch (err) {
      console.warn('Failed to fetch diff for reset preview:', err);
    } finally {
      setResetDiffLoading(false);
    }
  }, []);

  // Trigger diff fetch when reset dialog opens
  useEffect(() => {
    if (resetOpen) {
      fetchResetDiff();
      setResetDiffExpanded(false);
    }
  }, [resetOpen, fetchResetDiff]);

  // Format value for display (v5.4.2: improved object display)
  const formatResetValue = (value) => {
    if (value === null || value === undefined) return '(not set)';
    if (typeof value === 'object') {
      const keys = Object.keys(value);
      if (keys.length === 0) return '{}';
      if (keys.length <= 3) return `{${keys.join(', ')}}`;
      return `{${keys.slice(0, 2).join(', ')}... +${keys.length - 2}}`;
    }
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    const str = String(value);
    return str.length > 30 ? str.slice(0, 27) + '...' : str;
  };

  const handleExportClose = (success) => {
    setExportOpen(false);
    if (success) {
      onMessage?.('Configuration exported successfully', 'success');
    }
  };

  const handleImportClose = (imported) => {
    setImportOpen(false);
    if (imported) {
      onMessage?.('Configuration imported successfully', 'success');
      onConfigImported?.();
      onRefresh?.();
    }
  };

  const handleHistoryClose = (restored) => {
    setHistoryOpen(false);
    if (restored) {
      onMessage?.('Configuration restored from backup', 'success');
      onConfigImported?.();
      onRefresh?.();
    }
  };

  const handleResetToDefaults = async () => {
    if (!resetConfirmed) return;

    setResetting(true);
    try {
      const response = await fetch(endpoints.configRevert, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        throw new Error(`Reset failed: ${response.statusText}`);
      }

      onMessage?.('Configuration reset to defaults', 'success');
      onConfigImported?.();
      onRefresh?.();
      setResetOpen(false);
      setResetConfirmed(false);
    } catch (error) {
      onMessage?.(`Failed to reset: ${error.message}`, 'error');
    } finally {
      setResetting(false);
    }
  };

  const handleResetDialogClose = () => {
    setResetOpen(false);
    setResetConfirmed(false);
  };

  const handleMoreMenuClose = () => {
    setMoreMenuAnchor(null);
  };

  // Mobile: Compact layout with overflow menu
  if (isMobile) {
    return (
      <>
        <Box sx={{
          display: 'flex',
          gap: 1,
          alignItems: 'center',
          width: '100%',
          flexWrap: 'wrap'
        }}>
          {/* Tier 1: Primary Actions */}
          <Button
            variant="contained"
            size="small"
            startIcon={<CompareArrows />}
            onClick={onViewChanges}
            disabled={changesCount === 0}
            sx={{ minWidth: 0, px: 1.5 }}
          >
            <Badge badgeContent={changesCount} color="warning" max={99}>
              <Typography variant="button" sx={{ pr: changesCount > 0 ? 1 : 0 }}>
                Changes
              </Typography>
            </Badge>
          </Button>

          {syncAvailableCount > 0 && (
            <Button
              variant="outlined"
              size="small"
              color="info"
              startIcon={<Sync />}
              onClick={onSyncDefaults}
              sx={{ minWidth: 0, px: 1.5 }}
            >
              <Badge badgeContent={syncAvailableCount} color="info" max={99}>
                <Typography variant="button" sx={{ pr: 1 }}>
                  Sync
                </Typography>
              </Badge>
            </Button>
          )}

          <Box sx={{ flexGrow: 1 }} />

          {/* More Menu */}
          <IconButton
            onClick={(e) => setMoreMenuAnchor(e.currentTarget)}
            size="small"
          >
            <MoreVert />
          </IconButton>

          <Menu
            anchorEl={moreMenuAnchor}
            open={Boolean(moreMenuAnchor)}
            onClose={handleMoreMenuClose}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          >
            <MenuItem onClick={() => { setExportOpen(true); handleMoreMenuClose(); }}>
              <ListItemIcon><FileDownload fontSize="small" /></ListItemIcon>
              <ListItemText>Export</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => { setImportOpen(true); handleMoreMenuClose(); }}>
              <ListItemIcon><FileUpload fontSize="small" /></ListItemIcon>
              <ListItemText>Import</ListItemText>
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { setHistoryOpen(true); handleMoreMenuClose(); }}>
              <ListItemIcon><History fontSize="small" /></ListItemIcon>
              <ListItemText>Backup History</ListItemText>
            </MenuItem>
            <MenuItem onClick={() => { setAuditOpen(true); handleMoreMenuClose(); }}>
              <ListItemIcon><ReceiptLong fontSize="small" /></ListItemIcon>
              <ListItemText>Audit Log</ListItemText>
            </MenuItem>
            <Divider />
            <MenuItem onClick={() => { onRefresh?.(); handleMoreMenuClose(); }}>
              <ListItemIcon><Refresh fontSize="small" /></ListItemIcon>
              <ListItemText>Refresh</ListItemText>
            </MenuItem>
            <Divider />
            <MenuItem
              onClick={() => { setResetOpen(true); handleMoreMenuClose(); }}
              sx={{ color: 'warning.main' }}
            >
              <ListItemIcon><RestartAlt fontSize="small" color="warning" /></ListItemIcon>
              <ListItemText>Reset to Defaults</ListItemText>
            </MenuItem>
          </Menu>
        </Box>

        {/* Dialogs */}
        {renderDialogs()}
      </>
    );
  }

  // Helper to render dialogs (shared between mobile and desktop)
  function renderDialogs() {
    return (
      <>
        <ExportDialog
          open={exportOpen}
          onClose={handleExportClose}
          changesCount={changesCount}
        />

        <ImportDialog
          open={importOpen}
          onClose={handleImportClose}
        />

        <BackupHistoryDialog
          open={historyOpen}
          onClose={handleHistoryClose}
        />

        <AuditLogDialog
          open={auditOpen}
          onClose={() => setAuditOpen(false)}
        />

        {/* Reset to Defaults Confirmation Dialog (v5.4.1+ enhanced with diff preview) */}
        <Dialog
          open={resetOpen}
          onClose={handleResetDialogClose}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <WarningAmber color="warning" />
            Reset Configuration to Defaults
            {resetDiff.length > 0 && (
              <Chip
                label={`${resetDiff.length} change${resetDiff.length > 1 ? 's' : ''}`}
                color="warning"
                size="small"
                sx={{ ml: 1 }}
              />
            )}
          </DialogTitle>
          <DialogContent>
            <Alert severity="warning" sx={{ mb: 2 }}>
              This will reset ALL configuration parameters to their default values.
              Your current settings will be lost.
            </Alert>

            {/* Diff Preview Section (v5.4.1+) */}
            {resetDiffLoading ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <CircularProgress size={16} />
                <Typography variant="body2" color="text.secondary">
                  Loading changes preview...
                </Typography>
              </Box>
            ) : resetDiff.length > 0 ? (
              <Box sx={{ mb: 2 }}>
                <Button
                  size="small"
                  onClick={() => setResetDiffExpanded(!resetDiffExpanded)}
                  startIcon={resetDiffExpanded ? <ExpandLess /> : <ExpandMore />}
                  sx={{ mb: 1 }}
                >
                  {resetDiff.length} parameter{resetDiff.length > 1 ? 's' : ''} will be reverted
                </Button>
                <Collapse in={resetDiffExpanded}>
                  <Box sx={{
                    maxHeight: 250,
                    overflow: 'auto',
                    bgcolor: (theme) => theme.palette.mode === 'dark' ? 'grey.900' : 'grey.100',
                    borderRadius: 1,
                    border: 1,
                    borderColor: 'divider'
                  }}>
                    <List dense disablePadding>
                      {resetDiff.map((d, idx) => (
                        <ListItem
                          key={d.path || idx}
                          divider={idx < resetDiff.length - 1}
                          sx={{ py: 0.5, px: 1.5 }}
                        >
                          <MuiListItemText
                            primary={
                              <Typography variant="body2" fontFamily="monospace" fontWeight="medium">
                                {d.path || `${d.section}.${d.parameter}`}
                              </Typography>
                            }
                            secondary={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5, flexWrap: 'wrap' }}>
                                <Typography
                                  variant="caption"
                                  sx={{
                                    bgcolor: (theme) => alpha(theme.palette.error.main, 0.15),
                                    color: 'error.main',
                                    px: 0.75,
                                    py: 0.25,
                                    borderRadius: 0.5,
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {formatResetValue(d.new_value)}
                                </Typography>
                                <ArrowForward sx={{ fontSize: 12, color: 'text.disabled' }} />
                                <Typography
                                  variant="caption"
                                  sx={{
                                    bgcolor: (theme) => alpha(theme.palette.success.main, 0.15),
                                    color: 'success.main',
                                    px: 0.75,
                                    py: 0.25,
                                    borderRadius: 0.5,
                                    fontFamily: 'monospace'
                                  }}
                                >
                                  {formatResetValue(d.old_value)}
                                </Typography>
                              </Box>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                </Collapse>
              </Box>
            ) : (
              <Alert severity="info" sx={{ mb: 2 }}>
                No changes detected. Configuration already matches defaults.
              </Alert>
            )}

            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              A backup of your current configuration will be created automatically
              before resetting. You can restore it later from the History dialog.
            </Typography>
            <FormControlLabel
              control={
                <Checkbox
                  checked={resetConfirmed}
                  onChange={(e) => setResetConfirmed(e.target.checked)}
                  color="warning"
                />
              }
              label="I understand this will reset all configuration to defaults"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={handleResetDialogClose} disabled={resetting}>
              Cancel
            </Button>
            <Button
              onClick={handleResetToDefaults}
              variant="contained"
              color="warning"
              disabled={!resetConfirmed || resetting || resetDiff.length === 0}
              startIcon={resetting ? <CircularProgress size={16} /> : <RestartAlt />}
            >
              {resetting ? 'Resetting...' : `Reset ${resetDiff.length} Parameter${resetDiff.length !== 1 ? 's' : ''}`}
            </Button>
          </DialogActions>
        </Dialog>
      </>
    );
  }

  // Desktop/Tablet: 3-tier organized layout
  return (
    <>
      <Box sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 1,
        width: '100%'
      }}>
        {/* Tier 1: Primary Actions - Always visible, prominent */}
        <Box sx={{
          display: 'flex',
          gap: 1,
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          <Button
            variant="contained"
            size="small"
            startIcon={<CompareArrows />}
            onClick={onViewChanges}
            disabled={changesCount === 0}
          >
            <Badge badgeContent={changesCount} color="warning" max={99}>
              <Typography variant="button" sx={{ pr: changesCount > 0 ? 1.5 : 0 }}>
                View Changes
              </Typography>
            </Badge>
          </Button>

          {syncAvailableCount > 0 && (
            <Button
              variant="outlined"
              size="small"
              color="info"
              startIcon={<Sync />}
              onClick={onSyncDefaults}
            >
              <Badge badgeContent={syncAvailableCount} color="info" max={99}>
                <Typography variant="button" sx={{ pr: 1.5 }}>
                  Sync Defaults
                </Typography>
              </Badge>
            </Button>
          )}
        </Box>

        {/* Tier 2: Secondary Actions - Grouped by function */}
        <Box sx={{
          display: 'flex',
          gap: 0.5,
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          {/* File Group */}
          <Tooltip title="Export configuration to YAML file">
            <IconButton
              size="small"
              onClick={() => setExportOpen(true)}
              sx={{ color: 'text.secondary' }}
            >
              <FileDownload fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title="Import configuration from YAML file">
            <IconButton
              size="small"
              onClick={() => setImportOpen(true)}
              sx={{ color: 'text.secondary' }}
            >
              <FileUpload fontSize="small" />
            </IconButton>
          </Tooltip>

          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

          {/* History Group */}
          <Tooltip title="View backup history">
            <IconButton
              size="small"
              onClick={() => setHistoryOpen(true)}
              sx={{ color: 'text.secondary' }}
            >
              <History fontSize="small" />
            </IconButton>
          </Tooltip>

          <Tooltip title="View change audit log">
            <IconButton
              size="small"
              onClick={() => setAuditOpen(true)}
              sx={{ color: 'text.secondary' }}
            >
              <ReceiptLong fontSize="small" />
            </IconButton>
          </Tooltip>

          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

          {/* Utility */}
          <Tooltip title="Refresh configuration">
            <IconButton
              size="small"
              onClick={onRefresh}
              sx={{ color: 'text.secondary' }}
            >
              <Refresh fontSize="small" />
            </IconButton>
          </Tooltip>

          {/* Spacer */}
          <Box sx={{ flexGrow: 1 }} />

          {/* Tier 3: Destructive - Right-aligned, warning color */}
          <Tooltip title="Reset all parameters to default values">
            <Button
              variant="outlined"
              size="small"
              color="warning"
              startIcon={<RestartAlt />}
              onClick={() => setResetOpen(true)}
              sx={{ ml: 2 }}
            >
              Reset
            </Button>
          </Tooltip>
        </Box>
      </Box>

      {/* Dialogs */}
      {renderDialogs()}
    </>
  );
};

ImportExportToolbar.propTypes = {
  /** Number of parameters that differ from defaults */
  changesCount: PropTypes.number,
  /** Number of new defaults available for sync (v5.4.0+) */
  syncAvailableCount: PropTypes.number,
  /** Callback to refresh configuration */
  onRefresh: PropTypes.func,
  /** Callback to show messages (toast) */
  onMessage: PropTypes.func,
  /** Callback when config is imported */
  onConfigImported: PropTypes.func,
  /** Callback to view changes drawer (v5.4.0+) */
  onViewChanges: PropTypes.func,
  /** Callback to open sync defaults dialog (v5.4.0+) */
  onSyncDefaults: PropTypes.func,
};

export default ImportExportToolbar;
