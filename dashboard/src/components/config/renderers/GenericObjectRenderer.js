// dashboard/src/components/config/renderers/GenericObjectRenderer.js
import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Box, TextField, Switch, Slider, Typography, Tooltip, Paper,
  InputAdornment, Chip, Collapse, IconButton,
  Select, MenuItem, FormControl
} from '@mui/material';
import { ExpandMore, ExpandLess, Info } from '@mui/icons-material';

/**
 * GenericObjectRenderer - Schema-driven editor for flat objects
 *
 * Features:
 * - Auto-generates form fields from schema properties
 * - Supports string, number, boolean, enum types
 * - Dual input (text + slider) for numbers
 * - Validation from schema (min/max, required)
 * - Compact mode for table cells
 * - Description tooltips
 */

// Format field label from key
const formatLabel = (key) => {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
};

// Get field type from schema or infer from value
const getFieldType = (propSchema, value) => {
  if (propSchema?.enum) return 'enum';
  if (propSchema?.type === 'boolean' || typeof value === 'boolean') return 'boolean';
  if (propSchema?.type === 'number' || propSchema?.type === 'integer' || typeof value === 'number') return 'number';
  return 'string';
};

/**
 * Calculate smart range based on current value
 * Adapts to order of magnitude, stable during editing
 */
const calculateSmartRange = (value, isInteger = false) => {
  const absValue = Math.abs(value || 0);

  // If value is 0 or very small, use reasonable defaults
  if (absValue < 0.001) {
    return { min: 0, max: isInteger ? 100 : 10, step: isInteger ? 1 : 0.1 };
  }

  const magnitude = Math.floor(Math.log10(absValue));
  const step = isInteger ? 1 : Math.max(Math.pow(10, magnitude - 2), 0.001);
  const maxRaw = absValue * 3;
  const roundTo = Math.pow(10, magnitude);
  const max = Math.ceil(maxRaw / roundTo) * roundTo;
  const min = value < 0 ? -max : 0;

  return {
    min: Math.min(min, value * 0.5),
    max: Math.max(max, absValue * 1.5),
    step
  };
};

// Number field with optional slider
const NumberField = ({
  label,
  value,
  onChange,
  schema,
  disabled,
  compact,
  showSlider
}) => {
  const [localValue, setLocalValue] = useState(String(value ?? 0));
  const [isFocused, setIsFocused] = useState(false);

  // Calculate smart range based on initial value (stable during editing)
  const smartRange = useMemo(() => {
    try {
      return calculateSmartRange(value, schema?.type === 'integer');
    } catch {
      return { min: 0, max: 100, step: 0.1 };
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const min = schema?.minimum ?? smartRange?.min ?? 0;
  const max = schema?.maximum ?? smartRange?.max ?? 100;
  const step = schema?.step ?? smartRange?.step ?? 0.1;

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? 0));
    }
  }, [value, isFocused]);

  const handleTextChange = (e) => {
    setLocalValue(e.target.value);
  };

  const handleTextBlur = () => {
    setIsFocused(false);
    const parsed = parseFloat(localValue);
    if (!isNaN(parsed)) {
      const clamped = Math.max(min, Math.min(max, parsed));
      onChange(schema?.type === 'integer' ? Math.round(clamped) : clamped);
      setLocalValue(String(clamped));
    } else {
      setLocalValue(String(value ?? 0));
    }
  };

  const handleSliderChange = (_, newValue) => {
    onChange(newValue);
    setLocalValue(String(newValue));
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
      <TextField
        size="small"
        value={localValue}
        onChange={handleTextChange}
        onBlur={handleTextBlur}
        onFocus={() => setIsFocused(true)}
        disabled={disabled}
        type="text"
        inputMode="decimal"
        sx={{
          width: compact ? 80 : 120,
          '& .MuiOutlinedInput-root': {
            height: compact ? 28 : 36,
            fontSize: compact ? '0.75rem' : '0.85rem'
          },
          '& input': {
            textAlign: 'right',
            fontFamily: 'monospace',
            padding: compact ? '4px 8px' : '6px 12px'
          }
        }}
        InputProps={{
          endAdornment: schema?.unit && (
            <InputAdornment position="end">
              <Typography variant="caption" color="text.secondary">
                {schema.unit}
              </Typography>
            </InputAdornment>
          )
        }}
      />

      {showSlider && !compact && (
        <Slider
          size="small"
          value={typeof value === 'number' ? value : 0}
          onChange={handleSliderChange}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          sx={{
            flex: 1,
            minWidth: 80,
            '& .MuiSlider-thumb': { width: 12, height: 12 }
          }}
        />
      )}
    </Box>
  );
};

// Boolean field (switch)
const BooleanField = ({ value, onChange, disabled, compact }) => {
  return (
    <Switch
      checked={Boolean(value)}
      onChange={(e) => onChange(e.target.checked)}
      disabled={disabled}
      size={compact ? 'small' : 'medium'}
    />
  );
};

// String field
const StringField = ({ value, onChange, schema, disabled, compact }) => {
  const [localValue, setLocalValue] = useState(String(value ?? ''));

  useEffect(() => {
    setLocalValue(String(value ?? ''));
  }, [value]);

  return (
    <TextField
      size="small"
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={() => onChange(localValue)}
      disabled={disabled}
      placeholder={schema?.default ?? ''}
      sx={{
        flex: 1,
        minWidth: compact ? 100 : 150,
        '& .MuiOutlinedInput-root': {
          height: compact ? 28 : 36,
          fontSize: compact ? '0.75rem' : '0.85rem'
        },
        '& input': {
          padding: compact ? '4px 8px' : '6px 12px'
        }
      }}
    />
  );
};

// Enum field (dropdown)
const EnumField = ({ value, onChange, schema, disabled, compact }) => {
  const options = schema?.enum || [];

  return (
    <FormControl size="small" sx={{ minWidth: compact ? 100 : 150 }}>
      <Select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        sx={{
          height: compact ? 28 : 36,
          fontSize: compact ? '0.75rem' : '0.85rem'
        }}
      >
        {options.map((opt) => (
          <MenuItem key={opt} value={opt}>
            {opt}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
};

// Single property row
const PropertyRow = ({
  propKey,
  value,
  onChange,
  schema,
  disabled,
  compact
}) => {
  const showSlider = !compact;
  const fieldType = getFieldType(schema, value);
  const description = schema?.description;

  const renderField = () => {
    switch (fieldType) {
      case 'boolean':
        return (
          <BooleanField
            value={value}
            onChange={onChange}
            disabled={disabled}
            compact={compact}
          />
        );
      case 'number':
        return (
          <NumberField
            label={propKey}
            value={value}
            onChange={onChange}
            schema={schema}
            disabled={disabled}
            compact={compact}
            showSlider={showSlider}
          />
        );
      case 'enum':
        return (
          <EnumField
            value={value}
            onChange={onChange}
            schema={schema}
            disabled={disabled}
            compact={compact}
          />
        );
      default:
        return (
          <StringField
            value={value}
            onChange={onChange}
            schema={schema}
            disabled={disabled}
            compact={compact}
          />
        );
    }
  };

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 2,
        py: compact ? 0.5 : 1,
        px: compact ? 0 : 1,
        borderBottom: '1px solid',
        borderColor: 'divider',
        '&:last-child': { borderBottom: 'none' }
      }}
    >
      {/* Label with optional tooltip */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minWidth: compact ? 100 : 150 }}>
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'monospace',
            fontSize: compact ? '0.7rem' : '0.8rem',
            color: 'text.primary',
            fontWeight: 500
          }}
        >
          {formatLabel(propKey)}
        </Typography>
        {description && !compact && (
          <Tooltip title={description} arrow placement="top">
            <Info fontSize="small" sx={{ color: 'text.secondary', fontSize: 14, cursor: 'help' }} />
          </Tooltip>
        )}
      </Box>

      {/* Type indicator chip */}
      {!compact && (
        <Chip
          label={fieldType}
          size="small"
          variant="outlined"
          sx={{
            height: 18,
            fontSize: '0.65rem',
            '& .MuiChip-label': { px: 0.75 }
          }}
        />
      )}

      {/* Field */}
      <Box sx={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
        {renderField()}
      </Box>
    </Box>
  );
};

const GenericObjectRenderer = ({
  value,
  onChange,
  schema,
  disabled = false,
  compact = false
}) => {
  const [expanded, setExpanded] = useState(true);

  const obj = useMemo(() => value || {}, [value]);
  const properties = useMemo(() => schema?.properties || {}, [schema]);

  // Get sorted keys - schema order first, then remaining value keys
  const sortedKeys = useMemo(() => {
    const schemaKeys = Object.keys(properties);
    const valueKeys = Object.keys(obj);
    const allKeys = new Set([...schemaKeys, ...valueKeys]);
    return Array.from(allKeys);
  }, [properties, obj]);

  const handlePropertyChange = useCallback((propKey, newValue) => {
    onChange({
      ...obj,
      [propKey]: newValue
    });
  }, [obj, onChange]);

  const propertyCount = sortedKeys.length;

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 1
        }}
      >
        <Chip
          label={`${propertyCount} properties`}
          size="small"
          variant="outlined"
          sx={{ height: 22, fontSize: '0.75rem' }}
        />

        {!compact && propertyCount > 3 && (
          <IconButton size="small" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
          </IconButton>
        )}
      </Box>

      {/* Properties */}
      <Collapse in={expanded || compact} collapsedSize={compact ? 0 : 120}>
        <Paper
          variant="outlined"
          sx={{
            p: compact ? 0.5 : 1,
            bgcolor: 'background.paper'
          }}
        >
          {sortedKeys.length > 0 ? (
            sortedKeys.map((propKey) => (
              <PropertyRow
                key={propKey}
                propKey={propKey}
                value={obj[propKey]}
                onChange={(newVal) => handlePropertyChange(propKey, newVal)}
                schema={properties[propKey]}
                disabled={disabled}
                compact={compact}
              />
            ))
          ) : (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ py: 2, textAlign: 'center' }}
            >
              Empty object
            </Typography>
          )}
        </Paper>
      </Collapse>

      {/* Collapsed indicator */}
      {!expanded && !compact && propertyCount > 3 && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mt: 0.5, display: 'block', textAlign: 'center' }}
        >
          Click to expand ({propertyCount - 3} more properties hidden)
        </Typography>
      )}
    </Box>
  );
};

export default GenericObjectRenderer;
