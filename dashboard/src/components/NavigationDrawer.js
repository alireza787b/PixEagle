import React from 'react';
import { Drawer, List, ListItem, ListItemIcon, ListItemText, Box } from '@mui/material';
import HomeIcon from '@mui/icons-material/Home';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import DashboardIcon from '@mui/icons-material/Dashboard';
import LiveTvIcon from '@mui/icons-material/LiveTv';
import { Link } from 'react-router-dom';
import QuitButton from './QuitButton';

const NavigationDrawer = ({ mobileOpen, handleDrawerToggle }) => {
  const drawer = (
    <div>
      <List>
        <ListItem button component={Link} to="/">
          <ListItemIcon><HomeIcon /></ListItemIcon>
          <ListItemText primary="Home" />
        </ListItem>
        <ListItem button component={Link} to="/dashboard">
          <ListItemIcon><DashboardIcon /></ListItemIcon>
          <ListItemText primary="Dashboard" />
        </ListItem>
        <ListItem button component={Link} to="/tracker">
          <ListItemIcon><TrackChangesIcon /></ListItemIcon>
          <ListItemText primary="Tracker" />
        </ListItem>
        <ListItem button component={Link} to="/follower">
          <ListItemIcon><TrackChangesIcon /></ListItemIcon>
          <ListItemText primary="Follower" />
        </ListItem>
        <ListItem button component={Link} to="/live-feed">
          <ListItemIcon><LiveTvIcon /></ListItemIcon>
          <ListItemText primary="Live Feed" />
        </ListItem>
      </List>
      <Box sx={{ p: 2 }}>
        <QuitButton fullWidth />
      </Box>
    </div>
  );

  return (
    <nav>
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={handleDrawerToggle}
        ModalProps={{ keepMounted: true }}
      >
        {drawer}
      </Drawer>
    </nav>
  );
};

export default NavigationDrawer;
