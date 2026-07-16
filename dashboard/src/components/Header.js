import React from 'react';
import {
  AppBar, Toolbar, Typography, IconButton, Box
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import ThemeToggle from './ThemeToggle';
import BackendStatusIndicator from './BackendStatusIndicator';
import AuthStatusMenu from './AuthStatusMenu';

const Header = ({ handleDrawerToggle }) => {
  return (
    <AppBar position="static" sx={{ minWidth: 0 }}>
      <Toolbar sx={{ px: { xs: 1, sm: 2 }, gap: { xs: 0.5, sm: 1 }, minWidth: 0 }}>
        <IconButton
          edge="start"
          color="inherit"
          aria-label="menu"
          onClick={handleDrawerToggle}
          sx={{ display: { lg: 'none' } }}
        >
          <MenuIcon />
        </IconButton>
        <Typography
          variant="h6"
          noWrap
          sx={{
            flexGrow: 1,
            minWidth: 0,
            fontSize: { xs: '1.05rem', sm: '1.25rem' },
          }}
        >
          PixEagle
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 0.25, sm: 1 }, flexShrink: 0 }}>
          <BackendStatusIndicator />
          <AuthStatusMenu />
          <ThemeToggle size="small" />
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Header;
