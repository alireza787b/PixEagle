//dashboard/src/components/QuitButton.js
import React from 'react';
import { Button, Tooltip } from '@mui/material';
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew';
import { endpoints } from '../services/apiEndpoints';

const QuitButton = ({ fullWidth = false, sx = {} }) => {
  const handleQuit = async () => {
    try {
      const response = await fetch(endpoints.quit, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
      });
      const data = await response.json();
      console.log(`Response from ${endpoints.quit}:`, data);
      window.location.reload(); // Reload the page to ensure proper shutdown
    } catch (error) {
      console.error(`Error from ${endpoints.quit}:`, error);
      alert('Operation failed for Quit. Check console for details.');
    }
  };

  return (
    <Tooltip title="Quit application">
      <Button
        variant="contained"
        color="error"
        startIcon={<PowerSettingsNewIcon />}
        onClick={handleQuit}
        fullWidth={fullWidth}
        sx={sx}
      >
        Quit
      </Button>
    </Tooltip>
  );
};

export default QuitButton;
