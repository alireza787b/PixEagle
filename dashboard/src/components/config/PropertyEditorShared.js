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
  fixed_wing: <Flight fontSize="small" />,
  other: <Info fontSize="small" />,
  migration: <Warning fontSize="small" color="warning" />,
};

const optionValue = (option) => (
  option && typeof option === 'object' ? option.value : option
);
const optionLabel = (option) => (
  option && typeof option === 'object' ? (option.label || String(option.value)) : String(option)
);
const hasSliderRange = (min, max) => Number.isFinite(min) && Number.isFinite(max) && max > min;

const formatValue = (value) => {
  if (value === undefined) return '(not set)';
  if (value === null) return 'null';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_error) {
      return String(value);
    }
  }
  return String(value);
};

const PropertyValueEditor = ({ propMeta, value, onChange, disabled, mobile = false }) => {
  const defaultVal = propMeta?.default;
  const min = propMeta?.min;
  const max = propMeta?.max;
  const numericType = propMeta?.schemaType === 'integer' ? 'integer' : 'float';
  const step = propMeta?.step ?? (numericType === 'integer' ? 1 : 0.1);
  const [localValue, setLocalValue] = useState(() => String(value ?? defaultVal ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => {
    if (!isFocused) setLocalValue(String(value ?? defaultVal ?? ''));
  }, [value, isFocused, defaultVal]);

  if (!propMeta || propMeta.editable === false || !['boolean', 'enum', 'string', 'number'].includes(propMeta.type)) {
    return (
      <TextField
        fullWidth
        size="small"
        multiline={typeof value === 'object' && value !== null}
        minRows={typeof value === 'object' && value !== null ? 2 : undefined}
        maxRows={6}
        value={formatValue(value)}
        disabled
        helperText={propMeta?.readOnlyReason || 'Undeclared or unsupported value; migration required before editing'}
      />
    );
  }

  if (propMeta.type === 'boolean') {
    return (
      <Switch
        checked={Boolean(value)}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
        size={mobile ? 'medium' : 'small'}
      />
    );
  }

  if (propMeta.type === 'enum') {
    const options = propMeta.options || [];
    const inOptions = options.some((option) => optionValue(option) === value);
    const hasValue = value !== '' && value !== null && value !== undefined;
    const outOfContract = hasValue && !inOptions && !propMeta.allowCustomValues;
    const selectValue = inOptions ? value : (hasValue ? '__current_custom__' : '');
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
        <Select
          fullWidth={mobile}
          size="small"
          value={selectValue}
          onChange={(event) => {
            if (event.target.value === '__custom__') {
              const customValue = window.prompt('Enter custom value:', value ?? '');
              if (customValue !== null && customValue !== '') onChange(customValue);
              return;
            }
            if (event.target.value !== '__current_custom__') onChange(event.target.value);
          }}
          disabled={disabled || outOfContract}
          sx={{ minWidth: mobile ? 0 : 160 }}
        >
          {!inOptions && hasValue && (
            <MenuItem value="__current_custom__">{String(value)} (needs migration)</MenuItem>
          )}
          {options.map((option) => (
            <MenuItem key={String(optionValue(option))} value={optionValue(option)}>
              {optionLabel(option)}
            </MenuItem>
          ))}
          {propMeta.allowCustomValues && <Divider />}
          {propMeta.allowCustomValues && <MenuItem value="__custom__">Enter custom value...</MenuItem>}
        </Select>
        {outOfContract && <Chip label="Needs migration" size="small" color="warning" variant="outlined" />}
      </Box>
    );
  }

  if (propMeta.type === 'string') {
    return (
      <TextField
        fullWidth={mobile}
        size="small"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        sx={{ minWidth: mobile ? 0 : 160 }}
      />
    );
  }

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: mobile ? 0 : 200 }}>
        <TextField
          fullWidth={mobile}
          size="small"
          type="number"
          value={localValue}
          onChange={(event) => setLocalValue(event.target.value)}
          onFocus={() => {
            setIsFocused(true);
            setLocalValue(String(value ?? defaultVal ?? ''));
          }}
          onBlur={() => {
            setIsFocused(false);
            const parsed = parseCommittedNumeric(localValue, numericType);
            if (!parsed.valid) {
              setLocalValue(String(value ?? defaultVal ?? ''));
              return;
            }
            const boundedValue = clampNumericValue(parsed.value, min, max);
            setLocalValue(String(boundedValue));
            if (boundedValue !== value) onChange(boundedValue);
          }}
          disabled={disabled}
          inputProps={{ min, max, step }}
          sx={{ width: mobile ? '100%' : 110 }}
          InputProps={{
            endAdornment: propMeta.unit && (
              <InputAdornment position="end">
                <Typography variant="caption" color="text.secondary">{propMeta.unit}</Typography>
              </InputAdornment>
            )
          }}
        />
        {!mobile && hasSliderRange(min, max) && (
          <Slider
            size="small"
            value={typeof value === 'number' ? value : (defaultVal ?? min)}
            onChange={(_, newValue) => {
              onChange(newValue);
              setLocalValue(String(newValue));
            }}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            sx={{ flex: 1, minWidth: 80 }}
          />
        )}
      </Box>
      {mobile && hasSliderRange(min, max) && (
        <Slider
          size="small"
          value={typeof value === 'number' ? value : (defaultVal ?? min)}
          onChange={(_, newValue) => {
            onChange(newValue);
            setLocalValue(String(newValue));
          }}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          valueLabelDisplay="auto"
          sx={{ mt: 1 }}
        />
      )}
    </Box>
  );
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
  const isMigrationProperty = !propMeta || propMeta.editable === false;
  const controlsDisabled = disabled || isMigrationProperty;

  const rowSx = {
    ...(isOverride && {
      '& td:first-of-type': { borderLeft: '3px solid', borderLeftColor: 'warning.main' }
    }),
    '& .delete-action': { opacity: 0, transition: 'opacity 0.2s' },
    '&:hover .delete-action': { opacity: 1 }
  };

  return (
    <TableRow hover sx={rowSx}>
      <TableCell>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {isMigrationProperty ? <Warning fontSize="small" color="warning" /> : categoryIcons[propMeta?.category]}
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Typography variant="body2" fontWeight="medium">
                {propertyName}
              </Typography>
              {isMigrationProperty && (
                <Chip label="Needs migration" size="small" variant="outlined" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
              )}
              {isOverride && (
                <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
              )}
            </Box>
            <Typography variant="caption" color="text.secondary">
              {isMigrationProperty ? 'Undeclared or incomplete server contract' : propMeta?.description}
            </Typography>
          </Box>
        </Box>
      </TableCell>
      <TableCell>
        <PropertyValueEditor
          propMeta={propMeta}
          value={value}
          onChange={(newValue) => onChange(propertyName, newValue)}
          disabled={controlsDisabled}
        />
      </TableCell>
      {showComparison && (
        <TableCell>
          <Chip
            label={referenceValue !== undefined ? formatValue(referenceValue) : 'N/A'}
            size="small"
            variant="outlined"
          />
        </TableCell>
      )}
      <TableCell align="right">
        {removable ? (
          <Tooltip title={isMigrationProperty ? 'Resolve the schema migration before changing this entry' : 'Remove this override'}>
            <span>
            <IconButton className="delete-action" size="small" onClick={() => onRemove(propertyName)} disabled={controlsDisabled}>
              <Delete fontSize="small" />
            </IconButton>
            </span>
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
  const isMigrationProperty = !propMeta || propMeta.editable === false;
  const controlsDisabled = disabled || isMigrationProperty;

  return (
    <Card variant="outlined" sx={{
      mb: 2,
      ...(isOverride && { borderLeft: '3px solid', borderLeftColor: 'warning.main' })
    }}>
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
            {isMigrationProperty ? <Warning fontSize="small" color="warning" /> : categoryIcons[propMeta?.category]}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexWrap: 'wrap' }}>
                <Typography variant="body2" fontWeight="medium">
                  {propertyName}
                </Typography>
                {isMigrationProperty && (
                  <Chip label="Needs migration" size="small" variant="outlined" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
                {isOverride && (
                  <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {isMigrationProperty ? 'Undeclared or incomplete server contract' : propMeta?.description}
              </Typography>
            </Box>
          </Box>
          {removable ? (
            <IconButton size="small" onClick={() => onRemove(propertyName)} disabled={controlsDisabled} color="error">
              <Delete fontSize="small" />
            </IconButton>
          ) : (
            <Chip label="Default" size="small" variant="outlined" color="default" sx={{ height: 20, fontSize: '0.6rem' }} />
          )}
        </Box>

        {/* Value editor */}
        <PropertyValueEditor
          propMeta={propMeta}
          value={value}
          onChange={(newValue) => onChange(propertyName, newValue)}
          disabled={controlsDisabled}
          mobile
        />

        {/* Reference comparison */}
        {showComparison && referenceValue !== undefined && (
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary">
              {referenceLabel}: {formatValue(referenceValue)}
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
  followerTypeLabels = {},
  allowCustomProperties = false,
  customPropertyMeta = null,
  disabled = false,
}) => {
  const [dialogFollower, setDialogFollower] = useState(selectedFollower || '');
  const [selectedProperty, setSelectedProperty] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [isCustomMode, setIsCustomMode] = useState(false);
  const [customPropertyName, setCustomPropertyName] = useState('');

  const addableProperties = useMemo(() =>
    getAddablePropertiesFn?.(existingProperties || {}, dialogFollower) || [],
    [dialogFollower, existingProperties, getAddablePropertiesFn]
  );

  const groupedProperties = useMemo(() => {
    const groups = {};
    addableProperties.forEach(prop => {
      if (!groups[prop.category]) groups[prop.category] = [];
      groups[prop.category].push(prop);
    });
    return groups;
  }, [addableProperties]);

  const selectedMeta = selectedProperty && !isCustomMode
    ? getPropertyMeta?.(selectedProperty, dialogFollower)
    : null;
  const effectiveMeta = isCustomMode ? customPropertyMeta : selectedMeta;

  const handleAdd = () => {
    if (disabled || !effectiveMeta?.editable) return;
    const propName = isCustomMode ? customPropertyName.trim() : selectedProperty;
    const effectiveFollower = isOverrides ? dialogFollower : null;

    if (propName && propertyValue !== '' && (!isOverrides || effectiveFollower)) {
      let value;
      if (effectiveMeta.type === 'boolean') {
        value = propertyValue === 'true';
      } else if (effectiveMeta.type === 'enum') {
        value = propertyValue;
      } else if (effectiveMeta.type === 'string') {
        value = propertyValue;
      } else if (effectiveMeta.type === 'number') {
        const parsed = parseCommittedNumeric(
          propertyValue,
          effectiveMeta.schemaType === 'integer' ? 'integer' : 'float'
        );
        if (!parsed.valid) return;
        value = clampNumericValue(parsed.value, effectiveMeta.min, effectiveMeta.max);
      } else return;

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
      if (!allowCustomProperties || !customPropertyMeta?.editable) return;
      setIsCustomMode(true);
      setSelectedProperty('');
      const defaultValue = customPropertyMeta.default
        ?? (customPropertyMeta.type === 'boolean' ? false : (customPropertyMeta.type === 'number' ? 0 : ''));
      setPropertyValue(String(defaultValue));
    } else {
      setIsCustomMode(false);
      setSelectedProperty(propName);
      const meta = getPropertyMeta?.(propName, dialogFollower);
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
    ? (allowCustomProperties && customPropertyMeta?.editable && isCustomNameValid && propertyValue !== '')
    : (selectedProperty && selectedMeta?.editable && propertyValue !== ''));

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
                    disabled={disabled}
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
                        : 'Name and value are validated by the server-provided extension contract.'
                    }
                    error={Boolean(customPropertyName && !isCustomNameValid)}
                    sx={{ mb: 2 }}
                    disabled={disabled}
                  />
                  {customPropertyMeta?.type === 'boolean' ? (
                    <FormControl fullWidth>
                      <InputLabel>Value</InputLabel>
                      <Select
                        value={propertyValue}
                        onChange={(e) => setPropertyValue(e.target.value)}
                        label="Value"
                        disabled={disabled}
                      >
                        <MenuItem value="true">Enabled (ON)</MenuItem>
                        <MenuItem value="false">Disabled (OFF)</MenuItem>
                      </Select>
                    </FormControl>
                  ) : customPropertyMeta?.type === 'enum' ? (
                    <FormControl fullWidth>
                      <InputLabel>Value</InputLabel>
                      <Select
                        value={propertyValue}
                        onChange={(e) => setPropertyValue(e.target.value)}
                        label="Value"
                        disabled={disabled}
                      >
                        {(customPropertyMeta.options || []).map((option) => (
                          <MenuItem key={String(optionValue(option))} value={optionValue(option)}>
                            {optionLabel(option)}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  ) : (
                    <TextField
                      fullWidth
                      label="Value"
                      type={customPropertyMeta?.type === 'number' ? 'number' : 'text'}
                      value={propertyValue}
                      onChange={(e) => setPropertyValue(e.target.value)}
                      inputProps={{
                        min: customPropertyMeta?.min,
                        max: customPropertyMeta?.max,
                        step: customPropertyMeta?.step,
                      }}
                      disabled={disabled}
                    />
                  )}
                  <Button
                    size="small"
                    onClick={() => {
                      setIsCustomMode(false);
                      setCustomPropertyName('');
                    }}
                    sx={{ mt: 1 }}
                    disabled={disabled}
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
                      disabled={disabled}
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
                      {allowCustomProperties && <Divider />}
                      {allowCustomProperties && (
                        <MenuItem value="__custom__">
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Edit fontSize="small" color="primary" />
                            <Typography color="primary" fontStyle="italic" variant="body2">
                              Enter custom property...
                            </Typography>
                          </Box>
                        </MenuItem>
                      )}
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
                            disabled={disabled}
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
                            disabled={disabled}
                          >
                            {(selectedMeta.options || []).map(opt => (
                              <MenuItem key={String(optionValue(opt))} value={optionValue(opt)}>
                                {optionLabel(opt)}
                              </MenuItem>
                            ))}
                          </Select>
                          {getReferenceHint() && (
                            <FormHelperText>{getReferenceHint()}</FormHelperText>
                          )}
                        </FormControl>
                      ) : selectedMeta.type === 'string' ? (
                        <TextField
                          fullWidth
                          label="Value"
                          value={propertyValue}
                          onChange={(e) => setPropertyValue(e.target.value)}
                          helperText={getReferenceHint()}
                          disabled={disabled}
                        />
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
                              : hasSliderRange(selectedMeta.min, selectedMeta.max)
                                ? `Range: ${selectedMeta.min} - ${selectedMeta.max} ${selectedMeta.unit || ''}`
                                : selectedMeta.unit || undefined
                          }
                          disabled={disabled}
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
        <Button onClick={handleAdd} variant="contained" disabled={disabled || !canAdd}>
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
                {f.readOnly && (
                  <Chip size="small" label="Read-only" color="warning" variant="outlined" sx={{ ml: 1 }} />
                )}
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
            color={followersByType.migration?.some((entry) => entry.name === follower)
              ? 'warning'
              : (selectedFollower === follower ? 'primary' : 'default')}
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
