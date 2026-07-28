import React, { useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Snackbar,
  Tooltip,
  Typography,
} from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { usePendingRestart } from '../context/PendingRestartContext';
import { useAuthSession } from '../context/AuthSessionContext';
import { restartAvailabilityMessage } from './config/PendingRestartBanner';

const RestartButton = ({ fullWidth = false, sx = {} }) => {
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [restartError, setRestartError] = useState('');
  const { hasScope } = useAuthSession();
  const {
    runtimeStatus,
    manualRestartActionAvailable,
    restarting,
    restartNow,
  } = usePendingRestart();
  const canAdministerSystem = hasScope('system:admin');
  const available = canAdministerSystem && manualRestartActionAvailable;
  const unavailableReason = canAdministerSystem
    ? restartAvailabilityMessage(runtimeStatus?.restart_action?.reason)
    : 'An administrator session is required.';

  const handleRestart = async () => {
    setConfirmationOpen(false);
    setRestartError('');
    try {
      const result = await restartNow({
        requirePending: false,
        reason: 'manual_operator_restart',
        metadata: { ui: 'dashboard_navigation' },
      });
      if (!result?.success) {
        setRestartError(result?.error || 'PixEagle restart was not accepted.');
      }
    } catch (error) {
      setRestartError(error?.message || 'PixEagle restart failed.');
    }
  };

  return (
    <>
      <Tooltip title={available ? 'Restart PixEagle' : unavailableReason}>
        <span>
          <Button
            variant="outlined"
            color="warning"
            startIcon={<RestartAltIcon />}
            onClick={() => setConfirmationOpen(true)}
            disabled={!available || restarting}
            fullWidth={fullWidth}
            sx={sx}
          >
            {restarting ? 'Restarting' : 'Restart'}
          </Button>
        </span>
      </Tooltip>
      <Dialog
        open={confirmationOpen}
        onClose={() => setConfirmationOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Restart PixEagle?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Active video and dashboard sessions will reconnect after the supervised process restarts.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmationOpen(false)}>Cancel</Button>
          <Button color="warning" variant="contained" onClick={handleRestart}>
            Restart
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar
        open={Boolean(restartError)}
        autoHideDuration={8000}
        onClose={() => setRestartError('')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="error" onClose={() => setRestartError('')}>
          {restartError}
        </Alert>
      </Snackbar>
    </>
  );
};

export default RestartButton;
