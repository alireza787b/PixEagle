// dashboard/src/components/OperationalStatusBar.js
import React from 'react';
import { Box, Chip, Stack, Tooltip } from '@mui/material';
import SensorsIcon from '@mui/icons-material/Sensors';
import { normalizeTrackerStatus } from '../hooks/useStatuses';

const OperationalStatusBar = ({
  isTracking,
  trackerStatus,
  smartModeActive,
  activeModelName,
  smartTrackerRuntime,
  isFollowing,
  circuitBreakerActive,
  telemetryStatus,
}) => {
  const normalizedTrackerStatus = trackerStatus || (
    typeof isTracking === 'object'
      ? isTracking
      : normalizeTrackerStatus({
        active: Boolean(isTracking),
        has_output: Boolean(isTracking),
        usable_for_following: Boolean(isTracking),
      })
  );
  const trackerTooltip = normalizedTrackerStatus
    ? [
        normalizedTrackerStatus.detail,
        normalizedTrackerStatus.hasOutput !== undefined
          ? `has output: ${normalizedTrackerStatus.hasOutput ? 'yes' : 'no'}`
          : null,
        normalizedTrackerStatus.usableForFollowing !== undefined
          ? `follower usable: ${normalizedTrackerStatus.usableForFollowing ? 'yes' : 'no'}`
          : null,
      ].filter(Boolean).join(' | ')
    : 'Tracker status unavailable';

  const telemetryTooltip = telemetryStatus
    ? [
        telemetryStatus.detail,
        telemetryStatus.transport?.latestRequestResult
          ? `latest request: ${telemetryStatus.transport.latestRequestResult}`
          : null,
        telemetryStatus.requestFreshness?.fresh !== undefined
          ? `fresh: ${telemetryStatus.requestFreshness.fresh ? 'yes' : 'no'}`
          : null,
      ].filter(Boolean).join(' | ')
    : 'Telemetry unavailable';
  const smartModeKnown = typeof smartModeActive === 'boolean';
  const commandInhibitKnown = typeof circuitBreakerActive === 'boolean';
  const followingStateKnown = typeof isFollowing === 'boolean';
  const modeLabel = smartModeKnown
    ? smartModeActive
      ? `Smart${activeModelName ? `: ${activeModelName}` : ' (AI)'}`
      : 'Classic'
    : 'Unknown';
  const computeDevice = String(
    smartTrackerRuntime?.effective_device || '',
  ).trim().toLowerCase();
  const computeFallback = smartTrackerRuntime?.fallback_occurred === true;
  const computeStatus = smartModeActive === true
    ? computeDevice === 'cuda'
      ? { label: 'Compute: CUDA', color: 'success', variant: 'filled' }
      : computeDevice === 'cpu'
        ? {
            label: computeFallback ? 'Compute: CPU fallback' : 'Compute: CPU',
            color: computeFallback ? 'warning' : 'info',
            variant: computeFallback ? 'filled' : 'outlined',
          }
        : computeDevice
          ? {
              label: `Compute: ${computeDevice.toUpperCase()}`,
              color: 'info',
              variant: 'outlined',
            }
          : { label: 'Compute: Loading', color: 'default', variant: 'outlined' }
    : null;
  const computeTooltip = computeStatus
    ? [
        smartTrackerRuntime?.device_name,
        smartTrackerRuntime?.backend
          ? `backend: ${smartTrackerRuntime.backend}`
          : null,
        smartTrackerRuntime?.compute_capability
          ? `compute capability: ${smartTrackerRuntime.compute_capability}`
          : null,
        computeFallback
          ? smartTrackerRuntime?.fallback_reason || 'GPU load failed; CPU fallback is active'
          : null,
      ].filter(Boolean).join(' | ') || 'SmartTracker compute runtime is starting'
    : '';

  return (
    <Box
      sx={{
        py: 1,
        px: 2,
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap justifyContent="center">
        <Tooltip title={trackerTooltip}>
          <Chip
            label={normalizedTrackerStatus.chipLabel}
            size="small"
            color={normalizedTrackerStatus.color}
            variant={normalizedTrackerStatus.usableForFollowing ? 'filled' : 'outlined'}
            sx={{ fontWeight: 600, fontSize: 12 }}
          />
        </Tooltip>
        <Tooltip title={smartModeActive && activeModelName ? `Active model: ${activeModelName}` : ''}>
          <Chip
            label={`Mode: ${modeLabel}`}
            size="small"
            color={smartModeKnown ? (smartModeActive ? 'secondary' : 'primary') : 'default'}
            variant="outlined"
            sx={{
              fontWeight: 600,
              fontSize: 12,
              maxWidth: { xs: 190, sm: 280 },
              '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' },
            }}
          />
        </Tooltip>
        {computeStatus && (
          <Tooltip title={computeTooltip}>
            <Chip
              label={computeStatus.label}
              size="small"
              color={computeStatus.color}
              variant={computeStatus.variant}
              sx={{ fontWeight: 600, fontSize: 12 }}
            />
          </Tooltip>
        )}
        <Chip
          label={`Following: ${followingStateKnown ? (isFollowing ? 'ON' : 'OFF') : 'UNKNOWN'}`}
          size="small"
          color={followingStateKnown ? (isFollowing ? 'warning' : 'default') : 'warning'}
          variant={isFollowing === true ? 'filled' : 'outlined'}
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
        <Chip
          label={`Command: ${commandInhibitKnown ? (circuitBreakerActive ? 'Blocked' : 'Live') : 'Unknown'}`}
          size="small"
          color={commandInhibitKnown ? (circuitBreakerActive ? 'warning' : 'success') : 'default'}
          variant="outlined"
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
        {telemetryStatus && (
          <Tooltip title={telemetryTooltip}>
            <Chip
              icon={<SensorsIcon />}
              label={telemetryStatus.chipLabel}
              size="small"
              color={telemetryStatus.color}
              variant={telemetryStatus.usableForFollowing ? 'filled' : 'outlined'}
              sx={{ fontWeight: 600, fontSize: 12 }}
            />
          </Tooltip>
        )}
      </Stack>
    </Box>
  );
};

export default OperationalStatusBar;
