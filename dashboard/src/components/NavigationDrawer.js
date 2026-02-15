// dashboard/src/components/NavigationDrawer.js
import React, { useState, useEffect } from 'react';
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
  Tooltip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import LiveTvIcon from '@mui/icons-material/LiveTv';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import SettingsIcon from '@mui/icons-material/Settings';
import VideocamIcon from '@mui/icons-material/Videocam';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { Link, useLocation } from 'react-router-dom';
import { useTrackerStatus, useFollowerStatus } from '../hooks/useStatuses';
import QuitButton from './QuitButton';
import { endpoints } from '../services/apiEndpoints';

export const DRAWER_WIDTH = 220;

const NAV_SECTIONS = [
  {
    label: 'Operations',
    items: [
      { path: '/dashboard', label: 'Dashboard', icon: DashboardIcon },
      { path: '/live-feed', label: 'Live Feed', icon: LiveTvIcon },
      { path: '/recordings', label: 'Recordings', icon: VideocamIcon },
      { path: '/models', label: 'Models', icon: SmartToyIcon },
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

  const [versionInfo, setVersionInfo] = useState(null);
  const [showVersionDialog, setShowVersionDialog] = useState(false);

  const currentPath = location.pathname === '/' ? '/dashboard' : location.pathname;

  // Fetch version info
  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const response = await fetch(endpoints.systemConfig);
        const data = await response.json();
        if (data.success && data.config) {
          setVersionInfo({
            version: data.config.version || 'unknown',
            git: data.config.git || {},
          });
        }
      } catch (error) {
        console.error('Failed to fetch version info:', error);
      }
    };

    fetchVersion();
    // Refresh version info every 5 minutes
    const interval = setInterval(fetchVersion, 300000);
    return () => clearInterval(interval);
  }, []);

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
      <Box sx={{ px: 2, pb: 1.5 }}>
        <QuitButton fullWidth />
      </Box>

      {/* Version Info Footer */}
      {versionInfo && (
        <>
          <Divider />
          <Box
            sx={{
              px: 2,
              py: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              bgcolor: 'action.hover',
            }}
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <Typography variant="caption" sx={{ fontSize: 10, fontWeight: 600, color: 'text.secondary' }}>
                v{versionInfo.version}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  fontSize: 9,
                  color: 'text.disabled',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {versionInfo.git.commit !== 'unknown' ? `${versionInfo.git.commit}` : 'dev build'}
              </Typography>
            </Box>
            <Tooltip title="Version Info">
              <IconButton size="small" onClick={() => setShowVersionDialog(true)} sx={{ p: 0.5 }}>
                <InfoOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </>
      )}
    </Box>
  );

  // Version info dialog
  const versionDialog = versionInfo && (
    <Dialog open={showVersionDialog} onClose={() => setShowVersionDialog(false)} maxWidth="xs" fullWidth>
      <DialogTitle>PixEagle Version Info</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">
              Version
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {versionInfo.version}
            </Typography>
          </Box>
          {versionInfo.git.commit !== 'unknown' && (
            <>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Commit
                </Typography>
                <Typography variant="body2" fontFamily="monospace">
                  {versionInfo.git.commit}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Branch
                </Typography>
                <Typography variant="body2" fontFamily="monospace">
                  {versionInfo.git.branch}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Date
                </Typography>
                <Typography variant="body2">
                  {versionInfo.git.date}
                </Typography>
              </Box>
            </>
          )}
          <Divider />
          <Box>
            <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
              Project
            </Typography>
            <Typography variant="body2">
              <a
                href="https://github.com/alireza787b/PixEagle"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: theme.palette.primary.main, textDecoration: 'none' }}
              >
                github.com/alireza787b/PixEagle
              </a>
            </Typography>
          </Box>
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setShowVersionDialog(false)}>Close</Button>
      </DialogActions>
    </Dialog>
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

      {/* Version Info Dialog */}
      {versionDialog}
    </Box>
  );
};

export default NavigationDrawer;
