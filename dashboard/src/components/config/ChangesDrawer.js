// dashboard/src/components/config/ChangesDrawer.js
/**
 * ChangesDrawer - Slide-in panel for viewing configuration changes (v5.4.0+)
 *
 * Tabs:
 * - Unsaved: Local changes not yet persisted to disk
 * - Modified: Current values that differ from factory defaults
 * - Restart: Saved changes awaiting restart (non-immediate tier)
 */

import React, { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import {
  Drawer, Box, Typography, IconButton, Tabs, Tab, Chip, Button,
  List, ListItem, ListItemText, ListItemSecondaryAction, Divider,
  Alert, Tooltip
} from '@mui/material';
import {
  Close, Save, Undo, Warning, Check, Schedule, Sync,
  RestartAlt, FlightTakeoff, GpsFixed
} from '@mui/icons-material';

import { useConfigGlobalState } from '../../hooks/useConfigGlobalState';
import { useConfigDiff } from '../../hooks/useConfig';
import { ReloadTierChip } from './ReloadTierBadge';
import DiffViewer from './DiffViewer';

/**
 * Tab panel component
 */
const TabPanel = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ py: 2, overflow: 'auto', flexGrow: 1 }}>
    {value === index && children}
  </Box>
);

TabPanel.propTypes = {
  children: PropTypes.node,
  value: PropTypes.number.isRequired,
  index: PropTypes.number.isRequired,
};

/**
 * ChangesDrawer - Slide-in panel for viewing and managing changes
 *
 * @param {Object} props
 * @param {boolean} props.open - Whether the drawer is open
 * @param {Function} props.onClose - Callback when drawer closes
 * @param {Array} props.pendingRestartParams - Params awaiting restart
 * @param {Function} props.onMessage - Callback for toast messages
 */
const ChangesDrawer = ({
  open,
  onClose,
  pendingRestartParams = [],
  onMessage,
}) => {
  const [tabIndex, setTabIndex] = useState(0);
  const globalState = useConfigGlobalState();
  const { diff: modifiedFromDefaults, loading: diffLoading, refetch: refetchDiff } = useConfigDiff();

  // Calculate tab counts
  const unsavedCount = globalState.totalUnsaved || 0;
  const modifiedCount = modifiedFromDefaults?.length || 0;
  const restartCount = pendingRestartParams?.length || 0;

  // Format value for display
  const formatValue = (value) => {
    if (value === null || value === undefined) return 'null';
    if (typeof value === 'object') return JSON.stringify(value).slice(0, 30) + '...';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value).slice(0, 30);
  };

  // Get icon for restart tier
  const getRestartIcon = (tier) => {
    switch (tier) {
      case 'follower_restart':
        return <FlightTakeoff fontSize="small" />;
      case 'tracker_restart':
        return <GpsFixed fontSize="small" />;
      case 'system_restart':
        return <RestartAlt fontSize="small" />;
      default:
        return <Schedule fontSize="small" />;
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: { width: { xs: '100%', sm: 400, md: 450 }, display: 'flex', flexDirection: 'column' }
      }}
    >
      {/* Header */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        p: 2,
        borderBottom: 1,
        borderColor: 'divider'
      }}>
        <Typography variant="h6">Configuration Changes</Typography>
        <IconButton onClick={onClose} size="small">
          <Close />
        </IconButton>
      </Box>

      {/* Tabs */}
      <Tabs
        value={tabIndex}
        onChange={(e, newVal) => setTabIndex(newVal)}
        variant="fullWidth"
        sx={{ borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Warning fontSize="small" color={unsavedCount > 0 ? 'warning' : 'inherit'} />
              Unsaved
              {unsavedCount > 0 && (
                <Chip label={unsavedCount} size="small" color="warning" sx={{ height: 20 }} />
              )}
            </Box>
          }
        />
        <Tab
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Sync fontSize="small" color={modifiedCount > 0 ? 'info' : 'inherit'} />
              Modified
              {modifiedCount > 0 && (
                <Chip label={modifiedCount} size="small" color="info" sx={{ height: 20 }} />
              )}
            </Box>
          }
        />
        <Tab
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Schedule fontSize="small" color={restartCount > 0 ? 'error' : 'inherit'} />
              Restart
              {restartCount > 0 && (
                <Chip label={restartCount} size="small" color="error" sx={{ height: 20 }} />
              )}
            </Box>
          }
        />
      </Tabs>

      {/* Tab Panels */}
      <Box sx={{ flexGrow: 1, overflow: 'auto', p: 2 }}>
        {/* Unsaved Tab */}
        <TabPanel value={tabIndex} index={0}>
          {unsavedCount === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Check sx={{ fontSize: 48, color: 'success.main', mb: 1 }} />
              <Typography color="text.secondary">All changes saved</Typography>
            </Box>
          ) : (
            <>
              <Alert severity="warning" sx={{ mb: 2 }}>
                {unsavedCount} unsaved change{unsavedCount > 1 ? 's' : ''} in memory.
                Press Enter or blur from a field to save.
              </Alert>
              <List dense>
                {globalState.unsavedParams?.map((param, idx) => (
                  <React.Fragment key={`${param.section}-${param.param}`}>
                    <ListItem sx={{ bgcolor: 'warning.lighter', borderRadius: 1, mb: 0.5 }}>
                      <ListItemText
                        primary={
                          <Typography variant="body2" fontFamily="monospace">
                            {param.section}.{param.param}
                          </Typography>
                        }
                        secondary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                            <Typography variant="caption" color="error.main" sx={{ textDecoration: 'line-through' }}>
                              {formatValue(param.oldValue)}
                            </Typography>
                            <Typography variant="caption">→</Typography>
                            <Typography variant="caption" color="success.main">
                              {formatValue(param.newValue)}
                            </Typography>
                          </Box>
                        }
                      />
                    </ListItem>
                    {idx < globalState.unsavedParams.length - 1 && <Divider component="li" />}
                  </React.Fragment>
                ))}
              </List>
            </>
          )}
        </TabPanel>

        {/* Modified Tab */}
        <TabPanel value={tabIndex} index={1}>
          {modifiedCount === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Check sx={{ fontSize: 48, color: 'success.main', mb: 1 }} />
              <Typography color="text.secondary">All values match defaults</Typography>
            </Box>
          ) : (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                {modifiedCount} parameter{modifiedCount > 1 ? 's' : ''} differ from factory defaults.
              </Alert>
              <DiffViewer
                differences={modifiedFromDefaults || []}
                selectable={false}
                showFilter={true}
                compact={false}
              />
            </>
          )}
        </TabPanel>

        {/* Restart Tab */}
        <TabPanel value={tabIndex} index={2}>
          {restartCount === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Check sx={{ fontSize: 48, color: 'success.main', mb: 1 }} />
              <Typography color="text.secondary">No restart pending</Typography>
            </Box>
          ) : (
            <>
              <Alert severity="error" sx={{ mb: 2 }}>
                {restartCount} saved change{restartCount > 1 ? 's' : ''} require restart to take effect.
              </Alert>
              <List dense>
                {pendingRestartParams.map((param, idx) => (
                  <React.Fragment key={`${param.section}-${param.param}`}>
                    <ListItem sx={{ bgcolor: 'error.lighter', borderRadius: 1, mb: 0.5 }}>
                      <ListItemText
                        primary={
                          <Typography variant="body2" fontFamily="monospace">
                            {param.section}.{param.param}
                          </Typography>
                        }
                        secondary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                            {param.reloadTier && (
                              <ReloadTierChip tier={param.reloadTier} size="small" />
                            )}
                          </Box>
                        }
                      />
                      <ListItemSecondaryAction>
                        <Tooltip title={`Requires ${param.reloadTier || 'restart'}`}>
                          {getRestartIcon(param.reloadTier)}
                        </Tooltip>
                      </ListItemSecondaryAction>
                    </ListItem>
                    {idx < pendingRestartParams.length - 1 && <Divider component="li" />}
                  </React.Fragment>
                ))}
              </List>
            </>
          )}
        </TabPanel>
      </Box>

      {/* Footer Actions */}
      <Box sx={{
        p: 2,
        borderTop: 1,
        borderColor: 'divider',
        display: 'flex',
        gap: 1,
        justifyContent: 'flex-end'
      }}>
        <Button
          variant="outlined"
          startIcon={<Sync />}
          onClick={() => {
            refetchDiff();
            onMessage?.('Changes refreshed', 'info');
          }}
        >
          Refresh
        </Button>
        <Button
          variant="contained"
          onClick={onClose}
        >
          Close
        </Button>
      </Box>
    </Drawer>
  );
};

ChangesDrawer.propTypes = {
  /** Whether the drawer is open */
  open: PropTypes.bool.isRequired,
  /** Callback when drawer closes */
  onClose: PropTypes.func.isRequired,
  /** Parameters awaiting restart */
  pendingRestartParams: PropTypes.array,
  /** Callback for toast messages */
  onMessage: PropTypes.func,
};

export default ChangesDrawer;
