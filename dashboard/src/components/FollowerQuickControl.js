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
  Chip
} from '@mui/material';
import { SwapHoriz, Speed, ControlCamera, PowerSettingsNew, PowerOff } from '@mui/icons-material';
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
  const switchAction = isEngaged ? 'Switch Active' : 'Configure';

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Follower Profile
        </Typography>

        {/* Current Profile Status */}
        {currentProfile && (
          <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
            <Chip
              label={isEngaged ? "Active" : "Configured"}
              color={isEngaged ? "success" : "default"}
              size="small"
              icon={getStatusIcon(currentProfile.status)}
            />
            <Chip
              label={currentProfile.display_name || 'Unknown'}
              color="primary"
              size="small"
              icon={getProfileIcon(currentProfile.control_type)}
            />
            <Chip
              label={currentProfile.control_type}
              size="small"
              variant="outlined"
            />
          </Box>
        )}

        {/* Quick Switch */}
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 140, flexGrow: 1 }}>
            <Select
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value)}
              disabled={isTransitioning || availableProfiles.length === 0}
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
            variant="contained"
            size="small"
            onClick={handleQuickSwitch}
            disabled={!selectedProfile || isTransitioning}
            startIcon={isTransitioning ? <CircularProgress size={16} /> : <SwapHoriz />}
          >
            {isTransitioning ? 'Switching...' : switchAction}
          </Button>
        </Box>

        {/* Switch Result */}
        {switchResult && (
          <Alert 
            severity={switchResult.success ? 'success' : 'error'}
            onClose={() => setSwitchResult(null)}
            sx={{ mb: 1 }}
          >
            <Typography variant="caption">
              {switchResult.message}
            </Typography>
          </Alert>
        )}

        {/* Help Text */}
        <Typography variant="caption" color="textSecondary">
          {isEngaged
            ? `Follower is active with current profile. Switch to change control mode instantly.`
            : `Configured profile will be used when offboard mode starts. ${availableProfiles.length} profile${availableProfiles.length !== 1 ? 's' : ''} available.`
          }
        </Typography>
      </CardContent>
    </Card>
  );
};

export default FollowerQuickControl;