import React from 'react';
import {
  Box,
  Chip,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';
import LogoutIcon from '@mui/icons-material/Logout';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import { useAuthSession } from '../context/AuthSessionContext';

const AuthStatusMenu = () => {
  const {
    authenticated,
    principal,
    usesBrowserSession,
    logout,
    logoutPending,
  } = useAuthSession();

  if (!usesBrowserSession) {
    return (
      <Tooltip title="Same-host local compatibility">
        <Chip
          icon={<LockOpenIcon />}
          label="Local"
          size="small"
          color="default"
          variant="outlined"
          sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.55)' }}
        />
      </Tooltip>
    );
  }

  if (!authenticated) {
    return null;
  }

  const label = principal?.subject || principal?.role || 'operator';

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Tooltip title={principal?.role ? `Role: ${principal.role}` : 'Signed in'}>
        <Chip
          icon={<AccountCircleIcon />}
          label={<Typography variant="caption">{label}</Typography>}
          size="small"
          color="default"
          variant="outlined"
          sx={{ color: 'inherit', borderColor: 'rgba(255,255,255,0.55)' }}
        />
      </Tooltip>
      <Tooltip title="Sign out">
        <span>
          <IconButton
            color="inherit"
            size="small"
            onClick={() => logout()}
            disabled={logoutPending}
            aria-label="sign out"
          >
            <LogoutIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    </Box>
  );
};

export default AuthStatusMenu;
