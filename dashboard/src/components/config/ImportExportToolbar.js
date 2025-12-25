// dashboard/src/components/config/ImportExportToolbar.js
import React, { useState } from 'react';
import {
  Box, Button, Tooltip, Divider, Chip
} from '@mui/material';
import {
  FileUpload, FileDownload, History, Refresh,
  CompareArrows, WarningAmber, ReceiptLong
} from '@mui/icons-material';

import ExportDialog from './ExportDialog';
import ImportDialog from './ImportDialog';
import BackupHistoryDialog from './BackupHistoryDialog';
import AuditLogDialog from './AuditLogDialog';

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
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);

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

  return (
    <>
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
    </>
  );
};

export default ImportExportToolbar;
