// dashboard/src/components/OperationalStatusBar.js
import React from 'react';
import { Box, Chip, Stack, Tooltip } from '@mui/material';
import SensorsIcon from '@mui/icons-material/Sensors';

const OperationalStatusBar = ({
  isTracking,
  smartModeActive,
  isFollowing,
  circuitBreakerActive,
  telemetryStatus,
}) => {
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
        <Chip
          label={`Tracking: ${isTracking ? 'ON' : 'OFF'}`}
          size="small"
          color={isTracking ? 'success' : 'default'}
          variant={isTracking ? 'filled' : 'outlined'}
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
        <Chip
          label={`Mode: ${smartModeActive ? 'Smart (AI)' : 'Classic'}`}
          size="small"
          color={smartModeActive ? 'secondary' : 'primary'}
          variant="outlined"
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
        <Chip
          label={`Following: ${isFollowing ? 'ON' : 'OFF'}`}
          size="small"
          color={isFollowing ? 'warning' : 'default'}
          variant={isFollowing ? 'filled' : 'outlined'}
          sx={{ fontWeight: 600, fontSize: 12 }}
        />
        {circuitBreakerActive !== undefined && (
          <Chip
            label={`Safety: ${circuitBreakerActive ? 'Testing' : 'Live'}`}
            size="small"
            color={circuitBreakerActive ? 'warning' : 'success'}
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: 12 }}
          />
        )}
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
