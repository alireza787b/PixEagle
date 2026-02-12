// dashboard/src/components/OperationalStatusBar.js
import React from 'react';
import { Box, Chip, Stack } from '@mui/material';

const OperationalStatusBar = ({
  isTracking,
  smartModeActive,
  isFollowing,
  circuitBreakerActive,
}) => {
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
      </Stack>
    </Box>
  );
};

export default OperationalStatusBar;
