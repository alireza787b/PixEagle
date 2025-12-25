// dashboard/src/components/config/BackupHistoryDialog.js
import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Box, Typography, CircularProgress, Alert,
  List, ListItem, ListItemText, ListItemSecondaryAction,
  IconButton, Tooltip, Chip, Divider, Paper
} from '@mui/material';
import {
  History, Restore, Delete, Refresh, Schedule,
  Storage, CheckCircle, Warning
} from '@mui/icons-material';

import { useConfigHistory } from '../../hooks/useConfig';

/**
 * BackupHistoryDialog - Dialog for viewing and restoring config backups
 *
 * Features:
 * - List all available backups
 * - Show backup timestamp and size
 * - Restore from any backup
 * - Auto-refresh on open
 */
const BackupHistoryDialog = ({ open, onClose }) => {
  const { backups, loading, error, restoreBackup, refetch } = useConfigHistory();
  const [restoring, setRestoring] = useState(null);
  const [restoreError, setRestoreError] = useState(null);
  const [restoreSuccess, setRestoreSuccess] = useState(false);

  // Refresh on open
  useEffect(() => {
    if (open) {
      refetch();
      setRestoreError(null);
      setRestoreSuccess(false);
    }
  }, [open, refetch]);

  const handleRestore = async (backupId) => {
    setRestoring(backupId);
    setRestoreError(null);

    try {
      const success = await restoreBackup(backupId);
      if (success) {
        setRestoreSuccess(true);
        setTimeout(() => {
          onClose(true);
        }, 1500);
      } else {
        setRestoreError('Failed to restore backup');
      }
    } catch (err) {
      setRestoreError(err.message || 'Failed to restore backup');
    } finally {
      setRestoring(null);
    }
  };

  const handleClose = () => {
    if (!restoring) {
      onClose(restoreSuccess);
    }
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getRelativeTime = (timestamp) => {
    const now = Date.now() / 1000;
    const diff = now - timestamp;

    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} hours ago`;
    if (diff < 604800) return `${Math.floor(diff / 86400)} days ago`;
    return formatTimestamp(timestamp);
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <History />
        Backup History
        <Box sx={{ flexGrow: 1 }} />
        <Tooltip title="Refresh">
          <IconButton onClick={refetch} disabled={loading} size="small">
            <Refresh />
          </IconButton>
        </Tooltip>
      </DialogTitle>

      <DialogContent>
        {/* Success message */}
        {restoreSuccess && (
          <Alert
            severity="success"
            icon={<CheckCircle />}
            sx={{ mb: 2 }}
          >
            Configuration restored successfully! Refreshing...
          </Alert>
        )}

        {/* Error display */}
        {(error || restoreError) && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error || restoreError}
          </Alert>
        )}

        {/* Loading state */}
        {loading && !restoring && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress />
            <Typography sx={{ mt: 2 }}>Loading backups...</Typography>
          </Box>
        )}

        {/* Empty state */}
        {!loading && backups.length === 0 && (
          <Paper sx={{ p: 4, textAlign: 'center' }} variant="outlined">
            <Storage sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No Backups Available
            </Typography>
            <Typography variant="body2" color="text.disabled">
              Backups are created automatically when you save configuration changes.
            </Typography>
          </Paper>
        )}

        {/* Backup list */}
        {!loading && backups.length > 0 && (
          <List disablePadding>
            {backups.map((backup, index) => (
              <React.Fragment key={backup.id}>
                {index > 0 && <Divider />}
                <ListItem
                  sx={{
                    py: 2,
                    opacity: restoring && restoring !== backup.id ? 0.5 : 1
                  }}
                >
                  <ListItemText
                    primary={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Schedule fontSize="small" color="action" />
                        <Typography variant="body1">
                          {formatTimestamp(backup.timestamp)}
                        </Typography>
                        {index === 0 && (
                          <Chip
                            label="Latest"
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        )}
                      </Box>
                    }
                    secondary={
                      <Box sx={{ display: 'flex', gap: 2, mt: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">
                          {getRelativeTime(backup.timestamp)}
                        </Typography>
                        <Typography variant="caption" color="text.disabled">
                          {formatSize(backup.size)}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.disabled"
                          sx={{ fontFamily: 'monospace' }}
                        >
                          {backup.filename}
                        </Typography>
                      </Box>
                    }
                  />
                  <ListItemSecondaryAction>
                    <Tooltip title="Restore this backup">
                      <IconButton
                        edge="end"
                        onClick={() => handleRestore(backup.id)}
                        disabled={restoring !== null}
                        color="primary"
                      >
                        {restoring === backup.id ? (
                          <CircularProgress size={24} />
                        ) : (
                          <Restore />
                        )}
                      </IconButton>
                    </Tooltip>
                  </ListItemSecondaryAction>
                </ListItem>
              </React.Fragment>
            ))}
          </List>
        )}

        {/* Info footer */}
        {backups.length > 0 && (
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">
              Restoring a backup will replace your current configuration.
              A new backup will be created before restore.
            </Typography>
          </Alert>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={restoring !== null}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default BackupHistoryDialog;
