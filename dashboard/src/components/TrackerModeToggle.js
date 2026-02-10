// dashboard/src/components/TrackerModeToggle.js
import React, { useState, useCallback, useEffect } from 'react';
import { Switch, FormControlLabel, Typography, Box } from '@mui/material';
import { endpoints } from '../services/apiEndpoints';

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const TrackerModeToggle = ({ smartModeActive, setSmartModeActive }) => {
  const [loading, setLoading] = useState(false);

  const refreshSmartModeStatus = useCallback(async () => {
    const response = await fetch(endpoints.status, {
      cache: 'no-store',
      headers: NO_STORE_HEADERS,
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch smart mode status (${response.status})`);
    }

    const data = await response.json();
    setSmartModeActive(Boolean(data.smart_mode_active));
  }, [setSmartModeActive]);

  useEffect(() => {
    refreshSmartModeStatus().catch((err) => {
      console.error('Failed to sync tracker mode status:', err);
    });
  }, [refreshSmartModeStatus]);

  const handleToggle = async () => {
    setLoading(true);
    try {
      const response = await fetch(endpoints.toggleSmartMode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Failed to toggle tracker mode (${response.status})`);
      }

      await refreshSmartModeStatus();
    } catch (err) {
      console.error('Failed to toggle tracker mode:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" gutterBottom>
        Tracker Mode
      </Typography>
      <FormControlLabel
        control={
          <Switch
            checked={smartModeActive}
            onChange={handleToggle}
            disabled={loading}
            color="primary"
          />
        }
        label={smartModeActive ? 'Smart Tracker' : 'Classic Tracker'}
      />
    </Box>
  );
};

export default TrackerModeToggle;
