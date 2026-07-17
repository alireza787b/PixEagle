// dashboard/src/components/OperationalStatusBar.js
import React from 'react';
import { Box, Chip, Stack, Tooltip } from '@mui/material';
import SensorsIcon from '@mui/icons-material/Sensors';
import { normalizeTrackerStatus } from '../hooks/useStatuses';

const OperationalStatusBar = ({
  isTracking,
  trackerStatus,
  smartModeActive,
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
        <Chip
          label={`Mode: ${smartModeKnown ? (smartModeActive ? 'Smart (AI)' : 'Classic') : 'Unknown'}`}
          size="small"
          color={smartModeKnown ? (smartModeActive ? 'secondary' : 'primary') : 'default'}
          variant="outlined"
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
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
