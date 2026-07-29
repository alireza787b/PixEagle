// dashboard/src/components/ActionButtons.js
import React, { useRef, useState } from 'react';
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
  executionMode = 'PX4',
  commandPreviewReady = false,
  commandPreviewReason = null,
  smartModeActive,
  smartModeStatusLoading = false,
  segmentationActive,
  segmentationCapability = null,
  requireFollowStartConfirmation = true,
  handleTrackingToggle,
  handleSelectionToggle,
  handleButtonClick,
  handleToggleSmartMode,
}) => {
  const [switchLoading, setSwitchLoading] = useState(false);
  const [followConfirmOpen, setFollowConfirmOpen] = useState(false);
  const [followActionPending, setFollowActionPending] = useState(false);
  const followActionPendingRef = useRef(false);
  const { hasScope } = useAuthSession();
  const selectionArmed = selectionArmedProp ?? Boolean(isTracking);
  const toggleSelection = handleSelectionToggle || handleTrackingToggle;
  const canExecuteActions = hasScope('actions:execute');
  const smartModeKnown = typeof smartModeActive === 'boolean';
  const trackerModeControlsBlocked = smartModeStatusLoading || !smartModeKnown;
  const segmentationAvailable = segmentationCapability?.available === true;
  const segmentationDisabledReason = smartModeActive
    ? 'Selection assist is part of Classic mode; Smart mode uses its active detection model.'
    : segmentationCapability === null
      ? 'Selection assist status is unavailable.'
    : !segmentationAvailable
      ? `Selection assist unavailable: ${segmentationCapability?.unavailable_reason || 'model not ready'}`
      : 'Toggle AI-assisted target selection for Classic mode.';
  const segmentationActionDisabled = (
    trackerModeControlsBlocked
    || smartModeActive
    || !segmentationAvailable
    || !canExecuteActions
  );
  const trackerUsabilityKnown = Boolean(trackerStatus && typeof trackerStatus === 'object');
  const commandInhibitKnown = typeof circuitBreakerActive === 'boolean';
  const followingStateKnown = typeof isFollowing === 'boolean';
  const commandPreviewMode = String(executionMode || 'PX4').toUpperCase() === 'COMMAND_PREVIEW';
  const trackerReady = commandPreviewMode
    ? commandPreviewReady === true
    : (!trackerUsabilityKnown || trackerStatus.usableForFollowing);
  const canStartFollowing = canExecuteActions
    && isFollowing === false
    && trackerReady
    && commandInhibitKnown
    && (commandPreviewMode
      ? circuitBreakerActive === true && commandPreviewReady === true
      : circuitBreakerActive === false);
  let followDisabledReason = null;
  if (!followingStateKnown) {
    followDisabledReason = 'Following state is unavailable; Start is blocked and Stop remains available.';
  } else if (commandPreviewMode && commandPreviewReady !== true) {
    followDisabledReason = commandPreviewReason
      || 'Follower test requires a fresh video-file frame and an active tracker target.';
  } else if (!commandPreviewMode && trackerUsabilityKnown && !trackerStatus.usableForFollowing) {
    followDisabledReason = trackerStatus.followDisabledReason
      || trackerStatus.detail
      || 'Follower requires fresh, usable tracker output.';
  } else if (commandPreviewMode && circuitBreakerActive !== true) {
    followDisabledReason = 'Follower test requires the circuit breaker to remain active.';
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
    try {
      await handleToggleSmartMode();
    } catch {
      // The parent action owns operator-facing error reporting.
    } finally {
      setSwitchLoading(false);
    }
  };

  const submitFollowStart = async () => {
    if (!canStartFollowing || followActionPendingRef.current) {
      return;
    }
    followActionPendingRef.current = true;
    setFollowActionPending(true);
    try {
      await handleButtonClick(
        endpoints.offboardStartAction,
        false,
        buildActionRequest(commandPreviewMode ? 'start_command_preview' : 'start_following')
      );
    } finally {
      followActionPendingRef.current = false;
      setFollowActionPending(false);
    }
  };

  const handleStartFollowClick = () => {
    if (!canStartFollowing || followActionPendingRef.current) {
      return;
    }
    if (requireFollowStartConfirmation) {
      setFollowConfirmOpen(true);
      return;
    }
    void submitFollowStart();
  };

  const handleFollowConfirm = () => {
    if (!canStartFollowing || followActionPendingRef.current) {
      setFollowConfirmOpen(false);
      return;
    }
    setFollowConfirmOpen(false);
    void submitFollowStart();
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
                    sx={{ height: 38, fontSize: 11, whiteSpace: 'nowrap' }}
                  >
                    {selectionArmed
                      ? 'Cancel Select'
                      : trackingActive ? 'Retarget' : 'Select Target'}
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
                    sx={{ height: 38, fontSize: 11, whiteSpace: 'nowrap' }}
                  >
                    Re-Detect
                  </Button>
                </span>
              </Tooltip>
            </Grid>
            <Grid item xs={6}>
              <Tooltip title="Stop following, abort tracking, and clear the active target">
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
                    sx={{ height: 38, fontSize: 11, whiteSpace: 'nowrap' }}
                  >
                    Abort All
                  </Button>
                </span>
              </Tooltip>
            </Grid>
            <Grid item xs={6}>
              <Tooltip title={segmentationDisabledReason}>
                <span>
                  <Button
                    variant={segmentationActive === true ? 'contained' : 'outlined'}
                    color="secondary"
                    onClick={() => handleButtonClick(
                      endpoints.segmentationToggleAction,
                      false,
                      buildActionRequest('toggle_segmentation')
                    )}
                    fullWidth
                    size="small"
                    startIcon={<AutoAwesomeMosaicIcon />}
                    disabled={segmentationActionDisabled}
                    sx={{ height: 38, fontSize: 11, whiteSpace: 'nowrap' }}
                  >
                    Selection Assist
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
            {commandPreviewMode ? 'Follower test' : 'Offboard control'}
          </Typography>

          {isFollowing === false ? (
            <Tooltip title={followDisabledReason || (commandPreviewMode
              ? 'Run follower math and record local command intents'
              : 'Engage offboard mode and start autonomous following')}>
              <span>
                <Button
                  variant="contained"
                  color="success"
                  onClick={handleStartFollowClick}
                  fullWidth
                  size="small"
                  startIcon={<PlayCircleOutlineIcon />}
                  disabled={!canStartFollowing || followActionPending}
                  sx={{ minHeight: 36 }}
                >
                  {commandPreviewMode ? 'Start Follower Test' : 'Start Following'}
                </Button>
              </span>
            </Tooltip>
          ) : (
            <Tooltip title={followingStateKnown
              ? commandPreviewMode
                ? 'Stop the local follower test immediately'
                : 'Disengage offboard mode and stop following immediately'
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
                  startIcon={<StopCircleIcon />}
                  disabled={!canExecuteActions}
                  sx={{ minHeight: 36 }}
                >
                  {commandPreviewMode ? 'Stop Test' : 'Stop Following'}
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
          {commandPreviewMode ? 'Start Local Follower Test?' : 'Engage Autonomous Following?'}
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            {commandPreviewMode
              ? 'Run follower math locally. PX4 command dispatch remains blocked.'
              : 'Start Offboard following. The aircraft may move immediately.'}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {commandPreviewMode
              ? 'This validates command intents only; it is not a flight test.'
              : 'Confirm a clear area, a fresh target, and an operator-ready abort path.'}
          </Typography>
          {trackerUsabilityKnown && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {trackerStatus.chipLabel}; {trackerStatus.followLabel || 'follower state unknown'}.
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleFollowCancel}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleFollowConfirm}
            disabled={!canStartFollowing || followActionPending}
          >
            {commandPreviewMode ? 'Start Test' : 'Engage'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ActionButtons;
