// dashboard/src/components/FollowerQuickControl.js
import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  FormControl,
  Select,
  MenuItem,
  Button,
  Alert,
  CircularProgress,
  Chip,
  Tooltip,
  IconButton
} from '@mui/material';
import { SwapHoriz, Speed, ControlCamera, PowerSettingsNew, PowerOff, FlightTakeoff } from '@mui/icons-material';
import { useFollowerProfiles, useCurrentFollowerProfile } from '../hooks/useFollowerSchema';

const FollowerQuickControl = () => {
  const { profiles, loading: profilesLoading } = useFollowerProfiles();
  const { currentProfile, switchProfile, loading: currentLoading, isTransitioning } = useCurrentFollowerProfile();
  
  const [selectedProfile, setSelectedProfile] = useState('');
  const [switchResult, setSwitchResult] = useState(null);

  // Pre-select current active profile in dropdown (always keep in sync)
  React.useEffect(() => {
    if (currentProfile && currentProfile.mode) {
      setSelectedProfile(currentProfile.mode);
    }
  }, [currentProfile]);

  const handleQuickSwitch = async () => {
    if (!selectedProfile) return;

    setSwitchResult(null);

    try {
      const result = await switchProfile(selectedProfile);
      setSwitchResult(result);
      
      if (result.success) {
        setSelectedProfile('');
      }
    } catch (error) {
      setSwitchResult({
        success: false,
        message: `Error: ${error.message}`
      });
    }
  };

  if (profilesLoading || currentLoading) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Quick Control</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading...</Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  // Include ALL available profiles (don't filter out current one)
  const availableProfiles = Object.entries(profiles).filter(
    ([key, profile]) => profile.implementation_available
  );

  const getProfileIcon = (controlType) => {
    return controlType === 'velocity_body' ? <Speed /> : <ControlCamera />;
  };

  const getStatusIcon = (status) => {
    return status === 'engaged' ? <PowerSettingsNew /> : <PowerOff />;
  };

  const isEngaged = currentProfile?.status === 'engaged';
  const switchAction = isEngaged ? 'Switch Active' : 'Switch Follower';

  return (
    <>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Follower Profile
        </Typography>
        <Tooltip title="Select follower profile">
          <IconButton size="small">
            <FlightTakeoff fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Current Profile Status */}
      {currentProfile && (
        <Box sx={{ display: 'flex', gap: 0.5, mb: 1.5, flexWrap: 'wrap' }}>
          <Chip
            label={isEngaged ? "Active" : "Configured"}
            color={isEngaged ? "success" : "default"}
            size="small"
            icon={getStatusIcon(currentProfile.status)}
            sx={{ height: 22, fontSize: 11 }}
          />
          <Chip
            label={currentProfile.display_name || 'Unknown'}
            color="primary"
            size="small"
            icon={getProfileIcon(currentProfile.control_type)}
            sx={{ height: 22, fontSize: 11 }}
          />
        </Box>
      )}

      {/* Quick Switch */}
      <FormControl fullWidth size="small" sx={{ mb: 1 }}>
        <Select
          value={selectedProfile}
          onChange={(e) => setSelectedProfile(e.target.value)}
          disabled={isTransitioning || availableProfiles.length === 0}
          displayEmpty
          renderValue={(selected) => {
            const profile = availableProfiles.find(([key]) => key === selected);
            if (!profile) return <Typography variant="body2" color="text.secondary">Select Profile</Typography>;
            return (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {getProfileIcon(profile[1].control_type)}
                <Typography variant="body2">{profile[1].display_name}</Typography>
              </Box>
            );
          }}
        >
          {availableProfiles.map(([key, profile]) => (
            <MenuItem key={key} value={key}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {getProfileIcon(profile.control_type)}
                <Typography variant="body2">
                  {profile.display_name}
                </Typography>
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Button
        fullWidth
        variant="contained"
        color="primary"
        size="small"
        onClick={handleQuickSwitch}
        disabled={!selectedProfile || isTransitioning}
        startIcon={isTransitioning ? <CircularProgress size={16} color="inherit" /> : <SwapHoriz />}
      >
        {isTransitioning ? 'Switching...' : switchAction}
      </Button>

      {/* Switch Result */}
      {switchResult && (
        <Alert
          severity={switchResult.success ? 'success' : 'error'}
          onClose={() => setSwitchResult(null)}
          size="small"
          sx={{ mt: 1 }}
        >
          <Typography variant="caption">
            {switchResult.message}
          </Typography>
        </Alert>
      )}
    </>
  );
};

export default FollowerQuickControl;