// dashboard/src/components/TrackerSelector.js

/**
 * TrackerSelector Component
 *
 * A UI component for dynamically selecting and switching between different tracker types.
 * Mirrors the FollowerSelector UI pattern for consistency.
 *
 * Features:
 * - Schema-driven tracker list (no hardcoding)
 * - Real-time status display (tracking/configured)
 * - Smooth transitions during switching
 * - Error handling and user feedback
 * - Excludes SmartTracker (controlled via toggle) and non-UI trackers
 *
 * Project: PixEagle
 * Author: Alireza Ghaderi
 * Repository: https://github.com/alireza787b/PixEagle
 */

import React, { useState, useMemo, useCallback, memo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Alert,
  CircularProgress,
  Collapse,
  IconButton,
  Tooltip,
  Skeleton
} from '@mui/material';
import {
  TrackChanges,
  SwapHoriz,
  CheckCircle,
  Warning,
  ExpandMore,
  ExpandLess,
  Info,
  Speed,
  Visibility,
  FlightTakeoff
} from '@mui/icons-material';
import {
  useAvailableTrackers,
  useCurrentTracker,
  useSwitchTracker
} from '../hooks/useTrackerSchema';

// Loading skeleton component
const LoadingSkeleton = () => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Skeleton variant="text" width={150} height={32} />
        <Skeleton variant="circular" width={40} height={40} />
      </Box>
      <Skeleton variant="rectangular" height={56} sx={{ borderRadius: 1, mb: 2 }} />
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Skeleton variant="rectangular" width={80} height={24} sx={{ borderRadius: 1 }} />
        <Skeleton variant="rectangular" width={90} height={24} sx={{ borderRadius: 1 }} />
      </Box>
    </CardContent>
  </Card>
);

const TrackerSelector = memo(() => {
  // Custom hooks for tracker data
  const { trackers, loading: loadingTrackers, error: trackersError } = useAvailableTrackers();
  const { currentTracker, loading: loadingCurrent, error: currentError } = useCurrentTracker();
  const { switchTracker, switching, switchError } = useSwitchTracker();

  // Local state
  const [selectedTracker, setSelectedTracker] = useState('');
  const [showDetails, setShowDetails] = useState(false);

  // Update selected tracker when current tracker changes (pre-select current active tracker)
  React.useEffect(() => {
    if (currentTracker && currentTracker.tracker_type) {
      setSelectedTracker(currentTracker.tracker_type);
    }
  }, [currentTracker]);

  // Memoized tracker list for dropdown
  const trackerOptions = useMemo(() => {
    if (!trackers || !trackers.available_trackers) return [];

    return Object.entries(trackers.available_trackers).map(([key, tracker]) => ({
      value: key,
      label: tracker.ui_metadata?.display_name || key,
      icon: tracker.ui_metadata?.icon || '🎯',
      description: tracker.ui_metadata?.short_description || tracker.description || '',
      performance: tracker.ui_metadata?.performance_category || 'unknown'
    }));
  }, [trackers]);

  // Memoized current tracker details
  const currentTrackerInfo = useMemo(() => {
    if (!currentTracker) return null;

    return {
      displayName: currentTracker.display_name || currentTracker.tracker_type,
      icon: currentTracker.icon || '🎯',
      status: currentTracker.status || 'configured',
      isTracking: currentTracker.active || false,
      description: currentTracker.short_description || currentTracker.description || '',
      performanceCategory: currentTracker.performance_category || 'unknown',
      capabilities: currentTracker.capabilities || [],
      suitableFor: currentTracker.suitable_for || []
    };
  }, [currentTracker]);

  // Handle tracker selection change
  const handleTrackerChange = useCallback((event) => {
    setSelectedTracker(event.target.value);
  }, []);

  // Handle switch button click
  const handleSwitch = useCallback(async () => {
    if (!selectedTracker || selectedTracker === currentTracker?.tracker_type) {
      return;
    }

    const success = await switchTracker(selectedTracker);

    // If switch was successful and tracking was active, show info message
    // (The user will need to restart tracking to use the new tracker)
    if (success && currentTracker?.active) {
      // Info alert will be shown via switchError state from the hook
    }
  }, [selectedTracker, currentTracker, switchTracker]);

  // Check if switch button should be disabled
  const isSwitchDisabled = useMemo(() => {
    return (
      !selectedTracker ||
      selectedTracker === currentTracker?.tracker_type ||
      switching ||
      loadingTrackers ||
      loadingCurrent ||
      currentTracker?.following_active // Safety: block switching while following active
    );
  }, [selectedTracker, currentTracker, switching, loadingTrackers, loadingCurrent]);

  // Performance category badge color
  const getPerformanceCategoryColor = (category) => {
    const categoryColors = {
      'ultra_fast': '#4CAF50',
      'very_fast_high_accuracy': '#2196F3',
      'medium_speed_high_accuracy': '#FF9800',
      'external_data': '#9C27B0',
      'ai_powered': '#F44336'
    };
    return categoryColors[category] || '#757575';
  };

  // Status icon and color
  const getStatusInfo = () => {
    if (!currentTrackerInfo) return { icon: <Warning />, color: 'error', label: 'Unknown' };

    if (currentTrackerInfo.isTracking) {
      return { icon: <CheckCircle />, color: 'success', label: 'Tracking' };
    } else {
      return { icon: <Info />, color: 'warning', label: 'Configured' };
    }
  };

  // Show loading skeleton
  if (loadingTrackers && !trackers) {
    return <LoadingSkeleton />;
  }

  // Show error state
  if ((trackersError || currentError) && !trackers && !currentTracker) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Tracker Selector
          </Typography>
          <Alert severity="error" size="small">
            {trackersError || currentError || 'Failed to load tracker data'}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const statusInfo = getStatusInfo();

  return (
    <Card sx={{ height: '100%', opacity: switching ? 0.7 : 1, transition: 'opacity 0.3s' }}>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">
            Tracker Selector
          </Typography>
          <Tooltip title="Select different tracking algorithm">
            <IconButton size="small">
              <TrackChanges />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Current Status Chips */}
        {currentTrackerInfo && (
          <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
            <Chip
              label={statusInfo.label}
              color={statusInfo.color}
              size="small"
              icon={statusInfo.icon}
            />
            <Chip
              label={`${currentTrackerInfo.icon} ${currentTrackerInfo.displayName}`}
              color="primary"
              size="small"
            />
            {currentTrackerInfo.performanceCategory && (
              <Chip
                label={currentTrackerInfo.performanceCategory.replace(/_/g, ' ')}
                size="small"
                sx={{
                  bgcolor: getPerformanceCategoryColor(currentTrackerInfo.performanceCategory),
                  color: 'white'
                }}
                icon={<Speed fontSize="small" />}
              />
            )}
          </Box>
        )}

        {/* Tracker Selection Dropdown */}
        <FormControl fullWidth size="small" sx={{ mb: 2 }}>
          <InputLabel id="tracker-select-label">Select Tracker</InputLabel>
          <Select
            labelId="tracker-select-label"
            value={selectedTracker}
            onChange={handleTrackerChange}
            label="Select Tracker"
            disabled={switching || loadingTrackers}
          >
            {trackerOptions.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <span>{option.icon}</span>
                  <Box>
                    <Typography variant="body2">{option.label}</Typography>
                    <Typography variant="caption" color="textSecondary">
                      {option.description}
                    </Typography>
                  </Box>
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Switch Button */}
        <Button
          fullWidth
          variant="contained"
          color="primary"
          startIcon={switching ? <CircularProgress size={16} color="inherit" /> : <SwapHoriz />}
          onClick={handleSwitch}
          disabled={isSwitchDisabled}
          sx={{ mb: 2 }}
        >
          {switching ? 'Switching...' : 'Switch Tracker'}
        </Button>

        {/* Safety Warning - Block switching while following */}
        {currentTracker?.following_active && (
          <Alert severity="warning" size="small" sx={{ mb: 2 }}>
            <Typography variant="caption">
              Cannot switch tracker while following is active. Stop following first.
            </Typography>
          </Alert>
        )}

        {/* Switch Error/Info Alert */}
        {switchError && (
          <Alert
            severity={switchError.includes('Stop tracking') ? 'info' : 'error'}
            size="small"
            sx={{ mb: 2 }}
          >
            <Typography variant="caption">
              {switchError}
            </Typography>
          </Alert>
        )}

        {/* Switching Progress */}
        {switching && (
          <Box sx={{ mb: 2 }}>
            <CircularProgress size={20} />
            <Typography variant="caption" color="textSecondary" sx={{ ml: 1 }}>
              Switching tracker...
            </Typography>
          </Box>
        )}

        {/* Tracker Details Expandable Section */}
        {currentTrackerInfo && (
          <>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                pt: 1,
                borderTop: '1px solid',
                borderColor: 'divider'
              }}
              onClick={() => setShowDetails(!showDetails)}
            >
              <Typography variant="caption" color="textSecondary">
                {showDetails ? 'Hide Details' : 'Show Details'}
              </Typography>
              <IconButton size="small">
                {showDetails ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              </IconButton>
            </Box>

            <Collapse in={showDetails}>
              <Box sx={{ mt: 1, pt: 1 }}>
                {/* Description */}
                <Typography variant="caption" color="textSecondary" paragraph>
                  {currentTrackerInfo.description}
                </Typography>

                {/* Capabilities */}
                {currentTrackerInfo.capabilities.length > 0 && (
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="caption" fontWeight="bold" display="block">
                      Capabilities:
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                      {currentTrackerInfo.capabilities.map((capability) => (
                        <Chip
                          key={capability}
                          label={capability.replace(/_/g, ' ')}
                          size="small"
                          variant="outlined"
                          sx={{ height: 20, fontSize: '0.65rem' }}
                        />
                      ))}
                    </Box>
                  </Box>
                )}

                {/* Suitable For */}
                {currentTrackerInfo.suitableFor.length > 0 && (
                  <Box>
                    <Typography variant="caption" fontWeight="bold" display="block">
                      Suitable For:
                    </Typography>
                    <Box component="ul" sx={{ m: 0, pl: 2, mt: 0.5 }}>
                      {currentTrackerInfo.suitableFor.map((item, index) => (
                        <Typography
                          key={index}
                          component="li"
                          variant="caption"
                          color="textSecondary"
                        >
                          {item}
                        </Typography>
                      ))}
                    </Box>
                  </Box>
                )}
              </Box>
            </Collapse>
          </>
        )}

        {/* Status Message */}
        {currentTracker?.message && !currentTracker.active && (
          <Alert severity="info" size="small" sx={{ mt: 2 }}>
            <Typography variant="caption">
              {currentTracker.message}
            </Typography>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
});

export default TrackerSelector;
