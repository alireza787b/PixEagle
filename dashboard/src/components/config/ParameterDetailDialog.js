// dashboard/src/components/config/ParameterDetailDialog.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Box, Typography, Button, TextField, Switch, Select, MenuItem,
  FormControl, FormControlLabel, InputLabel, Chip, Divider,
  CircularProgress, Alert, IconButton, Tooltip, Slider
} from '@mui/material';
import {
  Close, Save, Undo, RestartAlt, Info, Warning, Edit
} from '@mui/icons-material';

import { useResponsive } from '../../hooks/useResponsive';
import SmartValueEditor from './SmartValueEditor';
import SafetyLimitsEditor from './SafetyLimitsEditor';
import { ReloadTierChip } from './ReloadTierBadge';

/**
 * Deep equality comparison for detecting modified values
 */
const isDeepEqual = (a, b) => {
  if (a === b) return true;
  if (a === null || b === null) return a === b;
  if (a === undefined || b === undefined) return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return a === b;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    return a.every((item, i) => isDeepEqual(item, b[i]));
  }
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => isDeepEqual(a[key], b[key]));
};

/**
 * Format value compactly for mobile chips (max 20 chars)
 */
const formatCompactValue = (value) => {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'string') return value.length > 15 ? value.slice(0, 15) + '...' : value;
  if (Array.isArray(value)) return `[${value.length} items]`;
  if (typeof value === 'object') return `{${Object.keys(value).length} props}`;
  return String(value).slice(0, 20);
};

/**
 * ParameterDetailDialog - Full-featured parameter editing modal
 *
 * Features:
 * - Full description display
 * - Large, type-appropriate input
 * - Current vs Default comparison
 * - Min/max/step constraints display
 * - Unit information
 * - Restart requirement badge
 * - Inline validation errors
 * - Save / Reset to Default / Cancel buttons
 */
const ParameterDetailDialog = ({
  open,
  onClose,
  param,
  paramSchema,
  currentValue,
  defaultValue,
  onSave,
  onRevert,
  saving = false,
  configValues = {}
}) => {
  const { isMobile, buttonSize, iconButtonSize } = useResponsive();
  const [localValue, setLocalValue] = useState(currentValue);
  const [error, setError] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [customMode, setCustomMode] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const prevParamRef = useRef(null);

  // Reset local state when dialog opens with new param
  // Use a ref to track previous param to avoid race conditions
  useEffect(() => {
    if (open && param) {
      // Only reset if param changed or dialog just opened
      if (prevParamRef.current !== param) {
        prevParamRef.current = param;
        setIsInitialized(false);
      }
    } else if (!open) {
      prevParamRef.current = null;
      setIsInitialized(false);
    }
  }, [open, param]);

  // Initialize value once currentValue is available
  useEffect(() => {
    if (open && param && currentValue !== undefined && !isInitialized) {
      setLocalValue(currentValue);
      setError(null);
      setHasChanges(false);
      setCustomMode(false);
      setIsInitialized(true);
    }
  }, [open, param, currentValue, isInitialized]);

  // Track changes using deep comparison
  useEffect(() => {
    if (isInitialized) {
      setHasChanges(!isDeepEqual(localValue, currentValue));
    }
  }, [localValue, currentValue, isInitialized]);

  const type = paramSchema?.type || 'string';
  const isModified = !isDeepEqual(currentValue, defaultValue);
  const hasConstraints = paramSchema?.min !== undefined || paramSchema?.max !== undefined;

  // Validate value based on schema constraints
  const validateValue = useCallback((value) => {
    if (type === 'integer' || type === 'float') {
      const numValue = type === 'integer' ? parseInt(value, 10) : parseFloat(value);
      if (isNaN(numValue)) {
        return 'Must be a valid number';
      }
      if (paramSchema?.min !== undefined && numValue < paramSchema.min) {
        return `Value must be at least ${paramSchema.min}`;
      }
      if (paramSchema?.max !== undefined && numValue > paramSchema.max) {
        return `Value must be at most ${paramSchema.max}`;
      }
    }
    return null;
  }, [type, paramSchema]);

  const handleValueChange = (newValue) => {
    setLocalValue(newValue);
    const validationError = validateValue(newValue);
    setError(validationError);
  };

  const handleSave = () => {
    if (error) return;
    onSave(param, localValue);
  };

  const handleRevert = () => {
    onRevert(param);
    onClose();
  };

  const handleClose = () => {
    if (hasChanges) {
      // Could show confirmation, but for now just close
    }
    onClose();
  };

  // Format display value for different types
  const formatDisplayValue = (value) => {
    if (value === null || value === undefined) return 'null';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value);
  };

  // Render input based on type
  const renderInput = () => {
    // Boolean toggle
    if (type === 'boolean') {
      return (
        <FormControlLabel
          control={
            <Switch
              checked={Boolean(localValue)}
              onChange={(e) => handleValueChange(e.target.checked)}
              color="primary"
              disabled={saving}
            />
          }
          label={localValue ? 'Enabled' : 'Disabled'}
          sx={{ mt: 2 }}
        />
      );
    }

    // Enum/Select
    if (type === 'enum' || paramSchema?.options) {
      const options = paramSchema?.options || [];
      const isValueInOptions = options.some(opt => (opt.value || opt) === localValue);

      // Custom mode: show text field
      if (customMode) {
        return (
          <Box sx={{ mt: 2 }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
              <TextField
                fullWidth
                label="Custom Value"
                value={localValue ?? ''}
                onChange={(e) => handleValueChange(e.target.value)}
                disabled={saving}
                placeholder="Enter custom value..."
                helperText="Enter any value not in the predefined list"
              />
              <Tooltip title="Switch to dropdown">
                <IconButton
                  onClick={() => setCustomMode(false)}
                  sx={{ mt: 1 }}
                >
                  <Close />
                </IconButton>
              </Tooltip>
            </Box>

            {/* Show available options for reference */}
            <Box sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="subtitle2" gutterBottom>
                Predefined Options (for reference)
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                {options.map((opt) => (
                  <Chip
                    key={opt.value || opt}
                    label={opt.label || opt}
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      handleValueChange(opt.value || opt);
                      setCustomMode(false);
                    }}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Box>
            </Box>
          </Box>
        );
      }

      return (
        <Box sx={{ mt: 2 }}>
          <FormControl fullWidth>
            <InputLabel>Value</InputLabel>
            <Select
              value={isValueInOptions ? localValue : '__custom_current__'}
              onChange={(e) => {
                if (e.target.value === '__custom__') {
                  setCustomMode(true);
                } else if (e.target.value !== '__custom_current__') {
                  handleValueChange(e.target.value);
                }
              }}
              label="Value"
              disabled={saving}
              renderValue={(selected) => {
                if (selected === '__custom_current__') {
                  return `${localValue} (custom)`;
                }
                const opt = options.find(o => (o.value || o) === selected);
                return opt?.label || opt || selected;
              }}
            >
              {/* Show current custom value if not in options */}
              {!isValueInOptions && localValue && (
                <MenuItem value="__custom_current__" sx={{ bgcolor: 'action.selected' }}>
                  <Box>
                    <Typography variant="body1" fontWeight={500}>
                      {localValue}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Current custom value
                    </Typography>
                  </Box>
                </MenuItem>
              )}
              {!isValueInOptions && localValue && <Divider />}

              {options.map((opt) => (
                <MenuItem
                  key={opt.value || opt}
                  value={opt.value || opt}
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    py: opt.description ? 1.5 : 1
                  }}
                >
                  <Typography variant="body1" fontWeight={500}>
                    {opt.label || opt}
                  </Typography>
                  {opt.description && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ mt: 0.5 }}
                    >
                      {opt.description}
                    </Typography>
                  )}
                </MenuItem>
              ))}

              {/* Custom value option */}
              <Divider />
              <MenuItem value="__custom__">
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Edit fontSize="small" color="primary" />
                  <Typography color="primary" fontStyle="italic">
                    Enter custom value...
                  </Typography>
                </Box>
              </MenuItem>
            </Select>
          </FormControl>

          {/* Available Options List */}
          {options.some(opt => opt.description) && (
            <Box sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="subtitle2" gutterBottom>
                Available Options
              </Typography>
              {options.map((opt) => (
                <Box
                  key={opt.value || opt}
                  sx={{
                    py: 0.75,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    '&:last-child': { borderBottom: 'none' }
                  }}
                >
                  <Typography variant="body2" fontWeight={500}>
                    {opt.label || opt}
                    {(opt.value || opt) === localValue && (
                      <Chip label="Selected" size="small" color="primary" sx={{ ml: 1 }} />
                    )}
                  </Typography>
                  {opt.description && (
                    <Typography variant="caption" color="text.secondary">
                      {opt.description}
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      );
    }

    // Integer with slider (if has min/max)
    if (type === 'integer' && hasConstraints && paramSchema.max - paramSchema.min <= 1000) {
      return (
        <Box sx={{ mt: 2 }}>
          <TextField
            fullWidth
            type="number"
            label="Value"
            value={localValue ?? ''}
            onChange={(e) => handleValueChange(parseInt(e.target.value, 10) || 0)}
            error={!!error}
            helperText={error || `Range: ${paramSchema.min} - ${paramSchema.max}${paramSchema.unit ? ` ${paramSchema.unit}` : ''}`}
            disabled={saving}
            inputProps={{
              min: paramSchema.min,
              max: paramSchema.max,
              step: 1
            }}
          />
          <Slider
            value={localValue ?? paramSchema.min}
            onChange={(_, newValue) => handleValueChange(newValue)}
            min={paramSchema.min}
            max={paramSchema.max}
            step={1}
            marks={[
              { value: paramSchema.min, label: String(paramSchema.min) },
              { value: paramSchema.max, label: String(paramSchema.max) }
            ]}
            valueLabelDisplay="auto"
            disabled={saving}
            sx={{ mt: 2 }}
          />
        </Box>
      );
    }

    // Float with slider (if has min/max)
    if (type === 'float' && hasConstraints) {
      const step = paramSchema.step || 0.1;
      return (
        <Box sx={{ mt: 2 }}>
          <TextField
            fullWidth
            type="number"
            label="Value"
            value={localValue ?? ''}
            onChange={(e) => handleValueChange(parseFloat(e.target.value) || 0)}
            error={!!error}
            helperText={error || `Range: ${paramSchema.min} - ${paramSchema.max}${paramSchema.unit ? ` ${paramSchema.unit}` : ''}`}
            disabled={saving}
            inputProps={{
              min: paramSchema.min,
              max: paramSchema.max,
              step: step
            }}
          />
          <Slider
            value={localValue ?? paramSchema.min}
            onChange={(_, newValue) => handleValueChange(newValue)}
            min={paramSchema.min}
            max={paramSchema.max}
            step={step}
            marks={[
              { value: paramSchema.min, label: String(paramSchema.min) },
              { value: paramSchema.max, label: String(paramSchema.max) }
            ]}
            valueLabelDisplay="auto"
            disabled={saving}
            sx={{ mt: 2 }}
          />
        </Box>
      );
    }

    // Integer without slider
    if (type === 'integer') {
      return (
        <TextField
          fullWidth
          type="number"
          label="Value"
          value={localValue ?? ''}
          onChange={(e) => handleValueChange(parseInt(e.target.value, 10) || 0)}
          error={!!error}
          helperText={error || (hasConstraints ? `Range: ${paramSchema.min ?? '-∞'} - ${paramSchema.max ?? '∞'}` : undefined)}
          disabled={saving}
          sx={{ mt: 2 }}
          inputProps={{
            min: paramSchema?.min,
            max: paramSchema?.max,
            step: 1
          }}
        />
      );
    }

    // Float without slider
    if (type === 'float') {
      return (
        <TextField
          fullWidth
          type="number"
          label="Value"
          value={localValue ?? ''}
          onChange={(e) => handleValueChange(parseFloat(e.target.value) || 0)}
          error={!!error}
          helperText={error || (hasConstraints ? `Range: ${paramSchema.min ?? '-∞'} - ${paramSchema.max ?? '∞'}` : undefined)}
          disabled={saving}
          sx={{ mt: 2 }}
          inputProps={{
            min: paramSchema?.min,
            max: paramSchema?.max,
            step: paramSchema?.step || 0.1
          }}
        />
      );
    }

    // Array - use SmartValueEditor
    if (type === 'array') {
      return (
        <Box sx={{ mt: 2 }}>
          <SmartValueEditor
            value={localValue}
            onChange={handleValueChange}
            schema={paramSchema}
            mode="full"
            disabled={saving}
            showUndoRedo={!isMobile}
            label="Array Value"
          />
        </Box>
      );
    }

    // Object - use SafetyLimitsEditor for GlobalLimits/FollowerOverrides, SmartValueEditor for others
    if (type === 'object') {
      const isSafetyParam = param === 'GlobalLimits' || param === 'FollowerOverrides';

      if (isSafetyParam) {
        return (
          <Box sx={{ mt: 2 }}>
            <SafetyLimitsEditor
              type={param}
              value={localValue || {}}
              onChange={handleValueChange}
              globalLimits={param === 'FollowerOverrides' ? (configValues?.GlobalLimits || {}) : {}}
              disabled={saving}
            />
          </Box>
        );
      }

      return (
        <Box sx={{ mt: 2 }}>
          <SmartValueEditor
            value={localValue}
            onChange={handleValueChange}
            schema={paramSchema}
            mode="full"
            disabled={saving}
            showUndoRedo={!isMobile}
            label="Object Value"
          />
        </Box>
      );
    }

    // Default: string input
    return (
      <TextField
        fullWidth
        label="Value"
        value={localValue ?? ''}
        onChange={(e) => handleValueChange(e.target.value)}
        error={!!error}
        helperText={error}
        disabled={saving}
        sx={{ mt: 2 }}
      />
    );
  };

  if (!param) return null;

  // Show loading state while initializing
  const showLoading = !isInitialized && open;

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth={isMobile ? "xs" : "sm"}
      fullWidth
      fullScreen={isMobile}
      sx={{
        '& .MuiDialog-paper': {
          maxWidth: isMobile ? '100vw' : '600px',
          m: isMobile ? 0 : 2
        }
      }}
    >
      <DialogTitle sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        p: isMobile ? 1.5 : 2
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
          <Typography
            variant={isMobile ? "subtitle1" : "h6"}
            component="span"
            sx={{
              fontFamily: 'monospace',
              wordBreak: 'break-word',
              maxWidth: isMobile ? '70%' : '100%'
            }}
          >
            {param}
          </Typography>
          {paramSchema?.reload_tier && (
            <ReloadTierChip tier={paramSchema.reload_tier} size="small" showLabel={!isMobile} />
          )}
        </Box>
        <IconButton onClick={handleClose} size={iconButtonSize}>
          <Close />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: isMobile ? 1.5 : 2 }}>
        {showLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* Description */}
            {paramSchema?.description && (
              <Alert severity="info" icon={<Info />} sx={{ mb: 2 }}>
                <Typography variant="body2">{paramSchema.description}</Typography>
              </Alert>
            )}

            {/* INPUT FIRST - Primary action */}
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                mb: 1
              }}>
                New Value
                {isModified && (
                  <Chip
                    label="Modified"
                    color="warning"
                    size="small"
                    icon={<Warning fontSize="small" />}
                  />
                )}
              </Typography>
              {renderInput()}
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* Type and constraints info - Show on desktop */}
            {!isMobile && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                <Chip label={`Type: ${type}`} size="small" variant="outlined" />
                {paramSchema?.unit && (
                  <Chip label={`Unit: ${paramSchema.unit}`} size="small" variant="outlined" />
                )}
                {paramSchema?.min !== undefined && (
                  <Chip label={`Min: ${paramSchema.min}`} size="small" variant="outlined" />
                )}
                {paramSchema?.max !== undefined && (
                  <Chip label={`Max: ${paramSchema.max}`} size="small" variant="outlined" />
                )}
                {paramSchema?.step && (
                  <Chip label={`Step: ${paramSchema.step}`} size="small" variant="outlined" />
                )}
              </Box>
            )}

            {/* Current/Default - Secondary info */}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Reference Values
            </Typography>

            {isMobile ? (
              // Mobile: Compact chips
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label={`Current: ${formatCompactValue(currentValue)}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontFamily: 'monospace' }}
                />
                <Chip
                  label={`Default: ${formatCompactValue(defaultValue)}`}
                  size="small"
                  variant="outlined"
                  color="default"
                  sx={{ fontFamily: 'monospace' }}
                />
              </Box>
            ) : (
              // Desktop: Full comparison boxes
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    Current Value
                  </Typography>
                  <Typography variant="body2" sx={{
                    fontFamily: 'monospace',
                    bgcolor: isModified ? 'warning.light' : 'action.hover',
                    color: isModified ? 'warning.contrastText' : 'text.primary',
                    p: 1,
                    borderRadius: 1,
                    fontSize: '0.85rem',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}>
                    {formatDisplayValue(currentValue)}
                  </Typography>
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    Default Value
                  </Typography>
                  <Typography variant="body2" sx={{
                    fontFamily: 'monospace',
                    bgcolor: 'action.hover',
                    p: 1,
                    borderRadius: 1,
                    fontSize: '0.85rem',
                    overflowX: 'auto',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}>
                    {formatDisplayValue(defaultValue)}
                  </Typography>
                </Box>
              </Box>
            )}

            {hasChanges && !error && (
              <Alert severity="info" sx={{ mt: 2 }}>
                Click "Save" to apply this change.
              </Alert>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions sx={{
        p: isMobile ? 1.5 : 2,
        gap: 1,
        flexWrap: 'wrap'
      }}>
        {isModified && (
          <Button
            onClick={handleRevert}
            startIcon={<Undo />}
            color="warning"
            disabled={saving}
            size={buttonSize}
          >
            Reset to Default
          </Button>
        )}
        <Box sx={{ flex: 1 }} />
        <Button
          onClick={handleClose}
          disabled={saving}
          size={buttonSize}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          startIcon={saving ? <CircularProgress size={16} /> : <Save />}
          disabled={saving || !!error || !hasChanges}
          size={buttonSize}
        >
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ParameterDetailDialog;
