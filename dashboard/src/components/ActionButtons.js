// dashboard/src/components/ActionButtons.js
import React, { useState } from 'react';
import {
  Grid,
  Button,
  Typography,
  Tooltip,
  Box,
  Divider,
  Stack,
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
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import ReplayIcon from '@mui/icons-material/Replay';
import CancelOutlinedIcon from '@mui/icons-material/CancelOutlined';
import AutoAwesomeMosaicIcon from '@mui/icons-material/AutoAwesomeMosaic';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import FlightLandIcon from '@mui/icons-material/FlightLand';
import { endpoints } from '../services/apiEndpoints';
import { buildActionRequest } from '../services/actionRequests';
import { useAuthSession } from '../context/AuthSessionContext';

const ActionButtons = ({
  isTracking,
  selectionArmed: selectionArmedProp,
  trackingActive = false,
  trackerStatus,
  circuitBreakerActive,
  isFollowing,
  smartModeActive,
  smartModeStatusLoading = false,
  handleTrackingToggle,
  handleSelectionToggle,
  handleButtonClick,
  handleToggleSmartMode,
}) => {
  const [switchLoading, setSwitchLoading] = useState(false);
  const [followConfirmOpen, setFollowConfirmOpen] = useState(false);
  const { hasScope } = useAuthSession();
  const selectionArmed = selectionArmedProp ?? Boolean(isTracking);
  const toggleSelection = handleSelectionToggle || handleTrackingToggle;
  const canExecuteActions = hasScope('actions:execute');
  const smartModeKnown = typeof smartModeActive === 'boolean';
  const trackerModeControlsBlocked = smartModeStatusLoading || !smartModeKnown;
  const trackerUsabilityKnown = Boolean(trackerStatus && typeof trackerStatus === 'object');
  const commandInhibitKnown = typeof circuitBreakerActive === 'boolean';
  const followingStateKnown = typeof isFollowing === 'boolean';
  const canStartFollowing = canExecuteActions
    && isFollowing === false
    && (!trackerUsabilityKnown || trackerStatus.usableForFollowing)
    && commandInhibitKnown
    && circuitBreakerActive === false;
  let followDisabledReason = null;
  if (!followingStateKnown) {
    followDisabledReason = 'Following state is unavailable; Start is blocked and Stop remains available.';
  } else if (trackerUsabilityKnown && !trackerStatus.usableForFollowing) {
    followDisabledReason = trackerStatus.followDisabledReason
      || trackerStatus.detail
      || 'Follower requires fresh, usable tracker output.';
  } else if (circuitBreakerActive === true) {
    followDisabledReason = 'PX4 command dispatch is inhibited. Disable the circuit breaker before Following.';
  } else if (!commandInhibitKnown) {
    followDisabledReason = 'Circuit-breaker state is unavailable; Following is blocked.';
  } else if (!canExecuteActions) {
    followDisabledReason = 'Current session cannot execute Offboard actions.';
  }

  const handleSmartModeSwitch = async (event, newMode) => {
    if (newMode === null || trackerModeControlsBlocked) return;
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
    <Box>
      <Stack spacing={1.25}>
        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', fontWeight: 700, mb: 0.75, textTransform: 'uppercase' }}
          >
            Tracker mode
          </Typography>
          <ToggleButtonGroup
            value={smartModeKnown ? (smartModeActive ? 'smart' : 'classic') : null}
            exclusive
            onChange={handleSmartModeSwitch}
            disabled={switchLoading || trackerModeControlsBlocked || !canExecuteActions}
            fullWidth
            size="small"
            sx={{ minHeight: 34 }}
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
        </Box>

        <Divider />

        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', fontWeight: 700, mb: 0.75, textTransform: 'uppercase' }}
          >
            Tracking
          </Typography>
          <Grid container spacing={0.75}>
            <Grid item xs={6}>
              <Tooltip title={
                !smartModeKnown
                  ? 'Tracker mode is unavailable; target selection is blocked.'
                  : smartModeActive
                    ? 'Target selection is automatic in Smart Mode'
                    : 'Arm or cancel target selection on the video'
              }>
                <span>
                  <Button
                    variant="contained"
                    color={selectionArmed ? 'secondary' : 'primary'}
                    onClick={toggleSelection}
                    fullWidth
                    size="small"
                    startIcon={selectionArmed ? <StopCircleIcon /> : <PlayCircleOutlineIcon />}
                    disabled={trackerModeControlsBlocked || smartModeActive || !canExecuteActions}
                    sx={{ minHeight: 34, fontSize: 11 }}
                  >
                    {selectionArmed
                      ? 'Cancel Selection'
                      : trackingActive ? 'Select New Target' : 'Select Target'}
                  </Button>
                </span>
              </Tooltip>
            </Grid>
            <Grid item xs={6}>
              <Tooltip title="Re-detect the target with the classic tracker">
                <span>
                  <Button
                    variant="outlined"
                    color="primary"
                    onClick={() => handleButtonClick(
                      endpoints.trackingRedetectAction,
                      false,
                      buildActionRequest('redetect_tracking')
                    )}
                    fullWidth
                    size="small"
                    startIcon={<ReplayIcon />}
                    disabled={trackerModeControlsBlocked || smartModeActive || !canExecuteActions}
                    sx={{ minHeight: 34, fontSize: 11 }}
                  >
                    Re-Detect
                  </Button>
                </span>
              </Tooltip>
            </Grid>
            <Grid item xs={6}>
              <Tooltip title="Abort tracking activity and clear the target">
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
                    startIcon={<CancelOutlinedIcon />}
                    disabled={!canExecuteActions}
                    sx={{ minHeight: 34, fontSize: 11 }}
                  >
                    Cancel Tracker
                  </Button>
                </span>
              </Tooltip>
            </Grid>
            <Grid item xs={6}>
              <Tooltip title="Toggle the segmentation overlay">
                <span>
                  <Button
                    variant="outlined"
                    color="secondary"
                    onClick={() => handleButtonClick(
                      endpoints.segmentationToggleAction,
                      false,
                      buildActionRequest('toggle_segmentation')
                    )}
                    fullWidth
                    size="small"
                    startIcon={<AutoAwesomeMosaicIcon />}
                    disabled={!canExecuteActions}
                    sx={{ minHeight: 34, fontSize: 11 }}
                  >
                    Toggle Segmentation
                  </Button>
                </span>
              </Tooltip>
            </Grid>
          </Grid>
        </Box>

        <Divider />

        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', fontWeight: 700, mb: 0.75, textTransform: 'uppercase' }}
          >
            Offboard control
          </Typography>

          {isFollowing === false ? (
            <Tooltip title={followDisabledReason || "Engage offboard mode and start autonomous following"}>
              <span>
                <Button
                  variant="contained"
                  color="success"
                  onClick={handleStartFollowClick}
                  fullWidth
                  size="small"
                  startIcon={<FlightTakeoffIcon />}
                  disabled={!canStartFollowing}
                  sx={{ minHeight: 36 }}
                >
                  Start Following
                </Button>
              </span>
            </Tooltip>
          ) : (
            <Tooltip title={followingStateKnown
              ? 'Disengage offboard mode and stop following immediately'
              : 'Following state is unavailable; request a defensive stop'}>
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
                  startIcon={<FlightLandIcon />}
                  disabled={!canExecuteActions}
                  sx={{ minHeight: 36 }}
                >
                  Stop Following
                </Button>
              </span>
            </Tooltip>
          )}
        </Box>
      </Stack>

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
    </Box>
  );
};

export default ActionButtons;
