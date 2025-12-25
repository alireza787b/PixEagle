// dashboard/src/components/config/RestartPrompt.js
import React, { useState, useEffect, useCallback } from 'react';
import {
  Alert, AlertTitle, Box, Button, Chip, IconButton, LinearProgress,
  Dialog, DialogTitle, DialogContent, DialogActions, Typography
} from '@mui/material';
import { Close, RestartAlt, Schedule, Warning } from '@mui/icons-material';
import axios from 'axios';

import { endpoints } from '../../services/apiEndpoints';

/**
 * RestartPrompt - Shows a banner when parameters requiring restart have been changed
 *
 * Features:
 * - Display which parameters need restart
 * - Restart Later button (dismiss)
 * - Restart Now button (triggers backend restart)
 * - Progress indicator during restart
 * - Auto-recovery after restart completes
 */
const RestartPrompt = ({ params = [], onDismiss, onRestarted }) => {
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pollCount, setPollCount] = useState(0);

  // Poll for backend status after restart
  const pollStatus = useCallback(async () => {
    try {
      const response = await axios.get(endpoints.systemStatus, {
        timeout: 2000
      });
      if (response.data.success) {
        // Backend is back!
        setRestarting(false);
        setPollCount(0);
        onRestarted?.();
        return true;
      }
    } catch (error) {
      // Still restarting...
      return false;
    }
    return false;
  }, [onRestarted]);

  useEffect(() => {
    let interval;
    if (restarting && pollCount > 0) {
      interval = setInterval(async () => {
        const isBack = await pollStatus();
        if (!isBack && pollCount < 30) {
          setPollCount(prev => prev + 1);
        } else if (pollCount >= 30) {
          // Timeout after ~30 seconds
          setRestartError('Backend did not come back within expected time. Please check manually.');
          setRestarting(false);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [restarting, pollCount, pollStatus]);

  if (params.length === 0 && !restarting) {
    return null;
  }

  // Group by section
  const groupedParams = params.reduce((acc, p) => {
    if (!acc[p.section]) {
      acc[p.section] = [];
    }
    acc[p.section].push(p.param);
    return acc;
  }, {});

  const handleRestartClick = () => {
    setConfirmOpen(true);
  };

  const handleConfirmRestart = async () => {
    setConfirmOpen(false);
    setRestarting(true);
    setRestartError(null);
    setPollCount(0);

    try {
      const response = await axios.post(endpoints.systemRestart, {
        reason: `Configuration changes requiring restart: ${params.map(p => `${p.section}.${p.param}`).join(', ')}`
      });

      if (response.data.success) {
        // Start polling for backend to come back
        // Wait a bit for the restart to initiate
        setTimeout(() => {
          setPollCount(1);
        }, 3000);
      } else {
        throw new Error(response.data.message || 'Restart failed');
      }
    } catch (error) {
      setRestartError(error.message || 'Failed to initiate restart');
      setRestarting(false);
    }
  };

  const handleCancelConfirm = () => {
    setConfirmOpen(false);
  };

  // Show restarting state
  if (restarting) {
    return (
      <Alert
        severity="info"
        icon={<RestartAlt />}
        sx={{ mb: 2 }}
      >
        <AlertTitle>Restarting Backend...</AlertTitle>
        <Box>
          <Typography variant="body2" sx={{ mb: 1 }}>
            The backend is restarting to apply configuration changes.
            This page will refresh automatically when the backend is ready.
          </Typography>
          <LinearProgress sx={{ mt: 1 }} />
          {pollCount > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Waiting for backend... ({pollCount}s)
            </Typography>
          )}
        </Box>
      </Alert>
    );
  }

  // Show error state
  if (restartError) {
    return (
      <Alert
        severity="error"
        icon={<Warning />}
        sx={{ mb: 2 }}
        action={
          <Button color="inherit" size="small" onClick={() => setRestartError(null)}>
            Dismiss
          </Button>
        }
      >
        <AlertTitle>Restart Failed</AlertTitle>
        {restartError}
      </Alert>
    );
  }

  return (
    <>
      <Alert
        severity="warning"
        icon={<RestartAlt />}
        sx={{ mb: 2 }}
        action={
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <Button
              color="warning"
              size="small"
              variant="contained"
              startIcon={<RestartAlt />}
              onClick={handleRestartClick}
            >
              Restart Now
            </Button>
            <Button
              color="inherit"
              size="small"
              startIcon={<Schedule />}
              onClick={onDismiss}
            >
              Later
            </Button>
            <IconButton
              size="small"
              color="inherit"
              onClick={onDismiss}
            >
              <Close fontSize="small" />
            </IconButton>
          </Box>
        }
      >
        <AlertTitle>Restart Required</AlertTitle>
        <Box>
          The following changes require an application restart to take effect:
          <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {Object.entries(groupedParams).map(([section, paramList]) => (
              paramList.map(param => (
                <Chip
                  key={`${section}.${param}`}
                  label={`${section}.${param}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}
                />
              ))
            ))}
          </Box>
        </Box>
      </Alert>

      {/* Confirmation Dialog */}
      <Dialog
        open={confirmOpen}
        onClose={handleCancelConfirm}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RestartAlt color="warning" />
          Confirm Restart
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            Are you sure you want to restart the backend?
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The application will briefly go offline while the backend restarts.
            Active tracking or following operations will be interrupted.
          </Typography>
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              Changes to be applied:
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {params.slice(0, 5).map(p => (
                <Chip
                  key={`${p.section}.${p.param}`}
                  label={`${p.section}.${p.param}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}
                />
              ))}
              {params.length > 5 && (
                <Chip
                  label={`+${params.length - 5} more`}
                  size="small"
                  color="warning"
                />
              )}
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelConfirm}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleConfirmRestart}
            startIcon={<RestartAlt />}
          >
            Restart Now
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default RestartPrompt;
