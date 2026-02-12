// dashboard/src/components/NavigationDrawer.js
import React from 'react';
import {
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Box,
  Divider,
  Chip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import LiveTvIcon from '@mui/icons-material/LiveTv';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import SettingsIcon from '@mui/icons-material/Settings';
import { Link, useLocation } from 'react-router-dom';
import { useTrackerStatus, useFollowerStatus } from '../hooks/useStatuses';
import QuitButton from './QuitButton';

export const DRAWER_WIDTH = 220;

const NAV_SECTIONS = [
  {
    label: 'Operations',
    items: [
      { path: '/dashboard', label: 'Dashboard', icon: DashboardIcon },
      { path: '/live-feed', label: 'Live Feed', icon: LiveTvIcon },
    ],
  },
  {
    label: 'Telemetry',
    items: [
      { path: '/tracker', label: 'Tracker Data', icon: TrackChangesIcon },
      { path: '/follower', label: 'Follower Data', icon: FlightTakeoffIcon },
    ],
  },
  {
    label: 'System',
    items: [
      { path: '/settings', label: 'Settings', icon: SettingsIcon },
    ],
  },
];

const NavigationDrawer = ({ mobileOpen, handleDrawerToggle }) => {
  const location = useLocation();
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up('lg'));

  const isTracking = useTrackerStatus(3000);
  const isFollowing = useFollowerStatus(3000);

  const currentPath = location.pathname === '/' ? '/dashboard' : location.pathname;

  const drawer = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', pt: 1 }}>
      {/* Brand */}
      <Box sx={{ px: 2, py: 1.5, mb: 0.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, letterSpacing: 0.5 }}>
          PixEagle
        </Typography>
      </Box>
      <Divider />

      {/* Navigation Sections */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {NAV_SECTIONS.map((section) => (
          <List
            key={section.label}
            dense
            subheader={
              <ListSubheader
                disableSticky
                sx={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 1,
                  textTransform: 'uppercase',
                  lineHeight: '32px',
                  color: 'text.secondary',
                }}
              >
                {section.label}
              </ListSubheader>
            }
          >
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = currentPath === item.path;
              return (
                <ListItemButton
                  key={item.path}
                  component={Link}
                  to={item.path}
                  selected={isActive}
                  onClick={!isDesktop ? handleDrawerToggle : undefined}
                  sx={{
                    borderRadius: 1,
                    mx: 1,
                    mb: 0.25,
                    '&.Mui-selected': {
                      bgcolor: 'action.selected',
                    },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 36 }}>
                    <Icon fontSize="small" color={isActive ? 'primary' : 'action'} />
                  </ListItemIcon>
                  <ListItemText
                    primary={item.label}
                    primaryTypographyProps={{
                      variant: 'body2',
                      fontWeight: isActive ? 600 : 400,
                    }}
                  />
                </ListItemButton>
              );
            })}
          </List>
        ))}
      </Box>

      {/* Status Chips */}
      <Divider />
      <Box sx={{ px: 2, py: 1.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        <Chip
          label={isTracking ? 'Tracking' : 'Idle'}
          size="small"
          color={isTracking ? 'success' : 'default'}
          variant={isTracking ? 'filled' : 'outlined'}
          sx={{ fontSize: 11, height: 22 }}
        />
        <Chip
          label={isFollowing ? 'Following' : 'Standby'}
          size="small"
          color={isFollowing ? 'warning' : 'default'}
          variant={isFollowing ? 'filled' : 'outlined'}
          sx={{ fontSize: 11, height: 22 }}
        />
      </Box>

      {/* Quit Button */}
      <Box sx={{ px: 2, pb: 2 }}>
        <QuitButton fullWidth />
      </Box>
    </Box>
  );

  return (
    <Box
      component="nav"
      sx={{ width: { lg: DRAWER_WIDTH }, flexShrink: { lg: 0 } }}
    >
      {/* Mobile / Tablet: temporary overlay drawer */}
      <Drawer
        variant="temporary"
        open={mobileOpen}
        onClose={handleDrawerToggle}
        ModalProps={{ keepMounted: true }}
        sx={{
          display: { xs: 'block', lg: 'none' },
          '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
        }}
      >
        {drawer}
      </Drawer>

      {/* Desktop: persistent permanent drawer */}
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', lg: 'block' },
          '& .MuiDrawer-paper': {
            boxSizing: 'border-box',
            width: DRAWER_WIDTH,
            borderRight: '1px solid',
            borderColor: 'divider',
          },
        }}
        open
      >
        {drawer}
      </Drawer>
    </Box>
  );
};

export default NavigationDrawer;
