// dashboard/src/components/BackendStatusIndicator.js
import React, { useState, useEffect, useCallback } from 'react';
import { Box, Tooltip, CircularProgress } from '@mui/material';
import { Circle } from '@mui/icons-material';
import { endpoints } from '../services/apiEndpoints';

const STATUS_POLL_INTERVAL = 5000; // 5 seconds

/**
 * BackendStatusIndicator - Shows backend connection status
 *
 * States:
 * - Green: Backend online and responding
 * - Red: Backend offline or not responding
 * - Yellow (spinner): Initial loading / checking
 */
const BackendStatusIndicator = () => {
  const [status, setStatus] = useState('checking'); // 'online', 'offline', 'checking'
  const [lastCheck, setLastCheck] = useState(null);

  const checkStatus = useCallback(async () => {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const response = await fetch(endpoints.systemStatus, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        setStatus('online');
      } else {
        setStatus('offline');
      }
    } catch (error) {
      setStatus('offline');
    }
    setLastCheck(new Date());
  }, []);

  useEffect(() => {
    // Initial check
    checkStatus();

    // Set up polling
    const interval = setInterval(checkStatus, STATUS_POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [checkStatus]);

  const getStatusColor = () => {
    switch (status) {
      case 'online':
        return '#4caf50'; // green
      case 'offline':
        return '#f44336'; // red
      default:
        return '#ff9800'; // orange for checking
    }
  };

  const getTooltipText = () => {
    const timeStr = lastCheck
      ? lastCheck.toLocaleTimeString()
      : 'checking...';

    switch (status) {
      case 'online':
        return `Backend online (last checked: ${timeStr})`;
      case 'offline':
        return `Backend offline (last checked: ${timeStr})`;
      default:
        return 'Checking backend status...';
    }
  };

  return (
    <Tooltip title={getTooltipText()}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          mr: 1,
          cursor: 'default'
        }}
      >
        {status === 'checking' ? (
          <CircularProgress size={16} sx={{ color: 'white' }} />
        ) : (
          <Circle
            sx={{
              fontSize: 12,
              color: getStatusColor(),
              filter: status === 'online'
                ? 'drop-shadow(0 0 3px rgba(76, 175, 80, 0.7))'
                : 'drop-shadow(0 0 3px rgba(244, 67, 54, 0.7))'
            }}
          />
        )}
      </Box>
    </Tooltip>
  );
};

export default BackendStatusIndicator;
