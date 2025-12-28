// dashboard/src/components/config/renderers/PIDRenderer.js
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import {
  Box, TextField, Slider, Typography, Tooltip, IconButton
} from '@mui/material';
import { Tune } from '@mui/icons-material';

/**
 * PIDRenderer - Inline editor for PID triplet values {p, i, d}
 *
 * Features:
 * - Color-coded P/I/D fields (orange/blue/green)
 * - Both slider AND manual text input
 * - Compact mode for table cells
 * - Tooltips with descriptions
 * - Validation with min/max from schema
 */

// Color scheme for PID gains
const PID_COLORS = {
  p: { main: '#FF9800', light: '#FFE0B2', dark: '#E65100', label: 'Proportional' },
  i: { main: '#2196F3', light: '#BBDEFB', dark: '#0D47A1', label: 'Integral' },
  d: { main: '#4CAF50', light: '#C8E6C9', dark: '#1B5E20', label: 'Derivative' }
};

// Default value ranges for PID gains
const DEFAULT_RANGES = {
  p: { min: 0, max: 50, step: 0.1 },
  i: { min: 0, max: 5, step: 0.01 },
  d: { min: 0, max: 10, step: 0.01 }
};

const PIDField = ({
  label,
  value,
  onChange,
  color,
  range,
  disabled,
  compact,
  showSlider
}) => {
  const [localValue, setLocalValue] = useState(String(value ?? 0));
  const [isFocused, setIsFocused] = useState(false);

  // Sync local value when external value changes (not during focus)
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
      // Clamp to range
      const clamped = Math.max(range.min, Math.min(range.max, parsed));
      onChange(clamped);
      setLocalValue(String(clamped));
    } else {
      // Reset to current value
      setLocalValue(String(value ?? 0));
    }
  };

  const handleSliderChange = (_, newValue) => {
    onChange(newValue);
    setLocalValue(String(newValue));
  };

  return (
    <Box sx={{ flex: 1, minWidth: compact ? 70 : 100 }}>
      <Tooltip title={`${color.label} gain`} arrow placement="top">
        <Typography
          variant="caption"
          sx={{
            color: color.main,
            fontWeight: 'bold',
            fontSize: compact ? '0.65rem' : '0.75rem',
            display: 'block',
            mb: 0.25
          }}
        >
          {label.toUpperCase()}
        </Typography>
      </Tooltip>

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
          '& .MuiOutlinedInput-root': {
            height: compact ? 28 : 36,
            fontSize: compact ? '0.75rem' : '0.875rem',
            '& fieldset': {
              borderColor: color.main,
              borderWidth: 2
            },
            '&:hover fieldset': {
              borderColor: color.dark
            },
            '&.Mui-focused fieldset': {
              borderColor: color.dark
            }
          },
          '& input': {
            textAlign: 'center',
            padding: compact ? '4px 8px' : '6px 12px',
            fontFamily: 'monospace'
          }
        }}
        InputProps={{
          sx: { bgcolor: 'background.paper' }
        }}
      />

      {showSlider && !compact && (
        <Slider
          size="small"
          value={typeof value === 'number' ? value : 0}
          onChange={handleSliderChange}
          min={range.min}
          max={range.max}
          step={range.step}
          disabled={disabled}
          sx={{
            mt: 0.5,
            color: color.main,
            '& .MuiSlider-thumb': {
              width: 12,
              height: 12
            },
            '& .MuiSlider-track': {
              height: 3
            },
            '& .MuiSlider-rail': {
              height: 3
            }
          }}
        />
      )}
    </Box>
  );
};

const PIDRenderer = ({
  value,
  onChange,
  schema,
  disabled = false,
  compact = false,
  showLabel = false,
  label = ''
}) => {
  const [showSliders, setShowSliders] = useState(!compact);

  // Normalize value to lowercase keys
  const normalizedValue = useMemo(() => ({
    p: value?.p ?? value?.P ?? 0,
    i: value?.i ?? value?.I ?? 0,
    d: value?.d ?? value?.D ?? 0
  }), [value]);

  // Get ranges from schema or use defaults
  const getRangeForKey = useCallback((key) => {
    const propSchema = schema?.properties?.[key] || schema?.properties?.[key.toUpperCase()];
    return {
      min: propSchema?.minimum ?? DEFAULT_RANGES[key].min,
      max: propSchema?.maximum ?? DEFAULT_RANGES[key].max,
      step: propSchema?.step ?? DEFAULT_RANGES[key].step
    };
  }, [schema?.properties]);

  const handleFieldChange = useCallback((key, newValue) => {
    onChange({
      ...normalizedValue,
      [key]: newValue
    });
  }, [normalizedValue, onChange]);

  return (
    <Box>
      {showLabel && label && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
          {label}
        </Typography>
      )}

      <Box sx={{ display: 'flex', gap: compact ? 0.5 : 1, alignItems: 'flex-start' }}>
        <PIDField
          label="P"
          value={normalizedValue.p}
          onChange={(v) => handleFieldChange('p', v)}
          color={PID_COLORS.p}
          range={getRangeForKey('p')}
          disabled={disabled}
          compact={compact}
          showSlider={showSliders}
        />
        <PIDField
          label="I"
          value={normalizedValue.i}
          onChange={(v) => handleFieldChange('i', v)}
          color={PID_COLORS.i}
          range={getRangeForKey('i')}
          disabled={disabled}
          compact={compact}
          showSlider={showSliders}
        />
        <PIDField
          label="D"
          value={normalizedValue.d}
          onChange={(v) => handleFieldChange('d', v)}
          color={PID_COLORS.d}
          range={getRangeForKey('d')}
          disabled={disabled}
          compact={compact}
          showSlider={showSliders}
        />

        {!compact && (
          <Tooltip title={showSliders ? 'Hide sliders' : 'Show sliders'}>
            <IconButton
              size="small"
              onClick={() => setShowSliders(!showSliders)}
              sx={{ mt: 2 }}
            >
              <Tune fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
};

export default PIDRenderer;
