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
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  Box, Typography, Paper, Alert, Chip, Divider,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, IconButton, Tooltip, Button, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, InputLabel, Select, MenuItem, ListSubheader,
  InputAdornment, Slider
} from '@mui/material';
import {
  Add, Delete, Info, Speed, Height, RotateRight,
  FlightTakeoff, CameraAlt, Flight, Warning, Edit
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

  // For number type (or unknown custom properties)
  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

  return (
    <TableRow hover>
      <TableCell>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {isCustomProperty ? <Edit fontSize="small" color="action" /> : categoryIcons[propMeta?.category]}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Typography variant="body2" fontWeight="medium">
                {propertyName}
              </Typography>
              {isCustomProperty && (
                <Chip label="Custom" size="small" variant="outlined" color="default" sx={{ height: 16, fontSize: '0.6rem' }} />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary">
              {isCustomProperty ? 'Custom property (not validated)' : propMeta?.description}
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
 *
 * Enhanced with:
 * - Follower selector for FollowerOverrides mode
 * - State reset on open to fix loading issues
 */
const AddPropertyDialog = ({
  open,
  onClose,
  onAdd,
  existingProperties,
  globalLimits,
  showComparison,
  // FollowerOverrides support
  isOverrides = false,
  selectedFollower = '',
  onFollowerChange,
  followersByType = {}
}) => {
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [customPropertyName, setCustomPropertyName] = useState('');
  const [dialogFollower, setDialogFollower] = useState('');

  // Reset state when dialog opens to fix loading issues
  useEffect(() => {
    if (open) {
      setSelectedProperty('');
      setPropertyValue('');
      setIsCustomMode(false);
      setCustomPropertyName('');
      setDialogFollower(selectedFollower || '');
    }
  }, [open, selectedFollower]);

  const addableProperties = useMemo(() =>
    getAddableProperties(existingProperties),
    [existingProperties, open]  // Added open to ensure recalculation when dialog opens
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

  const selectedMeta = selectedProperty && !isCustomMode ? getPropertyByName(selectedProperty) : null;

  const handleAdd = () => {
    const propName = isCustomMode ? customPropertyName.trim() : selectedProperty;
    const effectiveFollower = isOverrides ? dialogFollower : null;

    if (propName && propertyValue !== '' && (!isOverrides || effectiveFollower)) {
      const value = selectedMeta?.type === 'boolean'
        ? propertyValue === 'true'
        : parseFloat(propertyValue);

      // If follower changed in dialog, notify parent
      if (isOverrides && onFollowerChange && effectiveFollower !== selectedFollower) {
        onFollowerChange(effectiveFollower);
      }

      onAdd(propName, value, effectiveFollower);
      // Reset state
      setSelectedProperty('');
      setPropertyValue('');
      setIsCustomMode(false);
      setCustomPropertyName('');
      setDialogFollower('');
      onClose();
    }
  };

  const handlePropertySelect = (propName) => {
    if (propName === '__custom__') {
      setIsCustomMode(true);
      setSelectedProperty('');
      setPropertyValue('0');
    } else {
      setIsCustomMode(false);
      setSelectedProperty(propName);
      const meta = getPropertyByName(propName);
      // Set default value
      const defaultVal = globalLimits?.[propName] ?? meta?.default ?? 0;
      setPropertyValue(String(defaultVal));
    }
  };

  const handleClose = () => {
    setSelectedProperty('');
    setPropertyValue('');
    setIsCustomMode(false);
    setCustomPropertyName('');
    onClose();
  };

  // Check if custom property name is valid (not empty, not already exists)
  const isCustomNameValid = customPropertyName.trim() &&
    !existingProperties?.[customPropertyName.trim()] &&
    /^[A-Z][A-Z0-9_]*$/.test(customPropertyName.trim());

  // For FollowerOverrides mode, require follower selection
  const hasFollower = !isOverrides || dialogFollower;

  const canAdd = hasFollower && (isCustomMode
    ? (isCustomNameValid && propertyValue !== '')
    : (selectedProperty && propertyValue !== ''));

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {isOverrides ? 'Add Follower Override Property' : 'Add Safety Limit Property'}
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        {/* Follower selector for FollowerOverrides mode */}
        {isOverrides && (
          <FormControl fullWidth sx={{ mb: 2, mt: 1 }}>
            <InputLabel id="follower-select-label">Select Follower</InputLabel>
            <Select
              labelId="follower-select-label"
              value={dialogFollower}
              onChange={(e) => setDialogFollower(e.target.value)}
              label="Select Follower"
              displayEmpty
            >
              <MenuItem value="">
                <em>-- Select Follower --</em>
              </MenuItem>
              {Object.entries(followersByType || {}).map(([type, followers]) => [
                <ListSubheader key={`type-${type}`}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {followerTypeIcons[type]}
                    {FOLLOWER_TYPES[type]?.label || type}
                  </Box>
                </ListSubheader>,
                ...(followers || []).map(f => (
                  <MenuItem key={f.name} value={f.name}>
                    <Box>
                      <Typography variant="body2">{f.label}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {f.description}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))
              ])}
            </Select>
          </FormControl>
        )}

        <Alert severity="info" sx={{ mb: 2 }}>
          {isOverrides && !dialogFollower
            ? 'First select a follower, then choose a property to override.'
            : isCustomMode
              ? 'Enter a custom property name (UPPER_SNAKE_CASE) and numeric value.'
              : 'Select a property to add, or choose "Enter custom property" for advanced use.'}
        </Alert>

        {/* Only show property selection if follower is selected (for overrides) or not in overrides mode */}
        {(!isOverrides || dialogFollower) && isCustomMode ? (
          // Custom property mode
          <Box>
            <TextField
              fullWidth
              label="Property Name"
              value={customPropertyName}
              onChange={(e) => setCustomPropertyName(e.target.value.toUpperCase())}
              placeholder="MY_CUSTOM_LIMIT"
              helperText={
                customPropertyName && !isCustomNameValid
                  ? 'Use UPPER_SNAKE_CASE (e.g., MY_CUSTOM_LIMIT)'
                  : 'Custom properties are not validated. Use with caution.'
              }
              error={customPropertyName && !isCustomNameValid}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              label="Value"
              type="number"
              value={propertyValue}
              onChange={(e) => setPropertyValue(e.target.value)}
              inputProps={{ step: 0.1 }}
              helperText="Numeric value for this custom property"
            />
            <Button
              size="small"
              onClick={() => {
                setIsCustomMode(false);
                setCustomPropertyName('');
              }}
              sx={{ mt: 1 }}
            >
              ← Back to property list
            </Button>
          </Box>
        ) : (!isOverrides || dialogFollower) ? (
          // Standard property selection
          <>
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
                {/* Custom property option */}
                <Divider />
                <MenuItem value="__custom__">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Edit fontSize="small" color="primary" />
                    <Typography color="primary" fontStyle="italic" variant="body2">
                      Enter custom property...
                    </Typography>
                  </Box>
                </MenuItem>
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
          </>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          onClick={handleAdd}
          variant="contained"
          disabled={!canAdd}
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

  const handlePropertyAdd = useCallback((propName, propValue, followerFromDialog) => {
    if (isOverrides) {
      // Use follower from dialog if provided, otherwise use selected follower
      const targetFollower = followerFromDialog || selectedFollower;
      if (!targetFollower) return;

      // Update the selected follower if dialog specified a different one
      if (followerFromDialog && followerFromDialog !== selectedFollower) {
        setSelectedFollower(followerFromDialog);
      }

      const followerProps = { ...(value?.[targetFollower] || {}), [propName]: propValue };
      onChange({ ...value, [targetFollower]: followerProps });
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
            <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 400 }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 150 }}>Property</TableCell>
                    <TableCell sx={{ minWidth: 120 }}>Value</TableCell>
                    {isOverrides && <TableCell sx={{ minWidth: 100 }}>Global Value</TableCell>}
                    <TableCell align="right" sx={{ minWidth: 80, whiteSpace: 'nowrap' }}>Actions</TableCell>
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
              disabled={disabled}
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

      {/* Add Property Dialog - conditionally rendered to ensure fresh mount each time */}
      {addDialogOpen && (
        <AddPropertyDialog
          open={addDialogOpen}
          onClose={() => setAddDialogOpen(false)}
          onAdd={handlePropertyAdd}
          existingProperties={currentProperties}
          globalLimits={globalLimits}
          showComparison={isOverrides}
          isOverrides={isOverrides}
          selectedFollower={selectedFollower}
          onFollowerChange={setSelectedFollower}
          followersByType={followersByType}
        />
      )}
    </Box>
  );
};

export default SafetyLimitsEditor;
