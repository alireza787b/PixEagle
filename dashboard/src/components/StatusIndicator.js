//dashboard/src/components/StatusIndicator.js
import React from 'react';
import { Typography, Box, IconButton } from '@mui/material';
import { CheckCircle, Cancel } from '@mui/icons-material';

const StatusIndicator = ({ label, status }) => {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" mb={2}>
      <Typography variant="h6">{label}:</Typography>
      <IconButton>
        {status ? (
          <CheckCircle style={{ color: 'green' }} />
        ) : (
          <Cancel style={{ color: 'red' }} />
        )}
      </IconButton>
    </Box>
  );
};

export default StatusIndicator;
