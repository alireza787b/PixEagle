// dashboard/src/components/config/renderers/ScalarArrayRenderer.js
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Box, TextField, IconButton, Typography, Slider, Tooltip,
  Paper, Chip
} from '@mui/material';
import { Add, Remove, Tune } from '@mui/icons-material';

/**
 * ScalarArrayRenderer - Editor for arrays of scalar values (numbers, strings)
 *
 * Features:
 * - Indexed inputs for each element
 * - Slider support for number arrays
 * - Add/remove items
 * - Drag to reorder (future)
 * - Min/max item constraints from schema
 */

const ArrayItem = ({
  index,
  value,
  onChange,
  onRemove,
  disabled,
  itemType,
  showSlider,
  range,
  canRemove,
  compact
}) => {
  const [localValue, setLocalValue] = useState(String(value ?? ''));
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => {
    if (!isFocused) {
      setLocalValue(String(value ?? ''));
    }
  }, [value, isFocused]);

  const handleChange = (e) => {
    setLocalValue(e.target.value);
  };

  const handleBlur = () => {
    setIsFocused(false);
    if (itemType === 'number') {
      const parsed = parseFloat(localValue);
      if (!isNaN(parsed)) {
        onChange(index, parsed);
      } else {
        setLocalValue(String(value ?? 0));
      }
    } else {
      onChange(index, localValue);
    }
  };

  const handleSliderChange = (_, newValue) => {
    onChange(index, newValue);
    setLocalValue(String(newValue));
  };

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        py: 0.5
      }}
    >
      {/* Index label */}
      <Typography
        variant="caption"
        sx={{
          minWidth: compact ? 24 : 32,
          color: 'text.secondary',
          fontFamily: 'monospace',
          fontSize: compact ? '0.7rem' : '0.75rem'
        }}
      >
        [{index}]
      </Typography>

      {/* Value input */}
      <TextField
        size="small"
        value={localValue}
        onChange={handleChange}
        onBlur={handleBlur}
        onFocus={() => setIsFocused(true)}
        disabled={disabled}
        type="text"
        inputMode={itemType === 'number' ? 'decimal' : 'text'}
        sx={{
          flex: 1,
          minWidth: compact ? 60 : 80,
          '& .MuiOutlinedInput-root': {
            height: compact ? 28 : 32,
            fontSize: compact ? '0.75rem' : '0.85rem'
          },
          '& input': {
            fontFamily: 'monospace',
            textAlign: 'center',
            padding: compact ? '4px 8px' : '4px 12px'
          }
        }}
      />

      {/* Slider for numbers */}
      {showSlider && itemType === 'number' && range && !compact && (
        <Slider
          size="small"
          value={typeof value === 'number' ? value : 0}
          onChange={handleSliderChange}
          min={range.min}
          max={range.max}
          step={range.step}
          disabled={disabled}
          sx={{
            width: 100,
            mx: 1,
            '& .MuiSlider-thumb': { width: 12, height: 12 }
          }}
        />
      )}

      {/* Remove button */}
      {canRemove && (
        <Tooltip title="Remove item">
          <IconButton
            size="small"
            onClick={() => onRemove(index)}
            disabled={disabled}
            sx={{ p: 0.25 }}
          >
            <Remove fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
};

const ScalarArrayRenderer = ({
  value,
  onChange,
  schema,
  disabled = false,
  compact = false
}) => {
  const [showSliders, setShowSliders] = useState(!compact);

  const arr = useMemo(() => Array.isArray(value) ? value : [], [value]);

  // Determine item type
  const itemType = useMemo(() => {
    return schema?.itemType ||
      (arr.length > 0 ? (typeof arr[0] === 'number' ? 'number' : 'string') : 'number');
  }, [schema?.itemType, arr]);

  // Get constraints from schema
  const minItems = schema?.minItems ?? 0;
  const maxItems = schema?.maxItems ?? Infinity;
  const canAdd = arr.length < maxItems;
  const canRemove = arr.length > minItems;

  // Range for sliders (detect from existing values or schema)
  const range = useMemo(() => ({
    min: schema?.minimum ?? Math.min(0, ...arr.filter(v => typeof v === 'number')),
    max: schema?.maximum ?? Math.max(100, ...arr.filter(v => typeof v === 'number')),
    step: schema?.step ?? 1
  }), [schema?.minimum, schema?.maximum, schema?.step, arr]);

  const handleItemChange = useCallback((index, newValue) => {
    const newArr = [...arr];
    newArr[index] = newValue;
    onChange(newArr);
  }, [arr, onChange]);

  const handleRemove = useCallback((index) => {
    const newArr = arr.filter((_, i) => i !== index);
    onChange(newArr);
  }, [arr, onChange]);

  const handleAdd = useCallback(() => {
    const defaultValue = itemType === 'number' ? 0 : '';
    onChange([...arr, defaultValue]);
  }, [arr, onChange, itemType]);

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
          label={`${arr.length} items`}
          size="small"
          variant="outlined"
          sx={{ height: 22, fontSize: '0.75rem' }}
        />

        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {itemType === 'number' && !compact && (
            <Tooltip title={showSliders ? 'Hide sliders' : 'Show sliders'}>
              <IconButton
                size="small"
                onClick={() => setShowSliders(!showSliders)}
              >
                <Tune fontSize="small" />
              </IconButton>
            </Tooltip>
          )}

          {canAdd && (
            <Tooltip title="Add item">
              <IconButton
                size="small"
                onClick={handleAdd}
                disabled={disabled}
                color="primary"
              >
                <Add fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Items */}
      <Paper variant="outlined" sx={{ p: 1 }}>
        {arr.length > 0 ? (
          arr.map((item, index) => (
            <ArrayItem
              key={index}
              index={index}
              value={item}
              onChange={handleItemChange}
              onRemove={handleRemove}
              disabled={disabled}
              itemType={itemType}
              showSlider={showSliders}
              range={range}
              canRemove={canRemove}
              compact={compact}
            />
          ))
        ) : (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ py: 1, textAlign: 'center' }}
          >
            Empty array - click + to add items
          </Typography>
        )}
      </Paper>

      {/* Constraints info */}
      {(minItems > 0 || maxItems < Infinity) && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ mt: 0.5, display: 'block' }}
        >
          {minItems > 0 && `Min: ${minItems} items`}
          {minItems > 0 && maxItems < Infinity && ' | '}
          {maxItems < Infinity && `Max: ${maxItems} items`}
        </Typography>
      )}
    </Box>
  );
};

export default ScalarArrayRenderer;
