// dashboard/src/components/config/PropertyEditorShared.js
/**
 * PropertyEditorShared - Shared components for Safety and Follower config editors
 *
 * Exports: PropertyRow, PropertyCard, AddPropertyDialog, FollowerSelector,
 *          EmptyFollowerState, followerTypeIcons
 *
 * All components are dependency-injected via props (getPropertyMeta, getAddableProperties, etc.)
 * No direct import of Safety or Follower schema utils.
 */
import React, { useState, useMemo, useEffect } from 'react';
import {
  Box, Typography, Paper, Alert, Chip, Divider,
  TextField, IconButton, Tooltip, Button, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions,
  FormControl, FormHelperText, InputLabel, Select, MenuItem, ListSubheader,
  InputAdornment, Slider, Card, CardContent, TableRow, TableCell
} from '@mui/material';
import {
  Delete, Edit, Info, Warning,
  FlightTakeoff, CameraAlt, Flight
} from '@mui/icons-material';

import { clampNumericValue, parseCommittedNumeric } from '../../utils/numericInput';

// Shared follower type icons
export const followerTypeIcons = {
  multicopter: <FlightTakeoff fontSize="small" />,
  gimbal: <CameraAlt fontSize="small" />,
  fixed_wing: <Flight fontSize="small" />
};

/**
 * PropertyRow - Table row with inline editing for a single property
 *
 * Handles boolean (Switch), enum (Select), and number (TextField+Slider) types.
 * Override rows get a left border indicator and hover-revealed delete button.
 */
export const PropertyRow = ({
  propertyName,
  value,
  referenceValue,
  onChange,
  onRemove,
  showComparison,
  removable = true,
  isOverride = false,
  disabled,
  propMetaOverride,
  getPropertyMeta,
  categoryIcons = {}
}) => {
  const propMeta = propMetaOverride || getPropertyMeta?.(propertyName);
  const defaultVal = propMeta?.default;
  const [localValue, setLocalValue] = useState(() => String(value ?? defaultVal ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? defaultVal ?? ''));
    }
  }, [value, isFocused, defaultVal]);

  const rowSx = {
    ...(isOverride && {
      '& td:first-of-type': { borderLeft: '3px solid', borderLeftColor: 'warning.main' }
    }),
    '& .delete-action': { opacity: 0, transition: 'opacity 0.2s' },
    '&:hover .delete-action': { opacity: 1 }
  };

  // Boolean type
  if (propMeta?.type === 'boolean') {
    return (
      <TableRow hover sx={rowSx}>
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {categoryIcons[propMeta?.category]}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="body2" fontWeight="medium">
                  {propertyName}
                </Typography>
                {isOverride && (
                  <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
              </Box>
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
              label={referenceValue !== undefined ? (referenceValue ? 'ON' : 'OFF') : 'N/A'}
              size="small"
              variant="outlined"
              color={referenceValue ? 'success' : 'default'}
            />
          </TableCell>
        )}
        <TableCell align="right">
          {removable ? (
            <Tooltip title="Remove this override">
              <IconButton className="delete-action" size="small" onClick={() => onRemove(propertyName)} disabled={disabled}>
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : (
            <Typography variant="caption" color="text.disabled">Default</Typography>
          )}
        </TableCell>
      </TableRow>
    );
  }

  // Enum type
  if (propMeta?.type === 'enum') {
    return (
      <TableRow hover sx={rowSx}>
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {categoryIcons[propMeta?.category]}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="body2" fontWeight="medium">
                  {propertyName}
                </Typography>
                {isOverride && (
                  <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
              </Box>
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
              label={referenceValue !== undefined ? String(referenceValue) : 'N/A'}
              size="small"
              variant="outlined"
            />
          </TableCell>
        )}
        <TableCell align="right">
          {removable ? (
            <Tooltip title="Remove this override">
              <IconButton className="delete-action" size="small" onClick={() => onRemove(propertyName)} disabled={disabled}>
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : (
            <Typography variant="caption" color="text.disabled">Default</Typography>
          )}
        </TableCell>
      </TableRow>
    );
  }

  // Number type (default)
  return (
    <TableRow hover sx={rowSx}>
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
              {isOverride && (
                <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
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
              setLocalValue(String(value ?? defaultVal ?? ''));
            }}
            onBlur={() => {
              setIsFocused(false);
              const parsed = parseCommittedNumeric(localValue, 'float');
              if (!parsed.valid) {
                setLocalValue(String(value ?? defaultVal ?? ''));
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
            value={typeof value === 'number' ? value : (defaultVal ?? 0)}
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
            label={referenceValue !== undefined ? `${referenceValue} ${propMeta?.unit || ''}` : 'N/A'}
            size="small"
            variant="outlined"
          />
        </TableCell>
      )}
      <TableCell align="right">
        {removable ? (
          <Tooltip title="Remove this override">
            <IconButton className="delete-action" size="small" onClick={() => onRemove(propertyName)} disabled={disabled}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        ) : (
          <Typography variant="caption" color="text.disabled">Default</Typography>
        )}
      </TableCell>
    </TableRow>
  );
};

/**
 * PropertyCard - Card layout for mobile/tablet
 *
 * Touch-friendly with always-visible delete button and override badge.
 */
export const PropertyCard = ({
  propertyName,
  value,
  referenceValue,
  onChange,
  onRemove,
  showComparison,
  removable = true,
  isOverride = false,
  disabled,
  propMetaOverride,
  getPropertyMeta,
  categoryIcons = {},
  referenceLabel = 'Reference'
}) => {
  const propMeta = propMetaOverride || getPropertyMeta?.(propertyName);
  const defaultVal = propMeta?.default;
  const [localValue, setLocalValue] = useState(() => String(value ?? defaultVal ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  const isCustomProperty = !propMeta;
  const min = propMeta?.min ?? 0;
  const max = propMeta?.max ?? 1000;
  const step = propMeta?.step ?? 0.1;

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? defaultVal ?? ''));
    }
  }, [value, isFocused, defaultVal]);

  return (
    <Card variant="outlined" sx={{
      mb: 2,
      ...(isOverride && { borderLeft: '3px solid', borderLeftColor: 'warning.main' })
    }}>
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
                {isOverride && (
                  <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {isCustomProperty ? 'Custom property' : propMeta?.description}
              </Typography>
            </Box>
          </Box>
          {removable ? (
            <IconButton size="small" onClick={() => onRemove(propertyName)} disabled={disabled} color="error">
              <Delete fontSize="small" />
            </IconButton>
          ) : (
            <Chip label="Default" size="small" variant="outlined" color="default" sx={{ height: 20, fontSize: '0.6rem' }} />
          )}
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
                setLocalValue(String(value ?? defaultVal ?? ''));
              }}
              onBlur={() => {
                setIsFocused(false);
                const parsed = parseCommittedNumeric(localValue, 'float');
                if (!parsed.valid) {
                  setLocalValue(String(value ?? defaultVal ?? ''));
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
              value={typeof value === 'number' ? value : (defaultVal ?? 0)}
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

        {/* Reference comparison */}
        {showComparison && referenceValue !== undefined && (
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              {referenceLabel}: {propMeta?.type === 'boolean'
                ? (referenceValue ? 'ON' : 'OFF')
                : propMeta?.type === 'enum'
                  ? String(referenceValue)
                  : `${referenceValue} ${propMeta?.unit || ''}`}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

/**
 * AddPropertyDialog - Dialog for adding new properties
 *
 * Supports boolean, enum, and number types with reference default hints.
 */
export const AddPropertyDialog = ({
  open,
  onClose,
  onAdd,
  existingProperties,
  referenceDefaults,
  showComparison,
  isOverrides = false,
  selectedFollower = '',
  onFollowerChange,
  followersByType = {},
  getAddableProperties: getAddablePropertiesFn,
  getPropertyMeta,
  categoryIcons = {},
  propertyCategoryLabels = {},
  dialogTitle = 'Add Property',
  referenceLabel = 'Reference',
  followerTypeLabels = {}
}) => {
  const [dialogFollower, setDialogFollower] = useState(selectedFollower || '');
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [customPropertyName, setCustomPropertyName] = useState('');

  const addableProperties = useMemo(() =>
    getAddablePropertiesFn?.(existingProperties || {}) || [],
    [existingProperties, getAddablePropertiesFn]
  );

  const groupedProperties = useMemo(() => {
    const groups = {};
    addableProperties.forEach(prop => {
      if (!groups[prop.category]) groups[prop.category] = [];
      groups[prop.category].push(prop);
    });
    return groups;
  }, [addableProperties]);

  const selectedMeta = selectedProperty && !isCustomMode ? getPropertyMeta?.(selectedProperty) : null;

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
      const meta = getPropertyMeta?.(propName);
      const defaultVal = referenceDefaults?.[propName] ?? meta?.default ?? 0;
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
      if (followers && followers.length > 0) list.push({ type, followers });
    });
    return list;
  }, [followersByType]);

  const showPropertySelector = !isOverrides || dialogFollower;

  // Helper text showing reference defaults for boolean/enum selectors
  const getReferenceHint = () => {
    if (!selectedMeta || !showComparison) return null;
    const refVal = referenceDefaults?.[selectedProperty];
    if (refVal === undefined) return null;
    if (selectedMeta.type === 'boolean') {
      return `${referenceLabel} default: ${refVal ? 'ON' : 'OFF'}`;
    }
    if (selectedMeta.type === 'enum') {
      return `${referenceLabel} default: ${refVal}`;
    }
    return null;
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{dialogTitle}</DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 1 }}>
          {/* Step 1: Follower selector (FollowerOverrides only) */}
          {isOverrides && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" color="primary" sx={{ mb: 1 }}>
                Step 1: Select Follower
              </Typography>
              <FormControl fullWidth>
                <InputLabel id="shared-dialog-follower-select">Follower</InputLabel>
                <Select
                  labelId="shared-dialog-follower-select"
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
                        <span>{followerTypeLabels[type] || type}</span>
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
                    error={Boolean(customPropertyName && !isCustomNameValid)}
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
                            {propertyCategoryLabels[category] || category}
                          </Box>
                        </ListSubheader>,
                        ...props.map(prop => (
                          <MenuItem key={prop.name} value={prop.name}>
                            <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                              <Typography variant="body2">{prop.name}</Typography>
                              <Typography variant="caption" color="text.secondary">
                                {prop.description} ({prop.unit || prop.type})
                                {showComparison && referenceDefaults?.[prop.name] !== undefined &&
                                  ` \u2014 ${referenceLabel}: ${referenceDefaults[prop.name]}`}
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
                          {getReferenceHint() && (
                            <FormHelperText>{getReferenceHint()}</FormHelperText>
                          )}
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
                          {getReferenceHint() && (
                            <FormHelperText>{getReferenceHint()}</FormHelperText>
                          )}
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
                            showComparison && referenceDefaults?.[selectedProperty] !== undefined
                              ? `${referenceLabel} default: ${referenceDefaults[selectedProperty]} ${selectedMeta.unit || ''}`
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
        <Button onClick={handleAdd} variant="contained" disabled={!canAdd}>
          Add Property
        </Button>
      </DialogActions>
    </Dialog>
  );
};

/**
 * FollowerSelector - Grouped dropdown with quick-switch chips
 */
export const FollowerSelector = ({
  selectedFollower,
  onFollowerChange,
  followersByType = {},
  followerOverrideCounts = {},
  label = 'Select Follower to Configure',
  followerTypeLabels = {}
}) => (
  <Box sx={{ mb: 3 }}>
    <FormControl fullWidth>
      <InputLabel>{label}</InputLabel>
      <Select
        value={selectedFollower}
        onChange={(e) => onFollowerChange(e.target.value)}
        label={label}
      >
        <MenuItem value="">
          <em>-- Select Follower --</em>
        </MenuItem>
        {Object.entries(followersByType).map(([type, followers]) => [
          <ListSubheader key={`type-${type}`}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {followerTypeIcons[type]}
              {followerTypeLabels[type] || type}
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

    {/* Quick-switch chips for configured followers */}
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
            onClick={() => onFollowerChange(follower)}
            sx={{ cursor: 'pointer' }}
          />
        ))}
      </Box>
    )}
  </Box>
);

/**
 * EmptyFollowerState - Placeholder when no follower is selected
 */
export const EmptyFollowerState = ({
  message = 'Select a follower above to configure overrides',
  hint = 'No follower selected'
}) => (
  <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
    <Warning sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
    <Typography color="text.secondary">{message}</Typography>
    <Typography variant="caption" color="text.disabled">{hint}</Typography>
  </Paper>
);
