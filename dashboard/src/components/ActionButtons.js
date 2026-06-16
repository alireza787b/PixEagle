// dashboard/src/components/ActionButtons.js
import React, { useState } from 'react';
import {
  Grid,
  Button,
  Typography,
  Tooltip,
  Container,
  ToggleButtonGroup,
  ToggleButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import GpsFixedIcon from '@mui/icons-material/GpsFixed';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';
import { useAuthSession } from '../context/AuthSessionContext';

const ActionButtons = ({
  isTracking,
  trackerStatus,
  isFollowing,
  smartModeActive,
  handleTrackingToggle,
  handleButtonClick,
  handleToggleSmartMode,
}) => {
  const [switchLoading, setSwitchLoading] = useState(false);
  const [followConfirmOpen, setFollowConfirmOpen] = useState(false);
  const { hasScope } = useAuthSession();
  const canWriteControl = hasScope('control:write');
  const canExecuteActions = hasScope('actions:execute');
  const trackerUsabilityKnown = Boolean(trackerStatus && typeof trackerStatus === 'object');
  const canStartFollowing = canExecuteActions && (!trackerUsabilityKnown || trackerStatus.usableForFollowing);
  let followDisabledReason = null;
  if (trackerUsabilityKnown && !trackerStatus.usableForFollowing) {
    followDisabledReason = trackerStatus.detail || 'Follower requires fresh, usable tracker output.';
  } else if (!canExecuteActions) {
    followDisabledReason = 'Current session cannot execute Offboard actions.';
  }

  const handleSmartModeSwitch = async (event, newMode) => {
    if (newMode === null) return; // Prevent deselection
    const wantSmart = newMode === 'smart';
    if (wantSmart === smartModeActive) return; // Already in this mode
    setSwitchLoading(true);
    await handleToggleSmartMode();
    setSwitchLoading(false);
  };

  const handleStartFollowClick = () => {
    if (!canStartFollowing) {
      return;
    }
    setFollowConfirmOpen(true);
  };

  const handleFollowConfirm = () => {
    if (!canStartFollowing) {
      setFollowConfirmOpen(false);
      return;
    }
    setFollowConfirmOpen(false);
    handleButtonClick(
      endpoints.offboardStartAction,
      false,
      buildActionRequest('start_following')
    );
  };

  const handleFollowCancel = () => {
    setFollowConfirmOpen(false);
  };

  return (
    <Container disableGutters>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {/* Tracker Mode Toggle */}
        <Grid item xs={12}>
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            Tracker Mode
          </Typography>
          <ToggleButtonGroup
            value={smartModeActive ? 'smart' : 'classic'}
            exclusive
            onChange={handleSmartModeSwitch}
            disabled={switchLoading || !canWriteControl}
            fullWidth
            size="small"
            sx={{ mb: 0.5 }}
          >
            <ToggleButton value="classic" sx={{ textTransform: 'none', fontWeight: 600 }}>
              <GpsFixedIcon sx={{ fontSize: 16, mr: 0.5 }} />
              Classic
            </ToggleButton>
            <ToggleButton value="smart" sx={{ textTransform: 'none', fontWeight: 600 }}>
              <AutoFixHighIcon sx={{ fontSize: 16, mr: 0.5 }} />
              Smart (AI)
            </ToggleButton>
          </ToggleButtonGroup>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center' }}>
            {smartModeActive ? 'Click video to detect and track' : 'Draw box on video to track'}
          </Typography>
        </Grid>

        {/* Tracking Controls */}
        <Grid item xs={12}>
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            Tracking Controls
          </Typography>
          <Tooltip title={smartModeActive ? "Tracking is automatic in Smart Mode" : "Start or stop classic tracking"}>
            <span>
              <Button
                variant="contained"
                color={isTracking ? "secondary" : "primary"}
                onClick={handleTrackingToggle}
                fullWidth
                size="small"
                disabled={smartModeActive || !canWriteControl}
              >
                {isTracking ? "Stop Tracking" : "Start Tracking"}
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="Re-detect object (Classic tracker only)">
            <span>
              <Button
                variant="outlined"
                color="primary"
                onClick={() => handleButtonClick(endpoints.redetect)}
                fullWidth
                size="small"
                sx={{ mt: 0.5 }}
                disabled={smartModeActive || !canWriteControl}
              >
                Re-Detect
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="Cancel all tracking activities and reset">
            <span>
              <Button
                variant="outlined"
                color="warning"
                onClick={() => handleButtonClick(
                  endpoints.operatorAbortAction,
                  true,
                  buildActionRequest('cancel_activities')
                )}
                fullWidth
                size="small"
                sx={{ mt: 0.5 }}
                disabled={!canExecuteActions}
              >
                Cancel Tracker
              </Button>
            </span>
          </Tooltip>
        </Grid>

        {/* Segmentation */}
        <Grid item xs={12}>
          <Tooltip title="Toggle AI segmentation overlay">
            <span>
              <Button
                variant="outlined"
                color="secondary"
                onClick={() => handleButtonClick(endpoints.toggleSegmentation)}
                fullWidth
                size="small"
                disabled={!canWriteControl}
              >
                Toggle Segmentation
              </Button>
            </span>
          </Tooltip>
        </Grid>

        {/* Drone Control - Follow */}
        <Grid item xs={12}>
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            Drone Control
          </Typography>

          {!isFollowing ? (
            <Tooltip title={followDisabledReason || "Engage offboard mode and start autonomous following"}>
              <span>
                <Button
                  variant="contained"
                  color="success"
                  onClick={handleStartFollowClick}
                  fullWidth
                  size="small"
                  disabled={!canStartFollowing}
                >
                  Start Following
                </Button>
              </span>
            </Tooltip>
          ) : (
            <Tooltip title="Disengage offboard mode and stop following immediately">
              <span>
                <Button
                  variant="contained"
                  color="error"
                  onClick={() => handleButtonClick(
                    endpoints.offboardStopAction,
                    false,
                    buildActionRequest('stop_following')
                  )}
                  fullWidth
                  size="small"
                  disabled={!canExecuteActions}
                >
                  Stop Following
                </Button>
              </span>
            </Tooltip>
          )}
        </Grid>
      </Grid>

      {/* Follow Engagement Confirmation Dialog */}
      <Dialog
        open={followConfirmOpen}
        onClose={handleFollowCancel}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <WarningAmberIcon color="warning" />
          Engage Autonomous Following?
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            This will activate offboard mode and begin autonomous drone movement.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Ensure the area is clear and the drone is in a safe state before engaging.
            Tracker output must be fresh and marked usable for follower control.
          </Typography>
          {trackerUsabilityKnown && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Tracker state: {trackerStatus.chipLabel}; {trackerStatus.followLabel || 'follower usability unknown'}.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleFollowCancel}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleFollowConfirm}
            disabled={!canStartFollowing}
          >
            Engage
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ActionButtons;
