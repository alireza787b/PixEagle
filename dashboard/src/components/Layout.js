import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { CssBaseline, Box } from '@mui/material';
import Header from './Header';
import Footer from './Footer';
import NavigationDrawer from './NavigationDrawer';

const Layout = () => {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <CssBaseline />
      <Header handleDrawerToggle={handleDrawerToggle} />
      <NavigationDrawer mobileOpen={mobileOpen} handleDrawerToggle={handleDrawerToggle} />
      <Box component="main" sx={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </Box>
      <Footer />
    </Box>
  );
};

export default Layout;
