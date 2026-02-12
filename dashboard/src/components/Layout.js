import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { CssBaseline, Box } from '@mui/material';
import Header from './Header';
import Footer from './Footer';
import NavigationDrawer, { DRAWER_WIDTH } from './NavigationDrawer';

const Layout = () => {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <CssBaseline />
      <NavigationDrawer mobileOpen={mobileOpen} handleDrawerToggle={handleDrawerToggle} />
      <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, width: { lg: `calc(100% - ${DRAWER_WIDTH}px)` } }}>
        <Header handleDrawerToggle={handleDrawerToggle} />
        <Box component="main" sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <Outlet />
        </Box>
        <Footer />
      </Box>
    </Box>
  );
};

export default Layout;
