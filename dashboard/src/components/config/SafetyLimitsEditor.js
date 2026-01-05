// dashboard/src/components/config/SafetyLimitsEditor.js
/**
 * SafetyLimitsEditor - Specialized editor for Safety configuration
 *
 * Provides a unified, schema-driven interface for editing:
 * - GlobalLimits: Default safety limits for all followers
 * - FollowerOverrides: Per-follower limit overrides
 *
 * Features:
 * - Schema-driven property suggestions
 * - Follower selector for overrides
 * - Add/Edit/Remove properties
 * - Visual comparison with GlobalLimits
 * - Instructional guides
 */
import React, { useState, useMemo, useCallback } from 'react';
import {
  Box, Typography, Paper, Alert, Chip,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, IconButton, Tooltip, Button, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select, MenuItem, ListSubheader,
  InputAdornment, Slider
} from '@mui/material';
import {
  Add, Delete, Info, Speed, Height, RotateRight,
  FlightTakeoff, CameraAlt, Flight, Warning
} from '@mui/icons-material';

import {
  PROPERTY_CATEGORIES,
  FOLLOWER_TYPES,
  getAddableProperties,
  getPropertyByName,
  getFollowersByType
} from '../../utils/safetySchemaUtils';

// Category icons mapping
const categoryIcons = {
  altitude: <Height fontSize="small" color="success" />,
  velocity: <Speed fontSize="small" color="primary" />,
  rates: <RotateRight fontSize="small" color="warning" />
};

// Follower type icons
const followerTypeIcons = {
  multicopter: <FlightTakeoff fontSize="small" />,
  gimbal: <CameraAlt fontSize="small" />,
  fixed_wing: <Flight fontSize="small" />
};

/**
 * Single property row with inline editing
 */
const PropertyRow = ({
  propertyName,
  value,
  globalValue,
  onChange,
  onRemove,
  showComparison,
  disabled
}) => {
  const propMeta = getPropertyByName(propertyName);
  const [localValue, setLocalValue] = useState(value);
  const [isFocused, setIsFocused] = useState(false);

  const handleBlur = () => {
    setIsFocused(false);
    if (localValue !== value) {
      onChange(propertyName, localValue);
    }
  };

  const handleSliderChange = (_, newValue) => {
    setLocalValue(newValue);
    onChange(propertyName, newValue);
  };

  // For boolean type
  if (propMeta?.type === 'boolean') {
    return (
      <TableRow hover>
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {categoryIcons[propMeta?.category]}
            <Box>
              <Typography variant="body2" fontWeight="medium">
                {propertyName}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {propMeta?.description}
              </Typography>
            </Box>
          </Box>
        </TableCell>
        <TableCell>
          <Switch
            checked={Boolean(value)}
            onChange={(e) => onChange(propertyName, e.target.checked)}
            disabled={disabled}
            size="small"
          />
        </TableCell>
        {showComparison && (
          <TableCell>
            <Chip
              label={globalValue !== undefined ? (globalValue ? 'ON' : 'OFF') : 'N/A'}
              size="small"
              variant="outlined"
              color={globalValue ? 'success' : 'default'}
            />
          </TableCell>
        )}
        <TableCell align="right">
          <Tooltip title="Remove this override">
            <IconButton size="small" onClick={() => onRemove(propertyName)} disabled={disabled}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        </TableCell>
      </TableRow>
    );
  }

  // For number type
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 100;
  const step = propMeta?.step ?? 0.1;

  return (
    <TableRow hover>
      <TableCell>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {categoryIcons[propMeta?.category]}
          <Box>
            <Typography variant="body2" fontWeight="medium">
              {propertyName}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {propMeta?.description}
            </Typography>
          </Box>
        </Box>
      </TableCell>
      <TableCell>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 200 }}>
          <TextField
            size="small"
            type="number"
            value={isFocused ? localValue : value}
            onChange={(e) => setLocalValue(parseFloat(e.target.value) || 0)}
            onFocus={() => { setIsFocused(true); setLocalValue(value); }}
            onBlur={handleBlur}
            disabled={disabled}
            inputProps={{ min, max, step }}
            sx={{ width: 100 }}
            InputProps={{
              endAdornment: propMeta?.unit && (
                <InputAdornment position="end">
                  <Typography variant="caption" color="text.secondary">
                    {propMeta.unit}
                  </Typography>
                </InputAdornment>
              )
            }}
          />
          <Slider
            size="small"
            value={typeof value === 'number' ? value : 0}
            onChange={handleSliderChange}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            sx={{ flex: 1, minWidth: 80 }}
          />
        </Box>
      </TableCell>
      {showComparison && (
        <TableCell>
          <Chip
            label={globalValue !== undefined ? `${globalValue} ${propMeta?.unit || ''}` : 'N/A'}
            size="small"
            variant="outlined"
          />
        </TableCell>
      )}
      <TableCell align="right">
        <Tooltip title="Remove this override">
          <IconButton size="small" onClick={() => onRemove(propertyName)} disabled={disabled}>
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
      </TableCell>
    </TableRow>
  );
};

/**
 * Add Property Dialog
 */
const AddPropertyDialog = ({
  open,
  onClose,
  onAdd,
  existingProperties,
  globalLimits,
  showComparison
}) => {
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');

  const addableProperties = useMemo(() =>
    getAddableProperties(existingProperties),
    [existingProperties]
  );

  // Group by category
  const groupedProperties = useMemo(() => {
    const groups = {};
    addableProperties.forEach(prop => {
      if (!groups[prop.category]) {
        groups[prop.category] = [];
      }
      groups[prop.category].push(prop);
    });
    return groups;
  }, [addableProperties]);

  const selectedMeta = selectedProperty ? getPropertyByName(selectedProperty) : null;

  const handleAdd = () => {
    if (selectedProperty && propertyValue !== '') {
      const value = selectedMeta?.type === 'boolean'
        ? propertyValue === 'true'
        : parseFloat(propertyValue);
      onAdd(selectedProperty, value);
      setSelectedProperty('');
      setPropertyValue('');
      onClose();
    }
  };

  const handlePropertySelect = (propName) => {
    setSelectedProperty(propName);
    const meta = getPropertyByName(propName);
    // Set default value
    const defaultVal = globalLimits?.[propName] ?? meta?.default ?? 0;
    setPropertyValue(String(defaultVal));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Safety Limit Property</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>
          Select a property to add. Values are validated against schema constraints.
        </Alert>

        <FormControl fullWidth sx={{ mb: 2 }}>
          <InputLabel>Property</InputLabel>
          <Select
            value={selectedProperty}
            onChange={(e) => handlePropertySelect(e.target.value)}
            label="Property"
          >
            {Object.entries(groupedProperties).map(([category, props]) => [
              <ListSubheader key={`header-${category}`}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {categoryIcons[category]}
                  {PROPERTY_CATEGORIES[category]?.label || category}
                </Box>
              </ListSubheader>,
              ...props.map(prop => (
                <MenuItem key={prop.name} value={prop.name}>
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <Typography variant="body2">{prop.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {prop.description} ({prop.unit || prop.type})
                    </Typography>
                  </Box>
                </MenuItem>
              ))
            ])}
          </Select>
        </FormControl>

        {selectedMeta && (
          <Box>
            {selectedMeta.type === 'boolean' ? (
              <FormControl fullWidth>
                <InputLabel>Value</InputLabel>
                <Select
                  value={propertyValue}
                  onChange={(e) => setPropertyValue(e.target.value)}
                  label="Value"
                >
                  <MenuItem value="true">Enabled (ON)</MenuItem>
                  <MenuItem value="false">Disabled (OFF)</MenuItem>
                </Select>
              </FormControl>
            ) : (
              <TextField
                fullWidth
                label="Value"
                type="number"
                value={propertyValue}
                onChange={(e) => setPropertyValue(e.target.value)}
                inputProps={{
                  min: selectedMeta.min,
                  max: selectedMeta.max,
                  step: selectedMeta.step
                }}
                helperText={
                  showComparison && globalLimits?.[selectedProperty] !== undefined
                    ? `Global: ${globalLimits[selectedProperty]} ${selectedMeta.unit || ''}`
                    : `Range: ${selectedMeta.min} - ${selectedMeta.max} ${selectedMeta.unit || ''}`
                }
              />
            )}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          onClick={handleAdd}
          variant="contained"
          disabled={!selectedProperty || propertyValue === ''}
        >
          Add Property
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/**
 * Main SafetyLimitsEditor Component
 */
const SafetyLimitsEditor = ({
  type,                    // 'GlobalLimits' | 'FollowerOverrides'
  value,                   // Current object value
  onChange,                // Callback for changes
  globalLimits = {},       // Reference for comparison (FollowerOverrides only)
  disabled = false
}) => {
  const isOverrides = type === 'FollowerOverrides';
  const [selectedFollower, setSelectedFollower] = useState('');
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  // Get followers grouped by type
  const followersByType = useMemo(() => getFollowersByType(), []);

  // Get current properties being edited
  const currentProperties = useMemo(() => {
    if (isOverrides) {
      return selectedFollower ? (value?.[selectedFollower] || {}) : {};
    }
    return value || {};
  }, [isOverrides, selectedFollower, value]);

  // Count overrides per follower
  const followerOverrideCounts = useMemo(() => {
    if (!isOverrides || !value) return {};
    const counts = {};
    Object.entries(value).forEach(([follower, props]) => {
      counts[follower] = Object.keys(props || {}).length;
    });
    return counts;
  }, [isOverrides, value]);

  const handlePropertyChange = useCallback((propName, newValue) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(value?.[selectedFollower] || {}), [propName]: newValue };
      onChange({ ...value, [selectedFollower]: followerProps });
    } else {
      onChange({ ...value, [propName]: newValue });
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handlePropertyRemove = useCallback((propName) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(value?.[selectedFollower] || {}) };
      delete followerProps[propName];
      // If no props left, remove the follower entry
      if (Object.keys(followerProps).length === 0) {
        const newValue = { ...value };
        delete newValue[selectedFollower];
        onChange(newValue);
      } else {
        onChange({ ...value, [selectedFollower]: followerProps });
      }
    } else {
      const newValue = { ...value };
      delete newValue[propName];
      onChange(newValue);
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handlePropertyAdd = useCallback((propName, propValue) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(value?.[selectedFollower] || {}), [propName]: propValue };
      onChange({ ...value, [selectedFollower]: followerProps });
    } else {
      onChange({ ...value, [propName]: propValue });
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handleRemoveFollower = useCallback(() => {
    if (!selectedFollower || !isOverrides) return;
    const newValue = { ...value };
    delete newValue[selectedFollower];
    onChange(newValue);
    setSelectedFollower('');
  }, [selectedFollower, isOverrides, value, onChange]);

  const propertyEntries = Object.entries(currentProperties);
  const hasProperties = propertyEntries.length > 0;

  return (
    <Box>
      {/* Instructions */}
      <Alert severity="info" sx={{ mb: 2 }} icon={<Info />}>
        {isOverrides ? (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              Per-Follower Safety Overrides
            </Typography>
            <Typography variant="caption">
              Override specific limits for individual followers. Empty = uses GlobalLimits.
              This is an advanced feature for specialized configurations.
            </Typography>
          </Box>
        ) : (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              Global Safety Limits
            </Typography>
            <Typography variant="caption">
              Set default safety limits applied to all followers. These are the single source
              of truth for safety-critical parameters.
            </Typography>
          </Box>
        )}
      </Alert>

      {/* Follower Selector (FollowerOverrides only) */}
      {isOverrides && (
        <Box sx={{ mb: 3 }}>
          <FormControl fullWidth>
            <InputLabel>Select Follower to Configure</InputLabel>
            <Select
              value={selectedFollower}
              onChange={(e) => setSelectedFollower(e.target.value)}
              label="Select Follower to Configure"
            >
              <MenuItem value="">
                <em>-- Select Follower --</em>
              </MenuItem>
              {Object.entries(followersByType).map(([type, followers]) => [
                <ListSubheader key={`type-${type}`}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {followerTypeIcons[type]}
                    {FOLLOWER_TYPES[type]?.label || type}
                  </Box>
                </ListSubheader>,
                ...followers.map(f => (
                  <MenuItem key={f.name} value={f.name}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                      <Box>
                        <Typography variant="body2">{f.label}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {f.description}
                        </Typography>
                      </Box>
                      {followerOverrideCounts[f.name] > 0 && (
                        <Chip
                          size="small"
                          label={`${followerOverrideCounts[f.name]} overrides`}
                          color="warning"
                          sx={{ ml: 1 }}
                        />
                      )}
                    </Box>
                  </MenuItem>
                ))
              ])}
            </Select>
          </FormControl>

          {/* Summary of all overrides */}
          {Object.keys(followerOverrideCounts).length > 0 && (
            <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              <Typography variant="caption" color="text.secondary" sx={{ mr: 1 }}>
                Configured:
              </Typography>
              {Object.entries(followerOverrideCounts).map(([follower, count]) => (
                <Chip
                  key={follower}
                  label={`${follower.replace(/_/g, ' ')} (${count})`}
                  size="small"
                  variant={selectedFollower === follower ? 'filled' : 'outlined'}
                  color={selectedFollower === follower ? 'primary' : 'default'}
                  onClick={() => setSelectedFollower(follower)}
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Box>
          )}
        </Box>
      )}

      {/* Properties Table */}
      {(isOverrides && !selectedFollower) ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Warning sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary">
            Select a follower above to configure overrides
          </Typography>
          <Typography variant="caption" color="text.disabled">
            Or the FollowerOverrides section is empty (using GlobalLimits for all)
          </Typography>
        </Paper>
      ) : (
        <Box>
          {hasProperties ? (
            <Paper variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Property</TableCell>
                    <TableCell>Value</TableCell>
                    {isOverrides && <TableCell>Global Value</TableCell>}
                    <TableCell align="right" width={80}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {propertyEntries.map(([propName, propValue]) => (
                    <PropertyRow
                      key={propName}
                      propertyName={propName}
                      value={propValue}
                      globalValue={globalLimits?.[propName]}
                      onChange={handlePropertyChange}
                      onRemove={handlePropertyRemove}
                      showComparison={isOverrides}
                      disabled={disabled}
                    />
                  ))}
                </TableBody>
              </Table>
            </Paper>
          ) : (
            <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                {isOverrides
                  ? 'No overrides configured for this follower.'
                  : 'No properties configured.'}
              </Typography>
              <Typography variant="caption" color="text.disabled">
                Click "Add Property" below to add limits.
              </Typography>
            </Paper>
          )}

          {/* Action Buttons */}
          <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start' }}>
            <Button
              variant="outlined"
              startIcon={<Add />}
              onClick={() => setAddDialogOpen(true)}
              disabled={disabled || (isOverrides && !selectedFollower)}
            >
              Add Property
            </Button>

            {isOverrides && selectedFollower && hasProperties && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<Delete />}
                onClick={handleRemoveFollower}
                disabled={disabled}
              >
                Remove All Overrides
              </Button>
            )}
          </Box>
        </Box>
      )}

      {/* Add Property Dialog */}
      <AddPropertyDialog
        open={addDialogOpen}
        onClose={() => setAddDialogOpen(false)}
        onAdd={handlePropertyAdd}
        existingProperties={currentProperties}
        globalLimits={globalLimits}
        showComparison={isOverrides}
      />
    </Box>
  );
};

export default SafetyLimitsEditor;
