import React, { useState } from 'react';
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
import AccountManagementDialog from './AccountManagementDialog';

const AuthStatusMenu = () => {
  const [accountOpen, setAccountOpen] = useState(false);
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
    <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.25, sm: 0.5 }, minWidth: 0 }}>
      <Tooltip title={principal?.role ? `Role: ${principal.role}` : 'Signed in'}>
        <Chip
          icon={<AccountCircleIcon />}
          label={<Typography variant="caption" noWrap>{label}</Typography>}
          onClick={() => setAccountOpen(true)}
          aria-label={`Manage account for ${label}`}
          size="small"
          color="default"
          variant="outlined"
          sx={{
            color: 'inherit',
            borderColor: 'rgba(255,255,255,0.55)',
            maxWidth: { xs: 126, sm: 180 },
            '& .MuiChip-label': {
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            },
          }}
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
      <AccountManagementDialog
        open={accountOpen}
        onClose={() => setAccountOpen(false)}
      />
    </Box>
  );
};

export default AuthStatusMenu;
