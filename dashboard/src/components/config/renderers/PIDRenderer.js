// dashboard/src/components/config/renderers/PIDRenderer.js
import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Box, TextField, Slider, Typography, Tooltip, IconButton
} from '@mui/material';
import { Tune } from '@mui/icons-material';
import { useResponsive } from '../../../hooks/useResponsive';

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

// Fallback ranges when no value or schema available
const FALLBACK_RANGES = {
  p: { min: 0, max: 10, step: 0.1 },
  i: { min: 0, max: 1, step: 0.01 },
  d: { min: 0, max: 5, step: 0.01 }
};

/**
 * Calculate smart range based on current value
 * - Adapts to order of magnitude of the value
 * - Always includes 0 and current value with headroom
 * - Stable during editing (calculated once on mount)
 */
const calculateSmartRange = (value, key) => {
  const absValue = Math.abs(value || 0);

  // If value is 0 or very small, use fallback
  if (absValue < 0.001) {
    return FALLBACK_RANGES[key] || { min: 0, max: 10, step: 0.1 };
  }

  // Calculate order of magnitude
  const magnitude = Math.floor(Math.log10(absValue));

  // Smart step based on magnitude (2 decimal places of precision)
  const step = Math.max(Math.pow(10, magnitude - 2), 0.001);

  // Range: 0 to ~3x current value, rounded to nice number
  const maxRaw = absValue * 3;
  const roundTo = Math.pow(10, magnitude);
  const max = Math.ceil(maxRaw / roundTo) * roundTo;

  // Min is 0 for positive values, allow negative for negative values
  const min = value < 0 ? -max : 0;

  return {
    min: Math.min(min, value * 0.5),
    max: Math.max(max, absValue * 1.5),
    step
  };
};

const PIDField = ({
  label,
  value,
  onChange,
  color,
  range,
  disabled,
  compact,
  showSlider,
  mobileMode = false
}) => {
  const { touchTargetSize } = useResponsive();
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
    <Box sx={{
      flex: 1,
      minWidth: mobileMode ? 0 : (compact ? 70 : 100),
      width: mobileMode ? '100%' : 'auto'
    }}>
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
        size={mobileMode ? touchTargetSize : 'small'}
        fullWidth={mobileMode}
        value={localValue}
        onChange={handleTextChange}
        onBlur={handleTextBlur}
        onFocus={() => setIsFocused(true)}
        disabled={disabled}
        type="text"
        inputMode="decimal"
        sx={{
          '& .MuiOutlinedInput-root': {
            height: mobileMode ? (touchTargetSize === 'medium' ? 44 : 36) : (compact ? 28 : 36),
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
  label = '',
  isMobile: propIsMobile
}) => {
  const { isMobile: hookIsMobile } = useResponsive();
  const effectiveMobile = propIsMobile ?? hookIsMobile;

  // User can toggle sliders on desktop
  const [showSlidersLocal, setShowSlidersLocal] = useState(true);

  // Simple logic: hide sliders if mobile OR user toggled off OR compact mode
  const effectiveShowSliders = !effectiveMobile && showSlidersLocal && !compact;

  // Normalize value to lowercase keys
  const normalizedValue = useMemo(() => ({
    p: value?.p ?? value?.P ?? 0,
    i: value?.i ?? value?.I ?? 0,
    d: value?.d ?? value?.D ?? 0
  }), [value]);

  // Calculate ranges ONCE on mount (stable during editing)
  const initialRangesRef = useRef(null);
  if (initialRangesRef.current === null) {
    const initP = value?.p ?? value?.P ?? 0;
    const initI = value?.i ?? value?.I ?? 0;
    const initD = value?.d ?? value?.D ?? 0;
    initialRangesRef.current = {
      p: calculateSmartRange(initP, 'p'),
      i: calculateSmartRange(initI, 'i'),
      d: calculateSmartRange(initD, 'd')
    };
  }

  const getRangeForKey = useCallback((key) => {
    const propSchema = schema?.properties?.[key] || schema?.properties?.[key.toUpperCase()];
    const smartRange = initialRangesRef.current[key];

    return {
      min: propSchema?.minimum ?? smartRange.min,
      max: propSchema?.maximum ?? smartRange.max,
      step: propSchema?.step ?? smartRange.step
    };
  }, [schema?.properties]);

  const handleFieldChange = useCallback((key, newValue) => {
    onChange({
      ...normalizedValue,
      [key]: newValue
    });
  }, [normalizedValue, onChange]);

  return (
    <Box sx={{ width: effectiveMobile ? '100%' : 'auto' }}>
      {showLabel && label && (
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
          {label}
        </Typography>
      )}

      <Box sx={{
        display: 'flex',
        flexDirection: effectiveMobile ? 'column' : 'row',
        gap: compact ? 0.5 : (effectiveMobile ? 2 : 1),
        alignItems: 'flex-start',
        width: effectiveMobile ? '100%' : 'auto'
      }}>
        <PIDField
          label="P"
          value={normalizedValue.p}
          onChange={(v) => handleFieldChange('p', v)}
          color={PID_COLORS.p}
          range={getRangeForKey('p')}
          disabled={disabled}
          compact={compact}
          showSlider={effectiveShowSliders}
          mobileMode={effectiveMobile}
        />
        <PIDField
          label="I"
          value={normalizedValue.i}
          onChange={(v) => handleFieldChange('i', v)}
          color={PID_COLORS.i}
          range={getRangeForKey('i')}
          disabled={disabled}
          compact={compact}
          showSlider={effectiveShowSliders}
          mobileMode={effectiveMobile}
        />
        <PIDField
          label="D"
          value={normalizedValue.d}
          onChange={(v) => handleFieldChange('d', v)}
          color={PID_COLORS.d}
          range={getRangeForKey('d')}
          disabled={disabled}
          compact={compact}
          showSlider={effectiveShowSliders}
          mobileMode={effectiveMobile}
        />

        {!compact && (
          <Tooltip title={showSlidersLocal ? 'Hide sliders' : 'Show sliders'}>
            <IconButton
              size="small"
              onClick={() => setShowSlidersLocal(!showSlidersLocal)}
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
