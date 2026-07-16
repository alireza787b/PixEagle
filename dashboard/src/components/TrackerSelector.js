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
  IconButton,
  Tooltip,
  Skeleton
} from '@mui/material';
import {
  TrackChanges,
  SwapHoriz,
  CheckCircle,
  Warning,
  Info
} from '@mui/icons-material';
import {
  useAvailableTrackers,
  useCurrentTracker,
  useSwitchTracker
} from '../hooks/useTrackerSchema';
import { useTrackerStatus } from '../hooks/useStatuses';

// Loading skeleton component
const LoadingSkeleton = () => (
  <Box sx={{ py: 0.5 }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
      <Skeleton variant="text" width={120} height={24} />
      <Skeleton variant="circular" width={28} height={28} />
    </Box>
    <Skeleton variant="rectangular" height={40} sx={{ borderRadius: 1, mb: 1 }} />
    <Skeleton variant="rectangular" height={34} sx={{ borderRadius: 1 }} />
  </Box>
);

/**
 * Utility function to find matching tracker key from available trackers.
 * Handles various naming conventions (exact, case-insensitive, with/without suffix, prefix matching).
 *
 * @param {string} trackerType - The tracker type to match (e.g., "dlib", "CSRT")
 * @param {string[]} availableKeys - Array of available tracker keys (e.g., ["DlibTracker", "CSRTTracker"])
 * @returns {string|null} - Matching key or null if not found
 */
const findMatchingTrackerKey = (trackerType, availableKeys) => {
  if (!trackerType || !availableKeys || availableKeys.length === 0) {
    return null;
  }

  const normalizedType = trackerType.toLowerCase();

  // Strategy 1: Exact match
  if (availableKeys.includes(trackerType)) {
    return trackerType;
  }

  // Strategy 2: Case-insensitive exact match
  let match = availableKeys.find(key => key.toLowerCase() === normalizedType);
  if (match) return match;

  // Strategy 3: Match with "Tracker" suffix (e.g., "dlib" -> "DlibTracker")
  match = availableKeys.find(key => key.toLowerCase() === `${normalizedType}tracker`);
  if (match) return match;

  // Strategy 4: Key starts with tracker type (e.g., "csrt" -> "CSRTTracker", "kcf" -> "KCFKalmanTracker")
  match = availableKeys.find(key => key.toLowerCase().startsWith(normalizedType));
  if (match) return match;

  // No match found
  return null;
};

const TrackerSelector = memo(() => {
  // Custom hooks for tracker data
  const { trackers, loading: loadingTrackers, error: trackersError } = useAvailableTrackers();
  const { currentTracker, loading: loadingCurrent, error: currentError } = useCurrentTracker();
  const trackerRuntimeStatus = useTrackerStatus(3000);
  const { switchTracker, switching, switchError } = useSwitchTracker();

  // Local state
  const [selectedTracker, setSelectedTracker] = useState('');

  // Track pending user selection to prevent polling from overwriting it
  // This fixes the race condition where 2-second polling would reset user's dropdown choice
  const hasPendingSelection = React.useRef(false);

  const currentTrackerKey = useMemo(() => {
    if (!currentTracker?.tracker_type || !trackers?.available_trackers) {
      return currentTracker?.tracker_type || null;
    }
    return findMatchingTrackerKey(
      currentTracker.tracker_type,
      Object.keys(trackers.available_trackers)
    );
  }, [currentTracker, trackers]);

  if (hasPendingSelection.current && selectedTracker && currentTrackerKey === selectedTracker) {
    hasPendingSelection.current = false;
  }

  // Update selected tracker when current tracker changes (pre-select current active tracker)
  // Only sync with backend when there's no pending user selection
  React.useEffect(() => {
    // Skip sync if user has a pending selection that hasn't been applied yet
    // This prevents polling from overwriting the user's dropdown choice
    if (hasPendingSelection.current) {
      if (selectedTracker && currentTrackerKey && selectedTracker === currentTrackerKey) {
        hasPendingSelection.current = false;
      } else {
        return;
      }
    }

    if (currentTrackerKey) {
      setSelectedTracker(currentTrackerKey);
    } else if (currentTracker && currentTracker.tracker_type && trackers?.available_trackers) {
        console.warn(
          `TrackerSelector: Current tracker "${currentTracker.tracker_type}" not found in available trackers.`,
          'Available:', Object.keys(trackers.available_trackers)
        );
    }
  }, [currentTracker, currentTrackerKey, selectedTracker, trackers]);

  // Memoized tracker list for dropdown
  const trackerOptions = useMemo(() => {
    if (!trackers || !trackers.available_trackers) return [];

    return Object.entries(trackers.available_trackers).map(([key, tracker]) => ({
      value: tracker.request_tracker_type || key,
      label: tracker.ui_metadata?.display_name || key,
      icon: tracker.ui_metadata?.icon || '🎯',
      description: tracker.ui_metadata?.short_description || tracker.description || '',
      performance: tracker.ui_metadata?.performance_category || 'unknown',
      available: tracker.available !== false,
      unavailableReason: tracker.unavailable_reason || 'Tracker is unavailable in this runtime'
    }));
  }, [trackers]);

  const selectedTrackerOption = useMemo(
    () => trackerOptions.find((option) => option.value === selectedTracker) || null,
    [selectedTracker, trackerOptions]
  );

  // Memoized current tracker details
  const currentTrackerInfo = useMemo(() => {
    if (!currentTracker) return null;

    return {
      displayName: currentTracker.display_name || currentTracker.tracker_type,
      icon: currentTracker.icon || '🎯',
      status: currentTracker.status || 'configured',
      isTracking: trackerRuntimeStatus.activeTracking || false,
      description: currentTracker.short_description || currentTracker.description || '',
      performanceCategory: currentTracker.performance_category || 'unknown',
      capabilities: currentTracker.capabilities || [],
      suitableFor: currentTracker.suitable_for || [],
      runtime: trackerRuntimeStatus
    };
  }, [currentTracker, trackerRuntimeStatus]);

  // Handle tracker selection change
  const handleTrackerChange = useCallback((event) => {
    const newValue = event.target.value;
    setSelectedTracker(newValue);

    // Mark as pending selection if different from current tracker
    // This prevents polling from overwriting user's choice before they click "Switch"
    if (newValue !== currentTrackerKey) {
      hasPendingSelection.current = true;
    } else {
      // User selected current tracker again, no pending change
      hasPendingSelection.current = false;
    }
  }, [currentTrackerKey]);

  // Handle switch button click
  const handleSwitch = useCallback(async () => {
    if (!selectedTracker || selectedTracker === currentTrackerKey) {
      return;
    }

    const success = await switchTracker(selectedTracker);

    // Clear pending selection flag after switch attempt (success or failure)
    // This allows polling to sync the dropdown with backend state again
    hasPendingSelection.current = false;

    // If switch was successful and tracking was active, show info message
    // (The user will need to restart tracking to use the new tracker)
    if (success && currentTracker?.active) {
      // Info alert will be shown via switchError state from the hook
    }
  }, [selectedTracker, currentTracker, currentTrackerKey, switchTracker]);

  // Check if switch button should be disabled
  const isSwitchDisabled = useMemo(() => {
    return (
      !selectedTracker ||
      selectedTracker === currentTrackerKey ||
      switching ||
      loadingTrackers ||
      loadingCurrent ||
      selectedTrackerOption?.available === false ||
      currentTracker?.following_active // Safety: block switching while following active
    );
  }, [selectedTracker, selectedTrackerOption, currentTracker, currentTrackerKey, switching, loadingTrackers, loadingCurrent]);

  // Status icon and color
  const getStatusInfo = () => {
    if (!currentTrackerInfo) return { icon: <Warning />, color: 'error', label: 'Unknown' };

    const runtime = currentTrackerInfo.runtime;
    if (runtime?.usableForFollowing) {
      return { icon: <CheckCircle />, color: 'success', label: runtime.label };
    }
    if (runtime?.dataIsStale || (runtime?.hasOutput && !runtime?.usableForFollowing)) {
      return { icon: <Warning />, color: runtime.color || 'warning', label: runtime.label };
    }
    if (runtime?.guidance === 'unavailable') {
      return { icon: <Warning />, color: 'error', label: runtime.label };
    }
    if (runtime?.guidance === 'pending') {
      return { icon: <Info />, color: 'info', label: runtime.label };
    }

    return { icon: <Info />, color: runtime?.color || 'default', label: runtime?.label || 'Configured' };
  };

  // Show loading skeleton
  if (loadingTrackers && !trackers) {
    return <LoadingSkeleton />;
  }

  // Show error state
  if ((trackersError || currentError) && !trackers && !currentTracker) {
    return (
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600 }}>
          Classic Tracker
        </Typography>
        <Alert severity="error" size="small">
          {trackersError || currentError || 'Failed to load tracker data'}
        </Alert>
      </Box>
    );
  }

  const statusInfo = getStatusInfo();
  const catalogError = trackersError || currentError;

  return (
    <>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Classic Tracker
        </Typography>
        <Tooltip title="Select tracking algorithm">
          <IconButton size="small">
            <TrackChanges fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {catalogError && (
        <Alert severity="error" size="small" sx={{ mb: 1 }}>
          {catalogError}
        </Alert>
      )}

      {/* Current Status Chips */}
      {currentTrackerInfo && (
        <Box sx={{ display: 'flex', gap: 0.5, mb: 1.5, flexWrap: 'wrap' }}>
          <Chip
            label={statusInfo.label}
            color={statusInfo.color}
            size="small"
            icon={statusInfo.icon}
            sx={{ height: 22, fontSize: 11 }}
          />
          {trackerRuntimeStatus?.hasOutput && (
            <Chip
              label={trackerRuntimeStatus.followLabel}
              color={trackerRuntimeStatus.followColor}
              size="small"
              sx={{ height: 22, fontSize: 11 }}
            />
          )}
          <Chip
            label={`${currentTrackerInfo.icon} ${currentTrackerInfo.displayName}`}
            color="primary"
            size="small"
            sx={{ height: 22, fontSize: 11 }}
          />
        </Box>
      )}

      {/* Tracker Selection Dropdown */}
      <FormControl fullWidth size="small" sx={{ mb: 1 }}>
        <InputLabel id="tracker-select-label">Tracker Algorithm</InputLabel>
        <Select
          labelId="tracker-select-label"
          value={selectedTracker}
          onChange={handleTrackerChange}
          label="Tracker Algorithm"
          disabled={switching || loadingTrackers}
        >
          {trackerOptions.map((option) => (
            <MenuItem key={option.value} value={option.value} disabled={!option.available}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
                <span>{option.icon}</span>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2">{option.label}</Typography>
                  {!option.available && (
                    <Typography variant="caption" color="text.secondary">
                      {option.unavailableReason}
                    </Typography>
                  )}
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
        size="small"
        startIcon={switching ? <CircularProgress size={16} color="inherit" /> : <SwapHoriz />}
        onClick={handleSwitch}
        disabled={isSwitchDisabled}
      >
        {switching ? 'Switching...' : 'Switch Tracker'}
      </Button>

      {/* Safety Warning - Block switching while following */}
      {currentTracker?.following_active && (
        <Alert severity="warning" size="small" sx={{ mt: 1 }}>
          <Typography variant="caption">
            Cannot switch while following is active.
          </Typography>
        </Alert>
      )}

      {/* Switch Error/Info Alert */}
      {switchError && (
        <Alert
          severity={switchError.includes('Stop tracking') ? 'info' : 'error'}
          size="small"
          sx={{ mt: 1 }}
        >
          <Typography variant="caption">
            {switchError}
          </Typography>
        </Alert>
      )}
    </>
  );
});

export default TrackerSelector;
