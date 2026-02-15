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

const ActionButtons = ({
  isTracking,
  isFollowing,
  smartModeActive,
  handleTrackingToggle,
  handleButtonClick,
  handleToggleSmartMode,
}) => {
  const [switchLoading, setSwitchLoading] = useState(false);
  const [followConfirmOpen, setFollowConfirmOpen] = useState(false);

  const handleSmartModeSwitch = async (event, newMode) => {
    if (newMode === null) return; // Prevent deselection
    const wantSmart = newMode === 'smart';
    if (wantSmart === smartModeActive) return; // Already in this mode
    setSwitchLoading(true);
    await handleToggleSmartMode();
    setSwitchLoading(false);
  };

  const handleStartFollowClick = () => {
    setFollowConfirmOpen(true);
  };

  const handleFollowConfirm = () => {
    setFollowConfirmOpen(false);
    handleButtonClick(endpoints.startOffboardMode);
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
            disabled={switchLoading}
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
                disabled={smartModeActive}
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
                disabled={smartModeActive}
              >
                Re-Detect
              </Button>
            </span>
          </Tooltip>

          <Tooltip title="Cancel all tracking activities and reset">
            <Button
              variant="outlined"
              color="warning"
              onClick={() => handleButtonClick(endpoints.cancelActivities, true)}
              fullWidth
              size="small"
              sx={{ mt: 0.5 }}
            >
              Cancel Tracker
            </Button>
          </Tooltip>
        </Grid>

        {/* Segmentation */}
        <Grid item xs={12}>
          <Tooltip title="Toggle AI segmentation overlay">
            <Button
              variant="outlined"
              color="secondary"
              onClick={() => handleButtonClick(endpoints.toggleSegmentation)}
              fullWidth
              size="small"
            >
              Toggle Segmentation
            </Button>
          </Tooltip>
        </Grid>

        {/* Drone Control - Follow */}
        <Grid item xs={12}>
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
            Drone Control
          </Typography>

          {!isFollowing ? (
            <Tooltip title="Engage offboard mode and start autonomous following">
              <Button
                variant="contained"
                color="success"
                onClick={handleStartFollowClick}
                fullWidth
                size="small"
              >
                Start Following
              </Button>
            </Tooltip>
          ) : (
            <Tooltip title="Disengage offboard mode and stop following immediately">
              <Button
                variant="contained"
                color="error"
                onClick={() => handleButtonClick(endpoints.stopOffboardMode)}
                fullWidth
                size="small"
              >
                Stop Following
              </Button>
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
            Active tracking must be established first for reliable following.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleFollowCancel}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleFollowConfirm}
          >
            Engage
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ActionButtons;
