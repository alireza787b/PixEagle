import React, { useState } from 'react';
import {
  AppBar, Toolbar, Typography, IconButton, Tooltip, Box,
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
  LinearProgress
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import ThemeToggle from './ThemeToggle';
import BackendStatusIndicator from './BackendStatusIndicator';
import useSystemRestart from '../hooks/useSystemRestart';

const Header = ({ handleDrawerToggle }) => {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const {
    restarting,
    error,
    pollCount,
    initiateRestart,
    clearError
  } = useSystemRestart({
    reloadPageOnSuccess: true
  });

  const handleRestartClick = () => {
    setConfirmOpen(true);
  };

  const handleConfirmRestart = async () => {
    setConfirmOpen(false);
    await initiateRestart('User requested restart from Header');
  };

  const handleCancelConfirm = () => {
    setConfirmOpen(false);
  };

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            aria-label="menu"
            onClick={handleDrawerToggle}
            sx={{ display: { lg: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" style={{ flexGrow: 1 }}>
            PixEagle
          </Typography>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <BackendStatusIndicator />

            <Tooltip title={restarting ? 'Restarting...' : 'Restart Backend'}>
              <span>
                <IconButton
                  color="inherit"
                  onClick={handleRestartClick}
                  disabled={restarting}
                  size="small"
                >
                  <RestartAltIcon />
                </IconButton>
              </span>
            </Tooltip>

            <ThemeToggle />
          </Box>
        </Toolbar>

        {restarting && <LinearProgress color="secondary" />}
      </AppBar>

      {/* Confirmation Dialog */}
      <Dialog
        open={confirmOpen}
        onClose={handleCancelConfirm}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <RestartAltIcon color="warning" />
          Confirm Restart
        </DialogTitle>
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            Are you sure you want to restart the backend?
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The application will briefly go offline while the backend restarts.
            Active tracking or following operations will be interrupted.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelConfirm}>Cancel</Button>
          <Button
            variant="contained"
            color="warning"
            onClick={handleConfirmRestart}
            startIcon={<RestartAltIcon />}
          >
            Restart Now
          </Button>
        </DialogActions>
      </Dialog>

      {/* Error Snackbar - could add Snackbar here if needed */}
      {error && (
        <Box
          sx={{
            position: 'fixed',
            bottom: 16,
            right: 16,
            bgcolor: 'error.main',
            color: 'white',
            p: 2,
            borderRadius: 1,
            boxShadow: 3,
            cursor: 'pointer'
          }}
          onClick={clearError}
        >
          {error} (click to dismiss)
        </Box>
      )}
    </>
  );
};

export default Header;
