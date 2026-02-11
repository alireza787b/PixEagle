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
  InputAdornment, Slider, Card, CardContent
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
import { clampNumericValue, parseCommittedNumeric } from '../../utils/numericInput';
import { useResponsive } from '../../hooks/useResponsive';

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
  const [localValue, setLocalValue] = useState(() => String(value ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  const handleSliderChange = (_, newValue) => {
    onChange(propertyName, newValue);
  };

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? ''));
    }
  }, [value, isFocused]);

  // For number type (or unknown custom properties)
  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

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
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            onFocus={() => {
              setIsFocused(true);
              setLocalValue(String(value ?? ''));
            }}
            onBlur={() => {
              setIsFocused(false);
              const parsed = parseCommittedNumeric(localValue, 'float');
              if (!parsed.valid) {
                setLocalValue(String(value ?? ''));
                return;
              }
              const boundedValue = clampNumericValue(parsed.value, min, max);
              setLocalValue(String(boundedValue));
              if (boundedValue !== value) {
                onChange(propertyName, boundedValue);
              }
            }}
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
            onChange={(_, newValue) => {
              handleSliderChange(_, newValue);
              setLocalValue(String(newValue));
            }}
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
 * Property Card for mobile/tablet view
 * Touch-friendly card layout with full-width inputs
 */
const PropertyCard = ({
  propertyName,
  value,
  globalValue,
  onChange,
  onRemove,
  showComparison,
  disabled
}) => {
  const propMeta = getPropertyByName(propertyName);
  const [localValue, setLocalValue] = useState(() => String(value ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  const handleSliderChange = (_, newValue) => {
    onChange(propertyName, newValue);
  };

  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? ''));
    }
  }, [value, isFocused]);

  return (
    <Card variant="outlined" sx={{ mb: 2 }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        {/* Header: Property name with icon */}
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
            {isCustomProperty ? <Edit fontSize="small" color="action" /> : categoryIcons[propMeta?.category]}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                <Typography variant="body2" fontWeight="medium">
                  {propertyName}
                </Typography>
                {isCustomProperty && (
                  <Chip label="Custom" size="small" variant="outlined" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {isCustomProperty ? 'Custom property' : propMeta?.description}
              </Typography>
            </Box>
          </Box>
          <IconButton size="small" onClick={() => onRemove(propertyName)} disabled={disabled} color="error">
            <Delete fontSize="small" />
          </IconButton>
        </Box>

        {/* Value editor */}
        {propMeta?.type === 'boolean' ? (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="body2">Enabled</Typography>
            <Switch
              checked={Boolean(value)}
              onChange={(e) => onChange(propertyName, e.target.checked)}
              disabled={disabled}
            />
          </Box>
        ) : (
          <Box>
            <TextField
              fullWidth
              size="small"
              type="number"
              label="Value"
              value={localValue}
              onChange={(e) => setLocalValue(e.target.value)}
              onFocus={() => {
                setIsFocused(true);
                setLocalValue(String(value ?? ''));
              }}
              onBlur={() => {
                setIsFocused(false);
                const parsed = parseCommittedNumeric(localValue, 'float');
                if (!parsed.valid) {
                  setLocalValue(String(value ?? ''));
                  return;
                }
                const boundedValue = clampNumericValue(parsed.value, min, max);
                setLocalValue(String(boundedValue));
                if (boundedValue !== value) {
                  onChange(propertyName, boundedValue);
                }
              }}
              disabled={disabled}
              inputProps={{ min, max, step }}
              InputProps={{
                endAdornment: propMeta?.unit && (
                  <InputAdornment position="end">
                    <Typography variant="caption" color="text.secondary">
                      {propMeta.unit}
                    </Typography>
                  </InputAdornment>
                )
              }}
              sx={{ mb: 1 }}
            />
            <Slider
              size="small"
              value={typeof value === 'number' ? value : 0}
              onChange={(_, newValue) => {
                handleSliderChange(_, newValue);
                setLocalValue(String(newValue));
              }}
              min={min}
              max={max}
              step={step}
              disabled={disabled}
              valueLabelDisplay="auto"
            />
          </Box>
        )}

        {/* Global comparison */}
        {showComparison && globalValue !== undefined && (
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              Global: {propMeta?.type === 'boolean' ? (globalValue ? 'ON' : 'OFF') : `${globalValue} ${propMeta?.unit || ''}`}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

/**
 * Add Property Dialog
 *
 * Features:
 * - For GlobalLimits: Shows property selector only
 * - For FollowerOverrides: Shows follower selector FIRST, then property selector
 * - Custom property option for advanced users
 */
const AddPropertyDialog = ({
  open,
  onClose,
  onAdd,
  existingProperties,
  globalLimits,
  showComparison,
  isOverrides = false,
  selectedFollower = '',
  onFollowerChange,
  followersByType = {}
}) => {
  // State for dialog
  const [dialogFollower, setDialogFollower] = useState(selectedFollower || '');
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [customPropertyName, setCustomPropertyName] = useState('');

  // Compute addable properties based on existing ones
  const addableProperties = useMemo(() =>
    getAddableProperties(existingProperties || {}),
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

  const selectedMeta = selectedProperty && !isCustomMode ? getPropertyByName(selectedProperty) : null;

  const handleAdd = () => {
    const propName = isCustomMode ? customPropertyName.trim() : selectedProperty;
    const effectiveFollower = isOverrides ? dialogFollower : null;

    if (propName && propertyValue !== '' && (!isOverrides || effectiveFollower)) {
      let value;
      if (selectedMeta?.type === 'boolean') {
        value = propertyValue === 'true';
      } else {
        const parsed = parseCommittedNumeric(propertyValue, 'float');
        if (!parsed.valid) return;
        value = clampNumericValue(parsed.value, selectedMeta?.min, selectedMeta?.max);
      }

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

  // Get list of followers for selector
  const followerList = useMemo(() => {
    const list = [];
    Object.entries(followersByType || {}).forEach(([type, followers]) => {
      if (followers && followers.length > 0) {
        list.push({ type, followers });
      }
    });
    return list;
  }, [followersByType]);

  // Determine if we can show property selector
  const showPropertySelector = !isOverrides || dialogFollower;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {isOverrides ? 'Add Follower Override Property' : 'Add Safety Limit Property'}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 1 }}>
          {/* Step 1: Follower selector for FollowerOverrides mode */}
          {isOverrides && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                Step 1: Select Follower
              </Typography>
              <FormControl fullWidth>
                <InputLabel id="dialog-follower-select">Follower</InputLabel>
                <Select
                  labelId="dialog-follower-select"
                  value={dialogFollower}
                  onChange={(e) => setDialogFollower(e.target.value)}
                  label="Follower"
                >
                  <MenuItem value="">
                    <em>-- Select a follower --</em>
                  </MenuItem>
                  {followerList.map(({ type, followers }) => [
                    <ListSubheader key={`header-${type}`}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {followerTypeIcons[type]}
                        <span>{FOLLOWER_TYPES[type]?.label || type}</span>
                      </Box>
                    </ListSubheader>,
                    ...followers.map(f => (
                      <MenuItem key={f.name} value={f.name}>
                        <Box>
                          <Typography variant="body2">{f.label || f.name}</Typography>
                          {f.description && (
                            <Typography variant="caption" color="text.secondary">
                              {f.description}
                            </Typography>
                          )}
                        </Box>
                      </MenuItem>
                    ))
                  ])}
                </Select>
              </FormControl>
              {!dialogFollower && (
                <Alert severity="info" sx={{ mt: 1 }} icon={<Info />}>
                  Select a follower to add override properties
                </Alert>
              )}
            </Box>
          )}

          {/* Step 2 (or Step 1 for GlobalLimits): Property selector */}
          {showPropertySelector && (
            <Box>
              {isOverrides && (
                <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                  Step 2: Select Property
                </Typography>
              )}

              {isCustomMode ? (
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
              ) : (
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
              )}
            </Box>
          )}
        </Box>
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

  // Responsive: use card layout on mobile/tablet for better UX
  const { isMobile, isTablet } = useResponsive();
  const useCardLayout = isMobile || isTablet;

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

      {/* Properties Display - Responsive Card/Table Layout */}
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
            useCardLayout ? (
              // Mobile/Tablet: Card layout for touch-friendly interaction
              <Box>
                {propertyEntries.map(([propName, propValue]) => (
                  <PropertyCard
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
              </Box>
            ) : (
              // Desktop: Table layout with more information density
              <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
                <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: isOverrides ? '30%' : '40%' }}>Property</TableCell>
                      <TableCell sx={{ width: isOverrides ? '25%' : '35%' }}>Value</TableCell>
                      {isOverrides && <TableCell sx={{ width: '25%' }}>Global Value</TableCell>}
                      <TableCell align="right" sx={{ width: isOverrides ? '20%' : '25%', whiteSpace: 'nowrap' }}>Actions</TableCell>
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
            )
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
          <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start', flexWrap: 'wrap' }}>
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
