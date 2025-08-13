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

  const availableProfiles = Object.entries(profiles).filter(
    ([key, profile]) => profile.implementation_available && currentProfile?.mode !== key
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
          Quick Profile {switchAction}
        </Typography>

        {/* Current Profile */}
        {currentProfile && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="textSecondary">
              Current {isEngaged ? '(Active)' : '(Configured)'}:
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
              {getStatusIcon(currentProfile.status)}
              {getProfileIcon(currentProfile.control_type)}
              <Chip 
                label={currentProfile.display_name || 'Unknown'}
                color={isEngaged ? 'success' : 'warning'}
                size="small"
              />
            </Box>
          </Box>
        )}

        {/* Quick Switch */}
        <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 140, flexGrow: 1 }}>
            <Select
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value)}
              displayEmpty
              disabled={isTransitioning || availableProfiles.length === 0}
            >
              <MenuItem value="" disabled>
                <em>{switchAction} to...</em>
              </MenuItem>
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
            ? `${availableProfiles.length} profile${availableProfiles.length !== 1 ? 's' : ''} available for switching`
            : `Configure profile for when offboard mode starts. ${availableProfiles.length} option${availableProfiles.length !== 1 ? 's' : ''} available.`
          }
        </Typography>
      </CardContent>
    </Card>
  );
};

export default FollowerQuickControl;