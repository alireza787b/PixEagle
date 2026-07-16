import React from 'react';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Tooltip,
  Typography,
} from '@mui/material';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
import { usePendingRestart } from '../../context/PendingRestartContext';

export const restartAvailabilityMessage = (reason) => ({
  following_or_offboard_active: 'Stop following and leave Offboard before restarting.',
  restart_already_pending: 'A PixEagle restart is already pending.',
  durable_audit_unavailable: 'Restart audit storage is unavailable.',
  state_barrier_unavailable: 'Runtime safety state is unavailable.',
  restart_policy_denied: 'This connection is outside the configured restart policy.',
  system_admin_principal_required: 'An administrator session is required.',
}[reason] || 'System restart is unavailable for this runtime.');

const PendingRestartBanner = () => {
  const {
    runtimeStatus,
    pendingRestart,
    restartActionAvailable,
    confirmationOpen,
    restarting,
    reconnectAttempt,
    error,
    statusLoading,
    statusUnavailable,
    refreshRuntimeStatus,
    requestRestartConfirmation,
    closeRestartConfirmation,
    restartNow,
    clearError,
  } = usePendingRestart();

  const restartDisabled = !restartActionAvailable || restarting;
  const unavailableMessage = restartAvailabilityMessage(
    runtimeStatus?.restart_action?.reason
  );
  const restartTooltip = restartActionAvailable
    ? 'Restart PixEagle to apply pending system configuration'
    : unavailableMessage;

  return (
    <>
      {(pendingRestart || restarting || statusUnavailable) && (
        <Alert
          severity={statusUnavailable ? 'error' : (restarting ? 'info' : 'warning')}
          variant="outlined"
          icon={<RestartAltIcon fontSize="small" />}
          sx={{
            mx: { xs: 1, sm: 2 },
            mt: 1,
            py: 0.25,
            alignItems: 'center',
            '& .MuiAlert-message': { width: '100%', minWidth: 0 },
          }}
        >
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: { xs: 'stretch', sm: 'center' },
              justifyContent: 'space-between',
              gap: 1,
              minWidth: 0,
            }}
          >
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle2" component="div">
                {statusUnavailable
                  ? 'Config restart status unavailable'
                  : (restarting ? 'Restart requested' : 'System restart required')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {statusUnavailable
                  ? error
                  : restarting
                  ? `Reconnecting to PixEagle${reconnectAttempt > 0 ? ` (attempt ${reconnectAttempt})` : ''}...`
                  : 'Saved system configuration is waiting for a PixEagle restart.'}
              </Typography>
              {pendingRestart && !restartActionAvailable && !restarting && (
                <Typography variant="caption" color="warning.dark">
                  {unavailableMessage}
                </Typography>
              )}
              {error && !statusUnavailable && (
                <Button
                  color="error"
                  size="small"
                  onClick={clearError}
                  sx={{ mt: 0.25, px: 0, justifyContent: 'flex-start' }}
                >
                  {error}
                </Button>
              )}
            </Box>
            {statusUnavailable ? (
              <Button
                color="error"
                size="small"
                variant="contained"
                startIcon={<RefreshIcon />}
                onClick={() => refreshRuntimeStatus().catch(() => {})}
                disabled={statusLoading}
                sx={{ whiteSpace: 'nowrap', alignSelf: { xs: 'flex-start', sm: 'center' } }}
              >
                {statusLoading ? 'Checking' : 'Retry Status'}
              </Button>
            ) : (
              <Tooltip title={restartTooltip}>
                <span>
                  <Button
                    color="warning"
                    size="small"
                    variant="contained"
                    startIcon={<RestartAltIcon />}
                    onClick={requestRestartConfirmation}
                    disabled={restartDisabled}
                    sx={{ whiteSpace: 'nowrap', alignSelf: { xs: 'flex-start', sm: 'center' } }}
                  >
                    {restarting ? 'Reconnecting' : 'Restart Now'}
                  </Button>
                </span>
              </Tooltip>
            )}
          </Box>
          {restarting && <LinearProgress sx={{ mt: 1 }} />}
        </Alert>
      )}

      <Dialog
        open={confirmationOpen}
        onClose={restarting ? undefined : closeRestartConfirmation}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RestartAltIcon color="warning" />
          Confirm PixEagle Restart
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            Restart PixEagle to apply pending system configuration?
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The backend will briefly disconnect. PixEagle refuses this action
            while following or Offboard is active.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeRestartConfirmation} disabled={restarting}>
            Later
          </Button>
          <Tooltip title={restartTooltip}>
            <span>
              <Button
                variant="contained"
                color="warning"
                onClick={restartNow}
                disabled={restartDisabled}
                startIcon={<RestartAltIcon />}
              >
                Restart Now
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default PendingRestartBanner;
