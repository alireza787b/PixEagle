// dashboard/src/components/TrackerModeToggle.js
import React, { useState } from 'react';
import { Switch, FormControlLabel, Typography, Box } from '@mui/material';
import { endpoints } from '../services/apiEndpoints';

const TrackerModeToggle = ({ smartModeActive, setSmartModeActive }) => {
  const [loading, setLoading] = useState(false);

  const handleToggle = async () => {
    setLoading(true);
    try {
      await fetch(endpoints.toggleSmartMode, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      setSmartModeActive((prev) => !prev);
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
