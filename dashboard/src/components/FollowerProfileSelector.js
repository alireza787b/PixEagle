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
  // Always keep dropdown in sync with configured/active profile
  React.useEffect(() => {
    if (currentProfile && currentProfile.mode && !switching) {
      // Only update if different to avoid unnecessary re-renders
      if (selectedProfile !== currentProfile.mode) {
        setSelectedProfile(currentProfile.mode);
      }
    }
  }, [currentProfile, switching, selectedProfile]);

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
  const followingEngaged = Boolean(currentProfile?.active);
  const configuredMode = currentProfile?.configured_mode || currentProfile?.mode;

  return (
    <Box sx={{ mb: 0, minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.25, flexWrap: 'wrap' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1 }}>
          Follower Profile
        </Typography>
        {currentProfile?.display_name && (
          <Chip
            label={currentProfile.display_name}
            color={currentProfile.active ? 'primary' : 'default'}
            size="small"
            variant={currentProfile.active ? 'filled' : 'outlined'}
          />
        )}
      </Box>

      {/* Profile Selector */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 1.5,
          alignItems: { xs: 'stretch', sm: 'center' },
          mb: 1,
          minWidth: 0,
        }}
      >
        {followingEngaged && (
          <Alert severity="info" sx={{ width: '100%' }}>
            Stop follow mode before changing the control profile.
          </Alert>
        )}
        <FormControl sx={{ minWidth: 0, width: { xs: '100%', sm: 360 }, maxWidth: '100%' }} size="small">
          <InputLabel>Follower Profile</InputLabel>
          <Select
            value={selectedProfile}
            onChange={handleProfileChange}
            label="Follower Profile"
            disabled={switching || followingEngaged}
            sx={{
              '& .MuiSelect-select': {
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              },
            }}
          >
            {availableProfiles.map(([key, profile]) => (
              <MenuItem 
                key={key} 
                value={key}
                disabled={configuredMode === key}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" noWrap>
                    {profile.display_name}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis' }}
                    noWrap
                  >
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
          disabled={
            !selectedProfile
            || selectedProfile === configuredMode
            || switching
            || followingEngaged
          }
          startIcon={switching ? <CircularProgress size={16} /> : null}
          sx={{
            width: { xs: '100%', sm: 'auto' },
            minHeight: 40,
            flexShrink: 0,
          }}
        >
          {switching ? 'Saving...' : 'Save Profile'}
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

      {/* Confirmation Dialog */}
      <Dialog open={confirmDialog} onClose={handleCancelSwitch}>
        <DialogTitle>Save Follower Profile</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Save the follower profile change from{' '}
            <strong>{currentProfile?.display_name || 'current profile'}</strong>{' '}
            to{' '}
            <strong>{profiles[selectedProfile]?.display_name}</strong>?
          </DialogContentText>
          <DialogContentText sx={{ mt: 2 }}>
            The active control path will not change. This profile is applied by a
            follower restart or when the next follow session starts.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelSwitch}>Cancel</Button>
          <Button onClick={handleConfirmSwitch} variant="contained">
            Save Profile
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default FollowerProfileSelector;
