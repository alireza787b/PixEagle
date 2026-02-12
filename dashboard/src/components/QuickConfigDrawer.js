// dashboard/src/components/QuickConfigDrawer.js
import React from 'react';
import {
  Drawer,
  Box,
  Typography,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  IconButton,
  Chip,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TrackChangesIcon from '@mui/icons-material/TrackChanges';
import FlightTakeoffIcon from '@mui/icons-material/FlightTakeoff';
import VideocamIcon from '@mui/icons-material/Videocam';
import SecurityIcon from '@mui/icons-material/Security';
import TuneIcon from '@mui/icons-material/Tune';
import SettingsIcon from '@mui/icons-material/Settings';
import { useNavigate } from 'react-router-dom';

const QuickConfigDrawer = ({ open, onClose }) => {
  const navigate = useNavigate();

  const goToSettings = (section) => {
    onClose();
    navigate(section ? `/settings#${section}` : '/settings');
  };

  const configLinks = [
    { label: 'Tracker Settings', icon: TrackChangesIcon, section: 'SmartTracker' },
    { label: 'Follower Settings', icon: FlightTakeoffIcon, section: 'MC_VELOCITY_CHASE_FOLLOWER' },
    { label: 'Video Source', icon: VideocamIcon, section: 'VideoSource' },
    { label: 'Safety Limits', icon: SecurityIcon, section: 'Safety' },
    { label: 'OSD Display', icon: TuneIcon, section: 'OSD' },
  ];

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      sx={{ '& .MuiDrawer-paper': { width: 280 } }}
    >
      <Box sx={{ p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            Quick Settings
          </Typography>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
        <Divider />

        <List dense sx={{ mt: 1 }}>
          {configLinks.map((link) => {
            const Icon = link.icon;
            return (
              <ListItemButton
                key={link.section}
                onClick={() => goToSettings(link.section)}
                sx={{ borderRadius: 1, mb: 0.25 }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Icon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary={link.label}
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItemButton>
            );
          })}
        </List>

        <Divider sx={{ my: 1 }} />

        <ListItemButton
          onClick={() => goToSettings(null)}
          sx={{ borderRadius: 1 }}
        >
          <ListItemIcon sx={{ minWidth: 36 }}>
            <SettingsIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText
            primary="Open Full Settings"
            primaryTypographyProps={{ variant: 'body2', fontWeight: 600 }}
          />
          <Chip label="All" size="small" variant="outlined" sx={{ height: 20, fontSize: 10 }} />
        </ListItemButton>
      </Box>
    </Drawer>
  );
};

export default QuickConfigDrawer;
