// dashboard/src/components/config/ImportExportToolbar.js
import React, { useState } from 'react';
import {
  Box, Button, Tooltip, Divider, Chip, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Typography, FormControlLabel, Checkbox, Alert,
  CircularProgress
} from '@mui/material';
import {
  FileUpload, FileDownload, History, Refresh,
  CompareArrows, WarningAmber, ReceiptLong, RestartAlt
} from '@mui/icons-material';

import { useResponsive } from '../../hooks/useResponsive';
import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';
import BackupHistoryDialog from './BackupHistoryDialog';
import AuditLogDialog from './AuditLogDialog';
import { endpoints } from '../../services/apiEndpoints';

/**
 * ImportExportToolbar - Toolbar for config import/export operations
 *
 * Features:
 * - Export current config (full or changes-only)
 * - Import config with diff preview
 * - View and restore backup history
 * - Show count of changes from default
 */
const ImportExportToolbar = ({
  changesCount = 0,
  onRefresh,
  onMessage,
  onConfigImported
}) => {
  const { isMobile, iconButtonSize } = useResponsive();
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetConfirmed, setResetConfirmed] = useState(false);
  const [resetting, setResetting] = useState(false);

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

  return (
    <>
      {isMobile ? (
        // Mobile: Icon-only buttons in compact grid
        <Box sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(44px, 1fr))',
          gap: 0.5,
          alignItems: 'center',
          justifyItems: 'center',
          width: '100%'
        }}>
          {/* Changes indicator */}
          {changesCount > 0 && (
            <Chip
              icon={<CompareArrows />}
              label={changesCount}
              size="small"
              color="warning"
              variant="outlined"
              sx={{ gridColumn: '1 / -1', justifySelf: 'stretch' }}
            />
          )}

          {/* Export button */}
          <Tooltip title="Export">
            <IconButton
              size={iconButtonSize}
              onClick={() => setExportOpen(true)}
              sx={{ border: 1, borderColor: 'divider' }}
            >
              <FileDownload />
            </IconButton>
          </Tooltip>

          {/* Import button */}
          <Tooltip title="Import">
            <IconButton
              size={iconButtonSize}
              onClick={() => setImportOpen(true)}
              sx={{ border: 1, borderColor: 'divider' }}
            >
              <FileUpload />
            </IconButton>
          </Tooltip>

          {/* History button */}
          <Tooltip title="History">
            <IconButton
              size={iconButtonSize}
              onClick={() => setHistoryOpen(true)}
              sx={{ border: 1, borderColor: 'divider' }}
            >
              <History />
            </IconButton>
          </Tooltip>

          {/* Audit Log button */}
          <Tooltip title="Audit Log">
            <IconButton
              size={iconButtonSize}
              onClick={() => setAuditOpen(true)}
              sx={{ border: 1, borderColor: 'divider' }}
            >
              <ReceiptLong />
            </IconButton>
          </Tooltip>

          {/* Reset to Defaults button */}
          <Tooltip title="Reset">
            <IconButton
              size={iconButtonSize}
              color="warning"
              onClick={() => setResetOpen(true)}
              sx={{ border: 1, borderColor: 'warning.main' }}
            >
              <RestartAlt />
            </IconButton>
          </Tooltip>

          {/* Refresh button */}
          <Tooltip title="Refresh">
            <IconButton
              size={iconButtonSize}
              onClick={onRefresh}
              sx={{ border: 1, borderColor: 'divider' }}
            >
              <Refresh />
            </IconButton>
          </Tooltip>
        </Box>
      ) : (
        // Desktop: Full buttons with labels
        <Box sx={{
          display: 'flex',
          gap: 1,
          alignItems: 'center',
          flexWrap: 'wrap'
        }}>
          {/* Changes indicator */}
          {changesCount > 0 && (
            <Tooltip title={`${changesCount} parameters differ from defaults`}>
              <Chip
                icon={<CompareArrows />}
                label={`${changesCount} changes`}
                size="small"
                color="warning"
                variant="outlined"
              />
            </Tooltip>
          )}

          <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />

          {/* Export button */}
          <Tooltip title="Export configuration to YAML file">
            <Button
              variant="outlined"
              size="small"
              startIcon={<FileDownload />}
              onClick={() => setExportOpen(true)}
            >
              Export
            </Button>
          </Tooltip>

          {/* Import button */}
          <Tooltip title="Import configuration from YAML file">
            <Button
              variant="outlined"
              size="small"
              startIcon={<FileUpload />}
              onClick={() => setImportOpen(true)}
            >
              Import
            </Button>
          </Tooltip>

          {/* History button */}
          <Tooltip title="View backup history">
            <Button
              variant="outlined"
              size="small"
              startIcon={<History />}
              onClick={() => setHistoryOpen(true)}
            >
              History
            </Button>
          </Tooltip>

          {/* Audit Log button */}
          <Tooltip title="View change audit log">
            <Button
              variant="outlined"
              size="small"
              startIcon={<ReceiptLong />}
              onClick={() => setAuditOpen(true)}
            >
              Audit Log
            </Button>
          </Tooltip>

          {/* Reset to Defaults button */}
          <Tooltip title="Reset all parameters to default values">
            <Button
              variant="outlined"
              size="small"
              color="warning"
              startIcon={<RestartAlt />}
              onClick={() => setResetOpen(true)}
            >
              Reset to Defaults
            </Button>
          </Tooltip>

          <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />

          {/* Refresh button */}
          <Tooltip title="Refresh configuration">
            <Button
              variant="text"
              size="small"
              startIcon={<Refresh />}
              onClick={onRefresh}
            >
              Refresh
            </Button>
          </Tooltip>
        </Box>
      )}

      {/* Dialogs */}
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

      {/* Reset to Defaults Confirmation Dialog */}
      <Dialog
        open={resetOpen}
        onClose={handleResetDialogClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <WarningAmber color="warning" />
          Reset Configuration to Defaults
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This will reset ALL configuration parameters to their default values.
            Your current settings will be lost.
          </Alert>
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
            disabled={!resetConfirmed || resetting}
            startIcon={resetting ? <CircularProgress size={16} /> : <RestartAlt />}
          >
            {resetting ? 'Resetting...' : 'Reset to Defaults'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default ImportExportToolbar;
