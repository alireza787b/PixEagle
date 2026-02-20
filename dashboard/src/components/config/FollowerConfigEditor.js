// dashboard/src/components/config/FollowerConfigEditor.js
/**
 * FollowerConfigEditor - Specialized editor for Follower operational config
 *
 * Provides a unified, schema-driven interface for editing:
 * - General: Default operational params for all followers
 * - FollowerOverrides: Per-follower operational overrides
 *
 * Mirrors SafetyLimitsEditor pattern exactly for UI consistency.
 *
 * Features:
 * - Schema-driven property suggestions
 * - Follower selector for overrides
 * - Add/Edit/Remove properties
 * - Visual comparison with General defaults
 * - Enum and boolean type support
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
  Add, Delete, Info, Speed, Height, Tune,
  GpsOff, Navigation, FlightTakeoff, CameraAlt, Flight,
  Warning, Edit
} from '@mui/icons-material';

import {
  PROPERTY_CATEGORIES,
  getAddableProperties,
  getPropertyByName,
  getFollowersByType
} from '../../utils/followerConfigSchemaUtils';
import { FOLLOWER_TYPES } from '../../utils/safetySchemaUtils';
import { clampNumericValue, parseCommittedNumeric } from '../../utils/numericInput';
import { useResponsive } from '../../hooks/useResponsive';

// Category icons mapping
const categoryIcons = {
  timing: <Speed fontSize="small" color="primary" />,
  smoothing: <Tune fontSize="small" color="info" />,
  target_loss: <GpsOff fontSize="small" color="error" />,
  guidance: <Navigation fontSize="small" color="warning" />,
  altitude: <Height fontSize="small" color="success" />
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
  generalValue,
  onChange,
  onRemove,
  showComparison,
  disabled
}) => {
  const propMeta = getPropertyByName(propertyName);
  const [localValue, setLocalValue] = useState(() => String(value ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? ''));
    }
  }, [value, isFocused]);

  // Boolean type
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
              label={generalValue !== undefined ? (generalValue ? 'ON' : 'OFF') : 'N/A'}
              size="small"
              variant="outlined"
              color={generalValue ? 'success' : 'default'}
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

  // Enum type
  if (propMeta?.type === 'enum') {
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
          <Select
            size="small"
            value={value || ''}
            onChange={(e) => onChange(propertyName, e.target.value)}
            disabled={disabled}
            sx={{ minWidth: 160 }}
          >
            {(propMeta.options || []).map(opt => (
              <MenuItem key={opt} value={opt}>{opt}</MenuItem>
            ))}
          </Select>
        </TableCell>
        {showComparison && (
          <TableCell>
            <Chip
              label={generalValue !== undefined ? generalValue : 'N/A'}
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
  }

  // Number type (default)
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
              onChange(propertyName, newValue);
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
            label={generalValue !== undefined ? `${generalValue} ${propMeta?.unit || ''}` : 'N/A'}
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
 */
const PropertyCard = ({
  propertyName,
  value,
  generalValue,
  onChange,
  onRemove,
  showComparison,
  disabled
}) => {
  const propMeta = getPropertyByName(propertyName);
  const [localValue, setLocalValue] = useState(() => String(value ?? ''));
  const [isFocused, setIsFocused] = useState(false);

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
        {/* Header */}
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
        ) : propMeta?.type === 'enum' ? (
          <Select
            fullWidth
            size="small"
            value={value || ''}
            onChange={(e) => onChange(propertyName, e.target.value)}
            disabled={disabled}
          >
            {(propMeta.options || []).map(opt => (
              <MenuItem key={opt} value={opt}>{opt}</MenuItem>
            ))}
          </Select>
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
                onChange(propertyName, newValue);
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

        {/* General comparison */}
        {showComparison && generalValue !== undefined && (
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              General: {propMeta?.type === 'boolean'
                ? (generalValue ? 'ON' : 'OFF')
                : propMeta?.type === 'enum'
                  ? generalValue
                  : `${generalValue} ${propMeta?.unit || ''}`}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
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
  generalDefaults,
  showComparison,
  isOverrides = false,
  selectedFollower = '',
  onFollowerChange,
  followersByType = {}
}) => {
  const [dialogFollower, setDialogFollower] = useState(selectedFollower || '');
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [customPropertyName, setCustomPropertyName] = useState('');

  const addableProperties = useMemo(() =>
    getAddableProperties(existingProperties || {}),
    [existingProperties]
  );

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
      } else if (selectedMeta?.type === 'enum') {
        value = propertyValue;
      } else {
        const parsed = parseCommittedNumeric(propertyValue, 'float');
        if (!parsed.valid) return;
        value = clampNumericValue(parsed.value, selectedMeta?.min, selectedMeta?.max);
      }

      if (isOverrides && onFollowerChange && effectiveFollower !== selectedFollower) {
        onFollowerChange(effectiveFollower);
      }

      onAdd(propName, value, effectiveFollower);
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
      const defaultVal = generalDefaults?.[propName] ?? meta?.default ?? 0;
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

  const isCustomNameValid = customPropertyName.trim() &&
    !existingProperties?.[customPropertyName.trim()] &&
    /^[A-Z][A-Z0-9_]*$/.test(customPropertyName.trim());

  const hasFollower = !isOverrides || dialogFollower;

  const canAdd = hasFollower && (isCustomMode
    ? (isCustomNameValid && propertyValue !== '')
    : (selectedProperty && propertyValue !== ''));

  const followerList = useMemo(() => {
    const list = [];
    Object.entries(followersByType || {}).forEach(([type, followers]) => {
      if (followers && followers.length > 0) {
        list.push({ type, followers });
      }
    });
    return list;
  }, [followersByType]);

  const showPropertySelector = !isOverrides || dialogFollower;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {isOverrides ? 'Add Follower Config Override' : 'Add Follower Config Property'}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 1 }}>
          {/* Step 1: Follower selector (FollowerOverrides only) */}
          {isOverrides && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                Step 1: Select Follower
              </Typography>
              <FormControl fullWidth>
                <InputLabel id="follower-config-dialog-select">Follower</InputLabel>
                <Select
                  labelId="follower-config-dialog-select"
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
                  Select a follower to add config overrides
                </Alert>
              )}
            </Box>
          )}

          {/* Step 2: Property selector */}
          {showPropertySelector && (
            <Box>
              {isOverrides && (
                <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                  Step 2: Select Property
                </Typography>
              )}

              {isCustomMode ? (
                <Box>
                  <TextField
                    fullWidth
                    label="Property Name"
                    value={customPropertyName}
                    onChange={(e) => setCustomPropertyName(e.target.value.toUpperCase())}
                    placeholder="MY_CUSTOM_PARAM"
                    helperText={
                      customPropertyName && !isCustomNameValid
                        ? 'Use UPPER_SNAKE_CASE (e.g., MY_CUSTOM_PARAM)'
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
                    &larr; Back to property list
                  </Button>
                </Box>
              ) : (
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
                      ) : selectedMeta.type === 'enum' ? (
                        <FormControl fullWidth>
                          <InputLabel>Value</InputLabel>
                          <Select
                            value={propertyValue}
                            onChange={(e) => setPropertyValue(e.target.value)}
                            label="Value"
                          >
                            {(selectedMeta.options || []).map(opt => (
                              <MenuItem key={opt} value={opt}>{opt}</MenuItem>
                            ))}
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
                            showComparison && generalDefaults?.[selectedProperty] !== undefined
                              ? `General: ${generalDefaults[selectedProperty]} ${selectedMeta.unit || ''}`
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
 * Main FollowerConfigEditor Component
 */
const FollowerConfigEditor = ({
  type,                    // 'General' | 'FollowerOverrides'
  value,                   // Current object value
  onChange,                // Callback for changes
  generalDefaults = {},    // Reference for comparison (FollowerOverrides only)
  disabled = false
}) => {
  const isOverrides = type === 'FollowerOverrides';
  const [selectedFollower, setSelectedFollower] = useState('');
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  const { isMobile, isTablet } = useResponsive();
  const useCardLayout = isMobile || isTablet;

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
      const targetFollower = followerFromDialog || selectedFollower;
      if (!targetFollower) return;
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
              Per-Follower Config Overrides
            </Typography>
            <Typography variant="caption">
              Override specific operational params for individual followers.
              Empty = uses General defaults. Only set what differs from General.
            </Typography>
          </Box>
        ) : (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              General Follower Defaults
            </Typography>
            <Typography variant="caption">
              Shared operational parameters applied to all followers.
              Individual followers can override these via FollowerOverrides.
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

      {/* Properties Display */}
      {(isOverrides && !selectedFollower) ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Warning sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
          <Typography color="text.secondary">
            Select a follower above to configure overrides
          </Typography>
          <Typography variant="caption" color="text.disabled">
            Or the FollowerOverrides section is empty (using General defaults for all)
          </Typography>
        </Paper>
      ) : (
        <Box>
          {hasProperties ? (
            useCardLayout ? (
              <Box>
                {propertyEntries.map(([propName, propValue]) => (
                  <PropertyCard
                    key={propName}
                    propertyName={propName}
                    value={propValue}
                    generalValue={generalDefaults?.[propName]}
                    onChange={handlePropertyChange}
                    onRemove={handlePropertyRemove}
                    showComparison={isOverrides}
                    disabled={disabled}
                  />
                ))}
              </Box>
            ) : (
              <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
                <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: isOverrides ? '30%' : '40%' }}>Property</TableCell>
                      <TableCell sx={{ width: isOverrides ? '25%' : '35%' }}>Value</TableCell>
                      {isOverrides && <TableCell sx={{ width: '25%' }}>General Value</TableCell>}
                      <TableCell align="right" sx={{ width: isOverrides ? '20%' : '25%', whiteSpace: 'nowrap' }}>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {propertyEntries.map(([propName, propValue]) => (
                      <PropertyRow
                        key={propName}
                        propertyName={propName}
                        value={propValue}
                        generalValue={generalDefaults?.[propName]}
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
                Click "Add Property" below to add config parameters.
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

      {/* Add Property Dialog */}
      {addDialogOpen && (
        <AddPropertyDialog
          open={addDialogOpen}
          onClose={() => setAddDialogOpen(false)}
          onAdd={handlePropertyAdd}
          existingProperties={currentProperties}
          generalDefaults={generalDefaults}
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

export default FollowerConfigEditor;
