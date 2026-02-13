// dashboard/src/components/RecordingIndicator.js
/**
 * Small "REC" overlay indicator for the video feed.
 *
 * Positioned absolute in the top-right corner of the video card.
 * Only visible when recording is active. Shows a pulsing red dot
 * with "REC" text for immediate visual feedback.
 */

import React from 'react';
import { Box, Typography } from '@mui/material';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import { useRecording } from '../hooks/useRecording';

const RecordingIndicator = () => {
  const { recordingStatus } = useRecording(2000);

  const isActive = recordingStatus?.is_active === true;
  const isPaused = recordingStatus?.state === 'paused';

  if (!isActive) return null;

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 8,
        right: 8,
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        bgcolor: 'rgba(0, 0, 0, 0.7)',
        borderRadius: 1,
        px: 1,
        py: 0.25,
        zIndex: 10,
        pointerEvents: 'none',
      }}
    >
      <FiberManualRecordIcon
        sx={{
          fontSize: 12,
          color: isPaused ? 'warning.main' : '#ff1744',
          ...(!isPaused && {
            animation: 'rec-blink 1s ease-in-out infinite',
            '@keyframes rec-blink': {
              '0%, 100%': { opacity: 1 },
              '50%': { opacity: 0.2 },
            },
          }),
        }}
      />
      <Typography
        variant="caption"
        sx={{
          color: '#fff',
          fontWeight: 700,
          fontSize: 10,
          letterSpacing: 1,
          lineHeight: 1,
        }}
      >
        {isPaused ? 'PAUSED' : 'REC'}
      </Typography>
    </Box>
  );
};

export default RecordingIndicator;
