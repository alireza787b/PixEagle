// dashboard/src/components/config/SyncWithDefaultsDialog.js
/**
 * SyncWithDefaultsDialog - Dialog for syncing config with new defaults (v5.4.0+)
 *
 * Shows:
 * - New parameters available in defaults
 * - Changed default values
 * - Obsolete parameters to remove
 *
 * Allows selective acceptance of changes.
 */

import React, { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Typography, Button, Checkbox, Chip, Alert,
  List, ListItem, ListItemText, ListItemIcon, ListItemSecondaryAction,
  Divider, Collapse, IconButton, CircularProgress, Tooltip,
  Tabs, Tab, Badge
} from '@mui/material';
import {
  Sync, Add, Edit, Delete, ExpandMore, ExpandLess,
  CheckCircle, Warning, Info
} from '@mui/icons-material';

import { useDefaultsSync } from '../../hooks/useDefaultsSync';

/**
 * Tab panel component
 */
const TabPanel = ({ children, value, index }) => (
  <Box role="tabpanel" hidden={value !== index} sx={{ pt: 2 }}>
    {value === index && children}
  </Box>
);

TabPanel.propTypes = {
  children: PropTypes.node,
  value: PropTypes.number.isRequired,
  index: PropTypes.number.isRequired,
};

/**
 * SyncWithDefaultsDialog - Dialog for syncing with new defaults
 *
 * @param {Object} props
 * @param {boolean} props.open - Whether the dialog is open
 * @param {Function} props.onClose - Callback when dialog closes
 * @param {Function} props.onMessage - Callback for toast messages
 */
const SyncWithDefaultsDialog = ({
  open,
  onClose,
  onMessage,
}) => {
  const {
    newParameters,
    changedDefaults,
    removedParameters,
    counts,
    loading,
    error,
    refresh,
    acceptParameter,
    acceptAllNew,
  } = useDefaultsSync();

  const [tabIndex, setTabIndex] = useState(0);
  const [selectedNew, setSelectedNew] = useState(new Set());
  const [applying, setApplying] = useState(false);
  const [expandedSections, setExpandedSections] = useState({});

  // Group new parameters by section
  const groupedNewParams = useMemo(() => {
    const grouped = {};
    newParameters.forEach(param => {
      if (!grouped[param.section]) {
        grouped[param.section] = [];
      }
      grouped[param.section].push(param);
    });
    return grouped;
  }, [newParameters]);

  // Toggle section expansion
  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Toggle selection of a parameter
  const toggleSelection = (section, parameter) => {
    const key = `${section}.${parameter}`;
    setSelectedNew(prev => {
      const newSet = new Set(prev);
      if (newSet.has(key)) {
        newSet.delete(key);
      } else {
        newSet.add(key);
      }
      return newSet;
    });
  };

  // Select all new parameters
  const selectAllNew = () => {
    const allKeys = newParameters.map(p => `${p.section}.${p.parameter}`);
    setSelectedNew(new Set(allKeys));
  };

  // Deselect all
  const selectNone = () => {
    setSelectedNew(new Set());
  };

  // Apply selected new parameters
  const applySelected = async () => {
    if (selectedNew.size === 0) {
      onMessage?.('No parameters selected', 'warning');
      return;
    }

    setApplying(true);
    let successCount = 0;
    let failCount = 0;

    for (const key of selectedNew) {
      const [section, parameter] = key.split('.');
      const param = newParameters.find(
        p => p.section === section && p.parameter === parameter
      );

      if (param) {
        const result = await acceptParameter(section, parameter, param.default_value);
        if (result.success) {
          successCount++;
        } else {
          failCount++;
        }
      }
    }

    setApplying(false);
    setSelectedNew(new Set());

    if (failCount === 0) {
      onMessage?.(`${successCount} parameter(s) added successfully`, 'success');
    } else {
      onMessage?.(`${successCount} added, ${failCount} failed`, 'warning');
    }

    // Refresh the list
    refresh();
  };

  // Apply all new parameters
  const handleApplyAllNew = async () => {
    setApplying(true);
    const results = await acceptAllNew();
    setApplying(false);

    const successCount = results.filter(r => r.success).length;
    const failCount = results.filter(r => !r.success).length;

    if (failCount === 0) {
      onMessage?.(`${successCount} parameter(s) added successfully`, 'success');
    } else {
      onMessage?.(`${successCount} added, ${failCount} failed`, 'warning');
    }
  };

  // Format value for display
  const formatValue = (value) => {
    if (value === null || value === undefined) return 'null';
    if (typeof value === 'object') return JSON.stringify(value);
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value);
  };

  if (loading && open) {
    return (
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Sync color="info" />
        Sync Configuration with Defaults
        {counts.total > 0 && (
          <Chip
            label={`${counts.total} items`}
            color="info"
            size="small"
            sx={{ ml: 1 }}
          />
        )}
      </DialogTitle>

      <DialogContent dividers>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            Error loading sync data: {error}
          </Alert>
        )}

        {counts.total === 0 ? (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
            <Typography variant="h6" color="text.secondary">
              Configuration is in sync
            </Typography>
            <Typography variant="body2" color="text.disabled">
              No new parameters or changes detected
            </Typography>
          </Box>
        ) : (
          <>
            {/* Tabs */}
            <Tabs
              value={tabIndex}
              onChange={(e, newVal) => setTabIndex(newVal)}
              variant="fullWidth"
              sx={{ mb: 2 }}
            >
              <Tab
                label={
                  <Badge badgeContent={counts.new} color="success" max={99}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pr: 1 }}>
                      <Add fontSize="small" />
                      New
                    </Box>
                  </Badge>
                }
                disabled={counts.new === 0}
              />
              <Tab
                label={
                  <Badge badgeContent={counts.changed} color="warning" max={99}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pr: 1 }}>
                      <Edit fontSize="small" />
                      Changed
                    </Box>
                  </Badge>
                }
                disabled={counts.changed === 0}
              />
              <Tab
                label={
                  <Badge badgeContent={counts.removed} color="error" max={99}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, pr: 1 }}>
                      <Delete fontSize="small" />
                      Obsolete
                    </Box>
                  </Badge>
                }
                disabled={counts.removed === 0}
              />
            </Tabs>

            {/* New Parameters Tab */}
            <TabPanel value={tabIndex} index={0}>
              {counts.new === 0 ? (
                <Typography color="text.secondary">No new parameters</Typography>
              ) : (
                <>
                  <Alert severity="info" sx={{ mb: 2 }}>
                    {counts.new} new parameter{counts.new > 1 ? 's' : ''} available.
                    Select which ones to add to your configuration.
                  </Alert>

                  <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                    <Button size="small" onClick={selectAllNew}>Select All</Button>
                    <Button size="small" onClick={selectNone}>Select None</Button>
                    <Chip
                      label={`${selectedNew.size} selected`}
                      size="small"
                      color={selectedNew.size > 0 ? 'primary' : 'default'}
                    />
                  </Box>

                  <List dense>
                    {Object.entries(groupedNewParams).map(([section, params]) => {
                      const isExpanded = expandedSections[section] !== false;
                      const sectionSelected = params.every(
                        p => selectedNew.has(`${p.section}.${p.parameter}`)
                      );

                      return (
                        <React.Fragment key={section}>
                          <ListItem
                            button
                            onClick={() => toggleSection(section)}
                            sx={{ bgcolor: 'action.hover', borderRadius: 1, mb: 0.5 }}
                          >
                            <ListItemIcon>
                              <Checkbox
                                checked={sectionSelected}
                                indeterminate={
                                  !sectionSelected && params.some(
                                    p => selectedNew.has(`${p.section}.${p.parameter}`)
                                  )
                                }
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (sectionSelected) {
                                    // Deselect all in section
                                    setSelectedNew(prev => {
                                      const newSet = new Set(prev);
                                      params.forEach(p => newSet.delete(`${p.section}.${p.parameter}`));
                                      return newSet;
                                    });
                                  } else {
                                    // Select all in section
                                    setSelectedNew(prev => {
                                      const newSet = new Set(prev);
                                      params.forEach(p => newSet.add(`${p.section}.${p.parameter}`));
                                      return newSet;
                                    });
                                  }
                                }}
                                size="small"
                              />
                            </ListItemIcon>
                            <ListItemText
                              primary={section}
                              secondary={`${params.length} new parameter${params.length > 1 ? 's' : ''}`}
                            />
                            {isExpanded ? <ExpandLess /> : <ExpandMore />}
                          </ListItem>

                          <Collapse in={isExpanded}>
                            <List dense sx={{ pl: 4 }}>
                              {params.map(param => (
                                <ListItem
                                  key={`${param.section}.${param.parameter}`}
                                  button
                                  onClick={() => toggleSelection(param.section, param.parameter)}
                                >
                                  <ListItemIcon>
                                    <Checkbox
                                      checked={selectedNew.has(`${param.section}.${param.parameter}`)}
                                      size="small"
                                    />
                                  </ListItemIcon>
                                  <ListItemText
                                    primary={
                                      <Typography variant="body2" fontFamily="monospace">
                                        {param.parameter}
                                      </Typography>
                                    }
                                    secondary={
                                      <Box>
                                        <Typography variant="caption" color="text.secondary">
                                          {param.description}
                                        </Typography>
                                        <Box sx={{ mt: 0.5 }}>
                                          <Chip
                                            label={`Default: ${formatValue(param.default_value)}`}
                                            size="small"
                                            variant="outlined"
                                          />
                                          <Chip
                                            label={param.type}
                                            size="small"
                                            variant="outlined"
                                            sx={{ ml: 0.5 }}
                                          />
                                        </Box>
                                      </Box>
                                    }
                                  />
                                </ListItem>
                              ))}
                            </List>
                          </Collapse>
                        </React.Fragment>
                      );
                    })}
                  </List>
                </>
              )}
            </TabPanel>

            {/* Changed Defaults Tab */}
            <TabPanel value={tabIndex} index={1}>
              {counts.changed === 0 ? (
                <Typography color="text.secondary">No changed defaults</Typography>
              ) : (
                <Alert severity="warning">
                  Changed defaults feature coming in a future update.
                </Alert>
              )}
            </TabPanel>

            {/* Obsolete Parameters Tab */}
            <TabPanel value={tabIndex} index={2}>
              {counts.removed === 0 ? (
                <Typography color="text.secondary">No obsolete parameters</Typography>
              ) : (
                <>
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    {counts.removed} parameter{counts.removed > 1 ? 's' : ''} in your config
                    {counts.removed > 1 ? ' are' : ' is'} no longer in the schema.
                  </Alert>
                  <List dense>
                    {removedParameters.map(param => (
                      <ListItem key={`${param.section}.${param.parameter}`}>
                        <ListItemIcon>
                          <Warning color="warning" />
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Typography variant="body2" fontFamily="monospace">
                              {param.section}.{param.parameter}
                            </Typography>
                          }
                          secondary={`Current value: ${formatValue(param.current_value)}`}
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}
            </TabPanel>
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={refresh} disabled={loading}>
          Refresh
        </Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose}>
          Close
        </Button>
        {tabIndex === 0 && counts.new > 0 && (
          <>
            <Button
              variant="outlined"
              onClick={applySelected}
              disabled={applying || selectedNew.size === 0}
              startIcon={applying ? <CircularProgress size={16} /> : <Add />}
            >
              Add Selected ({selectedNew.size})
            </Button>
            <Button
              variant="contained"
              onClick={handleApplyAllNew}
              disabled={applying}
              startIcon={applying ? <CircularProgress size={16} /> : <Add />}
            >
              Add All New
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};

SyncWithDefaultsDialog.propTypes = {
  /** Whether the dialog is open */
  open: PropTypes.bool.isRequired,
  /** Callback when dialog closes */
  onClose: PropTypes.func.isRequired,
  /** Callback for toast messages */
  onMessage: PropTypes.func,
};

export default SyncWithDefaultsDialog;
