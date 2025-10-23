// dashboard/src/components/FollowerProfileSelector.js
import React, { useState } from 'react';
import {
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Typography,
  Chip,
  Alert,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle
} from '@mui/material';
import { useFollowerProfiles, useCurrentFollowerProfile } from '../hooks/useFollowerSchema';

const FollowerProfileSelector = () => {
  const { profiles, loading: profilesLoading } = useFollowerProfiles();
  const { currentProfile, switchProfile, loading: currentLoading } = useCurrentFollowerProfile();

  const [selectedProfile, setSelectedProfile] = useState('');
  const [switching, setSwitching] = useState(false);
  const [switchResult, setSwitchResult] = useState(null);
  const [confirmDialog, setConfirmDialog] = useState(false);

  // Pre-select current active profile in dropdown
  React.useEffect(() => {
    if (currentProfile && currentProfile.mode && !switching) {
      setSelectedProfile(currentProfile.mode);
    }
  }, [currentProfile, switching]);

  const handleProfileChange = (event) => {
    setSelectedProfile(event.target.value);
  };

  const handleSwitchClick = () => {
    if (selectedProfile) {
      setConfirmDialog(true);
    }
  };

  const handleConfirmSwitch = async () => {
    setConfirmDialog(false);
    setSwitching(true);
    setSwitchResult(null);

    try {
      const result = await switchProfile(selectedProfile);
      setSwitchResult(result);

      // Don't reset selection - the useEffect will update it to current profile automatically
    } catch (error) {
      setSwitchResult({
        success: false,
        message: `Error: ${error.message}`
      });
    } finally {
      setSwitching(false);
    }
  };

  const handleCancelSwitch = () => {
    setConfirmDialog(false);
  };

  if (profilesLoading || currentLoading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <CircularProgress size={20} />
        <Typography>Loading profiles...</Typography>
      </Box>
    );
  }

  const availableProfiles = Object.entries(profiles).filter(
    ([key, profile]) => profile.implementation_available
  );

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Follower Control Profile Selector
      </Typography>
      <Typography variant="caption" color="textSecondary" display="block" sx={{ mb: 2 }}>
        Switch between different control modes (velocity, attitude, position)
      </Typography>

      {/* Current Profile Display */}
      {currentProfile && currentProfile.active && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" color="textSecondary" gutterBottom>
            Current Profile:
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Chip 
              label={currentProfile.display_name}
              color="primary"
              variant="filled"
            />
            <Chip 
              label={currentProfile.control_type}
              size="small"
              variant="outlined"
            />
            <Chip 
              label={currentProfile.validation_status ? 'Valid' : 'Invalid'}
              color={currentProfile.validation_status ? 'success' : 'error'}
              size="small"
            />
          </Box>
        </Box>
      )}

      {/* Profile Selector */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2 }}>
        <FormControl sx={{ minWidth: 200 }} size="small">
          <InputLabel>Switch to Profile</InputLabel>
          <Select
            value={selectedProfile}
            onChange={handleProfileChange}
            label="Switch to Profile"
            disabled={switching}
          >
            {availableProfiles.map(([key, profile]) => (
              <MenuItem 
                key={key} 
                value={key}
                disabled={currentProfile?.mode === key}
              >
                <Box>
                  <Typography variant="body2">
                    {profile.display_name}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {profile.control_type} • {profile.description}
                  </Typography>
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Button
          variant="contained"
          onClick={handleSwitchClick}
          disabled={!selectedProfile || switching}
          startIcon={switching ? <CircularProgress size={16} /> : null}
        >
          {switching ? 'Switching...' : 'Switch Profile'}
        </Button>
      </Box>

      {/* Switch Result */}
      {switchResult && (
        <Alert 
          severity={switchResult.success ? 'success' : 'error'}
          onClose={() => setSwitchResult(null)}
          sx={{ mb: 2 }}
        >
          {switchResult.message}
        </Alert>
      )}

      {/* Available Profiles Summary */}
      <Box>
        <Typography variant="subtitle2" color="textSecondary" gutterBottom>
          Available Profiles: {availableProfiles.length}
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {availableProfiles.map(([key, profile]) => (
            <Chip
              key={key}
              label={profile.display_name}
              size="small"
              variant={currentProfile?.mode === key ? 'filled' : 'outlined'}
              color={currentProfile?.mode === key ? 'primary' : 'default'}
            />
          ))}
        </Box>
      </Box>

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialog} onClose={handleCancelSwitch}>
        <DialogTitle>Confirm Profile Switch</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to switch from{' '}
            <strong>{currentProfile?.display_name || 'current profile'}</strong>{' '}
            to{' '}
            <strong>{profiles[selectedProfile]?.display_name}</strong>?
          </DialogContentText>
          <DialogContentText sx={{ mt: 2, color: 'warning.main' }}>
            This will immediately change the drone's control behavior.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelSwitch}>Cancel</Button>
          <Button onClick={handleConfirmSwitch} variant="contained" color="warning">
            Confirm Switch
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default FollowerProfileSelector;