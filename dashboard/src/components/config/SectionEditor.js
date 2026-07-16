// dashboard/src/components/config/SectionEditor.js
import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';
import {
  Box, Paper, Typography, CircularProgress, Alert, Button, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, Chip, TextField, Switch, Select, MenuItem,
  FormControl, Card, CardContent
} from '@mui/material';
import {
  Refresh, Undo, Save, Check, Error as ErrorIcon, OpenInNew, Edit
} from '@mui/icons-material';

import { useConfigSection } from '../../hooks/useConfig';
import { useResponsive } from '../../hooks/useResponsive';
import { useConfigGlobalState } from '../../hooks/useConfigGlobalState';
import { parseCommittedNumeric } from '../../utils/numericInput';
import {
  isEditableSchemaContract,
  readOnlySchemaForValue,
} from '../../utils/configEditorSchemaUtils';
import ParameterDetailDialog from './ParameterDetailDialog';
import SmartValueEditor from './SmartValueEditor';
import SafetyLimitsEditor from './SafetyLimitsEditor';
import FollowerConfigEditor from './FollowerConfigEditor';
import { ReloadTierChip } from './ReloadTierBadge';

/**
 * Deep equality comparison for detecting modified values
 * Handles objects, arrays, primitives correctly
 */
const isDeepEqual = (a, b) => {
  if (a === b) return true;
  if (a === null || b === null) return a === b;
  if (a === undefined || b === undefined) return a === b;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return a === b;

  // Arrays
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    if (a.length !== b.length) return false;
    return a.every((item, i) => isDeepEqual(item, b[i]));
  }

  // Objects
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every(key => isDeepEqual(a[key], b[key]));
};

const optionValue = (option) => (
  option && typeof option === 'object' ? option.value : option
);

const optionLabel = (option) => (
  option && typeof option === 'object' ? (option.label || String(option.value)) : String(option)
);

const formatReadOnlyValue = (value) => {
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

// Type-specific input component with proper ref tracking
const ParameterInput = ({
  param,
  schema,
  value,
  defaultValue,
  onChange,
  onAutoSave,
  saveStatus,
  mobileMode = false,
  configValues = {},
  autoSaveEnabled = true,
  disabled = false,
}) => {
  const { touchTargetSize } = useResponsive();
  const paramSchema = schema?.parameters?.[param] || {};
  const type = paramSchema.type || 'string';
  const minValue = paramSchema.min;
  const maxValue = paramSchema.max;
  const unitLabel = paramSchema.unit;
  // Use schema default as fallback when value is undefined (missing from config)
  const effectiveValue = value !== undefined ? value : defaultValue;
  // Only show "Modified" when value is explicitly set and differs from default
  const isModified = value !== undefined && !isDeepEqual(value, defaultValue);
  const isNumericType = type === 'integer' || type === 'float' || type === 'number';
  const controlsDisabled = disabled || saveStatus === 'saving';
  const formatInputValue = useCallback((nextValue) => {
    if (!isNumericType) return nextValue;
    if (nextValue === null || nextValue === undefined) return '';
    return String(nextValue);
  }, [isNumericType]);

  // Use ref to track current input value for blur handling (must be called unconditionally)
  const currentValueRef = useRef(formatInputValue(effectiveValue));
  const [localInput, setLocalInput] = useState(() => formatInputValue(effectiveValue));
  const [isFocused, setIsFocused] = useState(false);
  const [validationError, setValidationError] = useState(null);

  // Sync local input with prop value when it changes externally
  useEffect(() => {
    if (!isNumericType || !isFocused) {
      const nextValue = formatInputValue(effectiveValue);
      setLocalInput(nextValue);
      currentValueRef.current = nextValue;
    }
    setValidationError(null);
  }, [effectiveValue, isNumericType, formatInputValue, isFocused]);

  // Validate value based on schema constraints
  const validateValue = useCallback((val) => {
    if (isNumericType) {
      if (!Number.isFinite(val)) return 'Invalid number';
      if (minValue !== undefined && val < minValue) {
        return `Min: ${minValue}`;
      }
      if (maxValue !== undefined && val > maxValue) {
        return `Max: ${maxValue}`;
      }
    }
    return null;
  }, [isNumericType, minValue, maxValue]);

  // Build helper text showing constraints
  const getHelperText = () => {
    if (validationError) return validationError;
    if (isNumericType) {
      const parts = [];
      if (minValue !== undefined) parts.push(`Min: ${minValue}`);
      if (maxValue !== undefined) parts.push(`Max: ${maxValue}`);
      if (unitLabel) parts.push(unitLabel);
      return parts.length > 0 ? parts.join(' | ') : undefined;
    }
    return undefined;
  };

  const handleInputChange = (newValue) => {
    if (controlsDisabled) return;
    setLocalInput(newValue);
    currentValueRef.current = newValue;
    const error = validateValue(newValue);
    setValidationError(error);
    onChange(param, newValue);
  };

  const saveIfAutoEnabled = (newValue) => {
    if (autoSaveEnabled) {
      onAutoSave(param, newValue);
    }
  };

  const scheduleSaveIfAutoEnabled = (newValue) => {
    if (autoSaveEnabled) {
      onAutoSave(param, newValue);
    }
  };

  const handleNonNumericBlur = () => {
    // Only auto-save on blur if autoSaveEnabled is true
    if (!autoSaveEnabled) return;

    const currentValue = currentValueRef.current;
    // Only save if value actually changed and no validation error
    if (!validationError && (currentValue !== value || (currentValue !== defaultValue && saveStatus !== 'saved'))) {
      onAutoSave(param, currentValue);
    }
  };

  const handleNumericInputChange = (rawValue) => {
    setLocalInput(rawValue);
    currentValueRef.current = rawValue;

    const parsed = parseCommittedNumeric(rawValue, type);
    if (!parsed.valid) {
      setValidationError(parsed.transient ? null : 'Invalid number');
      return;
    }

    const error = validateValue(parsed.value);
    setValidationError(error);
    if (!error) {
      onChange(param, parsed.value);
    }
  };

  const handleNumericBlur = () => {
    setIsFocused(false);
    const parsed = parseCommittedNumeric(currentValueRef.current, type);
    if (!parsed.valid) {
      const restored = formatInputValue(value);
      setLocalInput(restored);
      currentValueRef.current = restored;
      setValidationError('Invalid number');
      return;
    }

    const numericValue = parsed.value;
    const error = validateValue(numericValue);
    setValidationError(error);
    if (error) return;

    const normalized = formatInputValue(numericValue);
    setLocalInput(normalized);
    currentValueRef.current = normalized;
    onChange(param, numericValue);

    if (!autoSaveEnabled) return;
    if (!isDeepEqual(numericValue, value) || (!isDeepEqual(numericValue, defaultValue) && saveStatus !== 'saved')) {
      onAutoSave(param, numericValue);
    }
  };

  // Check if numeric value is outside recommended range (soft warning)
  const isOutsideRecommended = isNumericType && typeof value === 'number' && (
    (paramSchema.recommended_min != null && value < paramSchema.recommended_min) ||
    (paramSchema.recommended_max != null && value > paramSchema.recommended_max)
  );

  // Determine border color based on save status
  const getBorderColor = () => {
    if (saveStatus === 'saving') return 'info.main';
    if (saveStatus === 'saved') return 'success.main';
    if (saveStatus === 'error') return 'error.main';
    if (isOutsideRecommended) return '#ed6c02'; // amber/orange for recommended range warning
    if (isModified) return 'warning.main';
    return undefined;
  };

  const inputSx = {
    width: '100%',
    maxWidth: mobileMode ? '100%' : 200,
    '& .MuiOutlinedInput-root': {
      bgcolor: isModified ? 'action.hover' : undefined,
      borderColor: getBorderColor(),
      minHeight: touchTargetSize === 'medium' ? 44 : 'auto',
      '& fieldset': {
        borderColor: getBorderColor(),
        borderWidth: saveStatus ? 2 : 1
      }
    }
  };

  // Special handling for Safety section GlobalLimits and FollowerOverrides
  // Disambiguate from Follower section's FollowerOverrides using configValues keys
  const isSafetyParameter = (param === 'GlobalLimits' || (param === 'FollowerOverrides' && 'GlobalLimits' in configValues));
  if (isSafetyParameter && type === 'object') {
    const safetyType = param === 'GlobalLimits' ? 'GlobalLimits' : 'FollowerOverrides';
    const globalLimits = param === 'FollowerOverrides' ? (configValues.GlobalLimits || {}) : {};

    return (
      <Box sx={{ width: '100%' }}>
        <SafetyLimitsEditor
          type={safetyType}
          value={value || {}}
          schema={paramSchema}
          referenceSchema={schema?.parameters?.GlobalLimits}
          onChange={(newVal) => {
            onChange(param, newVal);
            scheduleSaveIfAutoEnabled(newVal);
          }}
          globalLimits={globalLimits}
          disabled={controlsDisabled}
        />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
          {saveStatus === 'saving' && <CircularProgress size={16} />}
          {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
          {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
        </Box>
      </Box>
    );
  }

  // Special handling for Follower section General and FollowerOverrides
  const isFollowerConfigParameter = (param === 'General' && 'General' in configValues) ||
    (param === 'FollowerOverrides' && 'General' in configValues);
  if (isFollowerConfigParameter && type === 'object') {
    const followerType = param === 'General' ? 'General' : 'FollowerOverrides';
    const generalDefaults = param === 'FollowerOverrides' ? (configValues.General || {}) : {};

    return (
      <Box sx={{ width: '100%' }}>
        <FollowerConfigEditor
          type={followerType}
          value={value || {}}
          schema={paramSchema}
          referenceSchema={schema?.parameters?.General}
          onChange={(newVal) => {
            onChange(param, newVal);
            scheduleSaveIfAutoEnabled(newVal);
          }}
          generalDefaults={generalDefaults}
          disabled={controlsDisabled}
        />
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
          {saveStatus === 'saving' && <CircularProgress size={16} />}
          {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
          {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
        </Box>
      </Box>
    );
  }

  // Boolean toggle - immediate save
  if (type === 'boolean') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Switch
          checked={Boolean(localInput)}
          onChange={(e) => {
            const newVal = e.target.checked;
            handleInputChange(newVal);
            saveIfAutoEnabled(newVal);
          }}
          color={isModified ? 'warning' : 'primary'}
          disabled={controlsDisabled}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      </Box>
    );
  }

  // Integer input
  if (type === 'integer') {
    const helperText = getHelperText();
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
        <TextField
          type="number"
          size={touchTargetSize}
          fullWidth={mobileMode}
          value={localInput ?? ''}
          onChange={(e) => handleNumericInputChange(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={handleNumericBlur}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleNumericBlur();
            }
          }}
          disabled={controlsDisabled}
          error={!!validationError}
          helperText={helperText}
          inputProps={{
            min: paramSchema.min,
            max: paramSchema.max,
            step: 1
          }}
          sx={inputSx}
          FormHelperTextProps={{ sx: { fontSize: '0.65rem', mt: 0.5 } }}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  // Float input
  if (type === 'float') {
    const helperText = getHelperText();
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
        <TextField
          type="number"
          size={touchTargetSize}
          fullWidth={mobileMode}
          value={localInput ?? ''}
          onChange={(e) => handleNumericInputChange(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={handleNumericBlur}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleNumericBlur();
            }
          }}
          disabled={controlsDisabled}
          error={!!validationError}
          helperText={helperText}
          inputProps={{
            min: paramSchema.min,
            max: paramSchema.max,
            step: paramSchema.step || 0.1
          }}
          sx={inputSx}
          FormHelperTextProps={{ sx: { fontSize: '0.65rem', mt: 0.5 } }}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  // Enum/Select - custom values are available only when the schema opts in.
  if (type === 'enum' || paramSchema.options) {
    const options = paramSchema.options || [];
    const isValueInOptions = options.some(opt => optionValue(opt) === localInput);
    const allowCustomValues = paramSchema.allow_custom_values === true;
    const hasCurrentValue = localInput !== '' && localInput !== null && localInput !== undefined;
    const outOfContract = hasCurrentValue && !isValueInOptions && !allowCustomValues;
    const enumDisabled = controlsDisabled || outOfContract;

    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
        <FormControl size={touchTargetSize} fullWidth={mobileMode} sx={{ minWidth: 0, maxWidth: '100%', width: '100%' }}>
          <Select
            value={isValueInOptions ? localInput : (localInput ? '__custom_current__' : '')}
            onChange={(e) => {
              const newVal = e.target.value;
              if (newVal === '__custom__') {
                // Prompt for custom value
                const customVal = window.prompt('Enter custom value:', localInput || '');
                if (customVal !== null && customVal !== '') {
                  handleInputChange(customVal);
                  saveIfAutoEnabled(customVal);
                }
              } else if (newVal !== '__custom_current__') {
                handleInputChange(newVal);
                saveIfAutoEnabled(newVal);
              }
            }}
            disabled={enumDisabled}
            sx={{
              bgcolor: isModified ? 'action.hover' : undefined
            }}
            renderValue={(selected) => {
              if (selected === '__custom_current__') {
                return `${localInput} (custom)`;
              }
              const opt = options.find(o => optionValue(o) === selected);
              return opt ? optionLabel(opt) : selected;
            }}
          >
            {/* Show current custom value if not in options */}
            {!isValueInOptions && localInput && (
              <MenuItem value="__custom_current__" sx={{ bgcolor: 'action.selected' }}>
                <Box>
                  <Typography variant="body2" fontWeight={500}>
                    {localInput}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Current custom value
                  </Typography>
                </Box>
              </MenuItem>
            )}
            {!isValueInOptions && localInput && <Divider />}

            {options.map((opt) => (
              <MenuItem
                key={String(optionValue(opt))}
                value={optionValue(opt)}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  py: opt.description ? 1 : 0.5
                }}
              >
                <Typography variant="body2" fontWeight={500}>
                  {optionLabel(opt)}
                </Typography>
                {opt.description && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mt: 0.25 }}
                  >
                    {opt.description}
                  </Typography>
                )}
              </MenuItem>
            ))}

            {allowCustomValues && <Divider />}
            {allowCustomValues && (
              <MenuItem value="__custom__">
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Edit fontSize="small" color="primary" />
                  <Typography color="primary" fontStyle="italic" variant="body2">
                    Enter custom value...
                  </Typography>
                </Box>
              </MenuItem>
            )}
          </Select>
        </FormControl>
        {outOfContract && (
          <Chip label="Needs migration" size="small" color="warning" variant="outlined" />
        )}
        {saveStatus === 'saving' && <CircularProgress size={16} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      </Box>
    );
  }

  // Array input - use SmartValueEditor inline
  if (type === 'array' && isEditableSchemaContract(paramSchema)) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, width: '100%' }}>
        <SmartValueEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
            scheduleSaveIfAutoEnabled(newVal);
          }}
          schema={paramSchema}
          mode="inline"
          disabled={controlsDisabled}
          showUndoRedo={false}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  // Object input - use SmartValueEditor inline
  if (type === 'object' && isEditableSchemaContract(paramSchema)) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, width: '100%' }}>
        <SmartValueEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
            scheduleSaveIfAutoEnabled(newVal);
          }}
          schema={paramSchema}
          mode="inline"
          disabled={controlsDisabled}
          showUndoRedo={false}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  if (!['string', 'boolean', 'integer', 'float', 'number', 'enum'].includes(type)) {
    return (
      <TextField
        fullWidth
        multiline
        minRows={2}
        maxRows={8}
        value={formatReadOnlyValue(effectiveValue)}
        disabled
        helperText={paramSchema.read_only_reason || 'Structured value is read-only without a complete schema contract'}
        sx={{ maxWidth: '100%' }}
      />
    );
  }

  // String input
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
      <TextField
        size={touchTargetSize}
        fullWidth={mobileMode}
        value={localInput ?? ''}
        onChange={(e) => handleInputChange(e.target.value)}
        onBlur={handleNonNumericBlur}
        onKeyDown={(e) => e.key === 'Enter' && handleNonNumericBlur()}
        disabled={controlsDisabled}
        sx={{ ...inputSx, width: '100%', maxWidth: mobileMode ? '100%' : 200 }}
      />
      {saveStatus === 'saving' && <CircularProgress size={16} />}
      {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
    </Box>
  );
};

// Mobile card component for parameter display
const ParameterCard = ({
  param,
  schema,
  value,
  defaultValue,
  saveStatus,
  onLocalChange,
  onAutoSave,
  onRevert,
  onOpenDetails,
  configValues = {},
  autoSaveEnabled = true,
  disabled = false,
}) => {
  const { buttonSize } = useResponsive();
  const paramSchema = schema?.parameters?.[param] || {};
  // Only show "Modified" when value is explicitly set and differs from default
  const isModified = value !== undefined && !isDeepEqual(value, defaultValue);

  return (
    <Card
      variant="outlined"
      data-param={param}
      sx={{
        mb: 2,
        bgcolor: isModified ? 'action.selected' : 'background.paper',
        borderColor: isModified ? 'warning.main' : 'divider',
        borderWidth: isModified ? 2 : 1
      }}
    >
      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
        {/* Header: Parameter Name */}
        <Typography variant="subtitle1" sx={{ fontFamily: 'monospace', mb: 0.5, fontWeight: 600 }}>
          {param}
        </Typography>

        {/* Description */}
        {paramSchema?.description && (
          <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: 'block' }}>
            {paramSchema.description}
          </Typography>
        )}

        {/* Value Input - 100% width on mobile */}
        <Box sx={{ mb: 2 }}>
          <ParameterInput
            param={param}
            schema={schema}
            value={value}
            defaultValue={defaultValue}
            onChange={onLocalChange}
            onAutoSave={onAutoSave}
            saveStatus={saveStatus}
            mobileMode={true}
            configValues={configValues}
            autoSaveEnabled={autoSaveEnabled}
            disabled={disabled}
          />
        </Box>

        {/* Info Chips */}
        {(paramSchema?.reload_tier || paramSchema?.unit || isModified) && (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
            {paramSchema?.reload_tier && (
              <ReloadTierChip tier={paramSchema.reload_tier} size="small" />
            )}
            {paramSchema?.unit && (
              <Chip label={paramSchema.unit} size="small" variant="outlined" />
            )}
            {isModified && (
              <Chip label="Modified" size="small" color="warning" />
            )}
          </Box>
        )}

        {/* Action Buttons - Touch-friendly */}
        <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <Button
            size={buttonSize}
            variant="outlined"
            startIcon={<OpenInNew />}
            onClick={onOpenDetails}
            disabled={disabled}
          >
            Details
          </Button>

          {isModified && (
            <Button
              size={buttonSize}
              variant="outlined"
              startIcon={<Undo />}
              onClick={() => onRevert(param)}
              disabled={disabled || saveStatus === 'saving'}
            >
              Revert
            </Button>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

const SectionEditor = ({ sectionName, highlightParam = null, onHighlightComplete = null, onRebootRequired, onMessage, autoSaveEnabled = true }) => {
  const {
    config,
    defaultConfig,
    schema,
    schemaAvailable,
    schemaError,
    defaultError,
    mutationsAllowed,
    loading,
    error,
    updateParameter,
    revertParameter,
    revertSection,
    refetch
  } = useConfigSection(sectionName);
  const { isMobile, isTablet, isCompactDesktop, compactTable } = useResponsive();
  const globalState = useConfigGlobalState();

  // Use card layout on mobile/tablet/compact-desktop (responsive breakpoint only)
  const useCardLayout = isMobile || isTablet || isCompactDesktop;

  const [localValues, setLocalValues] = useState({});
  const [saveStatuses, setSaveStatuses] = useState({}); // 'saving' | 'saved' | 'error' | null
  const [pendingChanges, setPendingChanges] = useState({}); // Track unsaved changes
  const [selectedParam, setSelectedParam] = useState(null); // For detail dialog
  const containerRef = useRef(null);
  const autoSaveTimersRef = useRef(new Map());
  const saveQueuesRef = useRef(new Map());
  const saveGenerationsRef = useRef(new Map());
  const lifecycleGenerationRef = useRef(0);

  const declaredParameters = useMemo(() => schema?.parameters || {}, [schema]);
  const displayParameters = useMemo(() => {
    const names = new Set([
      ...Object.keys(declaredParameters),
      ...Object.keys(config || {}),
    ]);
    return Object.fromEntries(Array.from(names).map((name) => [
      name,
      declaredParameters[name] || readOnlySchemaForValue(
        config?.[name],
        schemaAvailable
          ? 'Current parameter is not declared by the server schema'
          : (schemaError || 'Server schema is unavailable')
      ),
    ]));
  }, [config, declaredParameters, schemaAvailable, schemaError]);
  const displaySchema = useMemo(() => ({
    ...(schema || {}),
    display_name: schema?.display_name || sectionName,
    parameters: displayParameters,
  }), [schema, sectionName, displayParameters]);

  const isParameterEditable = useCallback((param) => (
    mutationsAllowed
    && Object.prototype.hasOwnProperty.call(declaredParameters, param)
    && isEditableSchemaContract(declaredParameters[param])
  ), [declaredParameters, mutationsAllowed]);

  const clearAutoSaveTimer = useCallback((param) => {
    const timer = autoSaveTimersRef.current.get(param);
    if (timer) clearTimeout(timer);
    autoSaveTimersRef.current.delete(param);
  }, []);

  const nextSaveGeneration = useCallback((param) => {
    const generation = (saveGenerationsRef.current.get(param) || 0) + 1;
    saveGenerationsRef.current.set(param, generation);
    return generation;
  }, []);

  // Scroll to and highlight a parameter when highlightParam changes
  useEffect(() => {
    if (!highlightParam || loading) return;

    const timer = setTimeout(() => {
      const targetEl = containerRef.current?.querySelector(
        `[data-param="${highlightParam}"]`
      );
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        targetEl.classList.add('param-highlight');
        const cleanup = setTimeout(() => {
          targetEl.classList.remove('param-highlight');
          onHighlightComplete?.();
        }, 2000);
        return () => clearTimeout(cleanup);
      } else {
        onHighlightComplete?.();
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [highlightParam, loading, onHighlightComplete]);

  // Clear save statuses after delay
  useEffect(() => {
    const timeouts = {};
    Object.entries(saveStatuses).forEach(([param, status]) => {
      if (status === 'saved') {
        timeouts[param] = setTimeout(() => {
          setSaveStatuses(prev => {
            const updated = { ...prev };
            delete updated[param];
            return updated;
          });
        }, 2000);
      }
    });
    return () => Object.values(timeouts).forEach(clearTimeout);
  }, [saveStatuses]);

  // Reset local state when section changes
  useEffect(() => {
    lifecycleGenerationRef.current += 1;
    autoSaveTimersRef.current.forEach(clearTimeout);
    autoSaveTimersRef.current.clear();
    saveGenerationsRef.current.clear();
    setLocalValues({});
    setSaveStatuses({});
    setPendingChanges({});
    setSelectedParam(null);
  }, [sectionName]);

  useEffect(() => () => {
    lifecycleGenerationRef.current += 1;
    autoSaveTimersRef.current.forEach(clearTimeout);
    autoSaveTimersRef.current.clear();
  }, []);

  const handleLocalChange = useCallback((param, value) => {
    if (!isParameterEditable(param)) return;
    setLocalValues(prev => ({ ...prev, [param]: value }));
    setPendingChanges(prev => ({ ...prev, [param]: value }));
    // Track in global state for status banner
    const oldValue = config[param];
    globalState.registerUnsavedChange?.(sectionName, param, oldValue, value);
  }, [config, sectionName, globalState, isParameterEditable]);

  const enqueueSave = useCallback((param, value, generation) => {
    const lifecycleGeneration = lifecycleGenerationRef.current;
    const preceding = saveQueuesRef.current.get(param) || Promise.resolve();
    const operation = preceding.catch(() => undefined).then(async () => {
      if (
        lifecycleGeneration !== lifecycleGenerationRef.current
        || generation !== saveGenerationsRef.current.get(param)
        || !isParameterEditable(param)
      ) {
        return { success: false, skipped: true };
      }

      setSaveStatuses(prev => ({ ...prev, [param]: 'saving' }));
      globalState.markSectionSaving?.(sectionName);

      try {
        const result = await updateParameter(param, value);
        const isCurrent = lifecycleGeneration === lifecycleGenerationRef.current
          && generation === saveGenerationsRef.current.get(param);
        if (!isCurrent) return result;

        if (result.success && result.saved !== false) {
          setSaveStatuses(prev => ({ ...prev, [param]: 'saved' }));
          setLocalValues(prev => {
            const updated = { ...prev };
            delete updated[param];
            return updated;
          });
          setPendingChanges(prev => {
            const updated = { ...prev };
            delete updated[param];
            return updated;
          });
          globalState.markParamSaved?.(sectionName, param);
          globalState.refreshModifiedCount?.();

          const paramSchema = declaredParameters[param];
          const reloadTier = paramSchema?.reload_tier || 'system_restart';
          if (reloadTier !== 'immediate') {
            onRebootRequired?.(sectionName, param, reloadTier);
          }

          const isSafetyParam = sectionName === 'Safety' || sectionName === 'SafetyLimits';
          onMessage?.(`${param} saved`, 'success', { persistent: isSafetyParam });
        } else {
          setSaveStatuses(prev => ({ ...prev, [param]: 'error' }));
          globalState.markSaveError?.(sectionName, param, result.error || 'Save failed');
          const errorMsg = result.error
            || (result.saved === false ? 'Failed to write to config file' : 'Validation failed');
          onMessage?.(`Error saving ${param}: ${errorMsg}`, 'error');
        }
        return result;
      } catch (err) {
        if (
          lifecycleGeneration === lifecycleGenerationRef.current
          && generation === saveGenerationsRef.current.get(param)
        ) {
          setSaveStatuses(prev => ({ ...prev, [param]: 'error' }));
          globalState.markSaveError?.(sectionName, param, err.message);
          onMessage?.(`Error saving ${param}: ${err.message}`, 'error');
        }
        return { success: false, error: err.message };
      }
    });

    saveQueuesRef.current.set(param, operation);
    operation.finally(() => {
      if (saveQueuesRef.current.get(param) === operation) {
        saveQueuesRef.current.delete(param);
      }
    });
    return operation;
  }, [declaredParameters, globalState, isParameterEditable, onMessage, onRebootRequired, sectionName, updateParameter]);

  const handleSave = useCallback((param, value) => {
    if (!isParameterEditable(param)) {
      return Promise.resolve({ success: false, skipped: true });
    }
    clearAutoSaveTimer(param);
    const generation = nextSaveGeneration(param);
    return enqueueSave(param, value, generation);
  }, [clearAutoSaveTimer, enqueueSave, isParameterEditable, nextSaveGeneration]);

  const handleAutoSave = useCallback((param, value) => {
    if (!autoSaveEnabled || !isParameterEditable(param)) return;
    clearAutoSaveTimer(param);
    const generation = nextSaveGeneration(param);
    const lifecycleGeneration = lifecycleGenerationRef.current;
    const timer = setTimeout(() => {
      autoSaveTimersRef.current.delete(param);
      if (lifecycleGeneration !== lifecycleGenerationRef.current) return;
      enqueueSave(param, value, generation);
    }, 250);
    autoSaveTimersRef.current.set(param, timer);
  }, [autoSaveEnabled, clearAutoSaveTimer, enqueueSave, isParameterEditable, nextSaveGeneration]);

  const handleRevert = useCallback(async (param) => {
    if (!isParameterEditable(param)) return;
    clearAutoSaveTimer(param);
    nextSaveGeneration(param);
    const preceding = saveQueuesRef.current.get(param);
    if (preceding) await preceding.catch(() => undefined);
    const success = await revertParameter(param);
    if (success) {
      setLocalValues(prev => {
        const updated = { ...prev };
        delete updated[param];
        return updated;
      });
      setPendingChanges(prev => {
        const updated = { ...prev };
        delete updated[param];
        return updated;
      });
      setSaveStatuses(prev => ({ ...prev, [param]: 'saved' }));
      // Update global state
      globalState.markParamSaved?.(sectionName, param);
      globalState.refreshModifiedCount?.();
      onMessage?.('Parameter reverted to default', 'info');
    }
  }, [clearAutoSaveTimer, globalState, isParameterEditable, nextSaveGeneration, onMessage, revertParameter, sectionName]);

  const handleRevertAll = useCallback(async () => {
    if (!mutationsAllowed) return;
    autoSaveTimersRef.current.forEach(clearTimeout);
    autoSaveTimersRef.current.clear();
    Object.keys(displayParameters).forEach(nextSaveGeneration);
    await Promise.allSettled(Array.from(saveQueuesRef.current.values()));
    const success = await revertSection();
    if (success) {
      setLocalValues({});
      setPendingChanges({});
      setSaveStatuses({});
      // Clear section from global state
      globalState.clearSectionChanges?.(sectionName);
      globalState.refreshModifiedCount?.();
      onMessage?.('Section reverted to defaults', 'info');
    }
  }, [displayParameters, globalState, mutationsAllowed, nextSaveGeneration, onMessage, revertSection, sectionName]);

  const handleSaveAll = useCallback(async () => {
    if (!mutationsAllowed) return;
    const params = Object.keys(pendingChanges);
    for (const param of params) {
      await handleSave(param, pendingChanges[param]);
    }
  }, [pendingChanges, handleSave, mutationsAllowed]);

  // Handle save from detail dialog
  const handleDialogSave = useCallback(async (param, value) => {
    await handleSave(param, value);
    setSelectedParam(null);
  }, [handleSave]);

  // Handle revert from detail dialog
  const handleDialogRevert = useCallback(async (param) => {
    await handleRevert(param);
    setSelectedParam(null);
  }, [handleRevert]);

  if (loading) {
    return (
      <Paper sx={{ p: 4, textAlign: 'center' }}>
        <CircularProgress />
        <Typography sx={{ mt: 2 }}>Loading {sectionName}...</Typography>
      </Paper>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        Error loading section: {error}
      </Alert>
    );
  }

  const parameters = displayParameters;
  const paramNames = Object.keys(parameters);
  const hasUnsavedChanges = Object.keys(pendingChanges).length > 0;
  const readOnlyParamNames = paramNames.filter((param) => !isParameterEditable(param));

  // Use local values if changed, otherwise use config values
  const getValue = (param) => {
    return localValues[param] !== undefined ? localValues[param] : config[param];
  };

  // Identify specialized object params that need full-width rendering (Safety/Follower editors)
  const isSpecializedParam = (param) => {
    if (parameters[param]?.type !== 'object') return false;
    if (param === 'GlobalLimits' || (param === 'FollowerOverrides' && 'GlobalLimits' in config)) return true;
    if ((param === 'General' || param === 'FollowerOverrides') && 'General' in config) return true;
    return false;
  };
  const simpleParams = paramNames.filter(p => !isSpecializedParam(p));
  const specializedParams = paramNames.filter(p => isSpecializedParam(p));

  return (
    <Paper
      ref={containerRef}
      sx={{
        p: { xs: 2, md: 3 },
        '& .param-highlight': {
          animation: 'paramFlash 2s ease-in-out',
        },
        '@keyframes paramFlash': {
          '0%':   { backgroundColor: 'transparent' },
          '15%':  { backgroundColor: 'rgba(25, 118, 210, 0.15)' },
          '30%':  { backgroundColor: 'rgba(25, 118, 210, 0.25)' },
          '60%':  { backgroundColor: 'rgba(25, 118, 210, 0.15)' },
          '100%': { backgroundColor: 'transparent' },
        }
      }}
    >
      {/* Header */}
      <Box sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        justifyContent: 'space-between',
        alignItems: { xs: 'stretch', sm: 'center' },
        gap: 2,
        mb: 2
      }}>
        <Box>
          <Typography
            variant="h5"
            sx={{ fontSize: { xs: '1.25rem', md: '1.5rem' } }}
          >
            {displaySchema.display_name || sectionName}
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" color="text.secondary" component="span">
              {paramNames.length} parameters
            </Typography>
            {hasUnsavedChanges && (
              <Chip
                label={`${Object.keys(pendingChanges).length} unsaved`}
                size="small"
                color="warning"
              />
            )}
          </Box>
        </Box>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {hasUnsavedChanges && (
            <Button
              variant="contained"
              color="primary"
              startIcon={<Save />}
              onClick={handleSaveAll}
              disabled={!mutationsAllowed}
              size="small"
            >
              Save All
            </Button>
          )}
          <Tooltip title="Refresh from server">
            <IconButton onClick={refetch}>
              <Refresh />
            </IconButton>
          </Tooltip>
          <Button
            variant="outlined"
            startIcon={<Undo />}
            onClick={handleRevertAll}
            disabled={!mutationsAllowed}
            size="small"
          >
            Revert All
          </Button>
        </Box>
      </Box>

      {!schemaAvailable && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Configuration schema unavailable or malformed. Current values are shown read-only and all configuration mutations are disabled.
          {schemaError ? ` ${schemaError}` : ''}
        </Alert>
      )}

      {schemaAvailable && readOnlyParamNames.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {readOnlyParamNames.length} current parameter{readOnlyParamNames.length === 1 ? ' is' : 's are'} read-only because the server contract is incomplete or undeclared: {readOnlyParamNames.join(', ')}.
        </Alert>
      )}

      {defaultError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Default values are unavailable. Current values remain visible; default comparisons may be incomplete.
        </Alert>
      )}

      {/* Unsaved changes warning */}
      {hasUnsavedChanges && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {autoSaveEnabled
            ? 'You have unsaved changes. Click "Save All" or press Enter/blur from a field to save individual changes.'
            : 'Manual save mode: Changes are stored locally. Click "Save All" to persist all changes.'}
        </Alert>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Conditional Rendering: Card Layout (Mobile/Tablet) vs Table (Desktop only) */}
      {useCardLayout ? (
        // Mobile/Tablet: Card Layout for better touch experience
        <Box>
          {paramNames.map((param) => (
            <ParameterCard
              key={param}
              param={param}
              schema={displaySchema}
              value={getValue(param)}
              defaultValue={defaultConfig[param] ?? parameters[param]?.default}
              saveStatus={saveStatuses[param]}
              onLocalChange={handleLocalChange}
              onAutoSave={handleAutoSave}
              onRevert={handleRevert}
              onOpenDetails={() => setSelectedParam(param)}
              configValues={config}
              autoSaveEnabled={autoSaveEnabled}
              disabled={!isParameterEditable(param)}
            />
          ))}
        </Box>
      ) : (
        // Desktop: Table for simple params, full-width cards for specialized editors
        <Box>
          {/* Table for simple (non-specialized) params */}
          {simpleParams.length > 0 && (
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 'bold', width: compactTable ? '22%' : '20%' }}>Parameter</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', width: compactTable ? '38%' : '35%' }}>Value</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', width: compactTable ? '14%' : '18%' }}>Default</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', width: compactTable ? '12%' : '14%' }}>Info</TableCell>
                    <TableCell sx={{ fontWeight: 'bold', width: compactTable ? '14%' : '13%', whiteSpace: 'nowrap' }}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {simpleParams.map((param) => {
                  const paramSchema = parameters[param];
                  const currentValue = getValue(param);
                  const defaultValue = defaultConfig[param] ?? paramSchema?.default;
                  const modified = !isDeepEqual(currentValue, defaultValue);
                  const hasPending = param in pendingChanges;
                  const saveStatus = saveStatuses[param];

                  return (
                    <TableRow
                      key={param}
                      data-param={param}
                      sx={{
                        bgcolor: modified ? 'action.selected' : undefined,
                        '&:hover': { bgcolor: 'action.hover' }
                      }}
                    >
                      <TableCell sx={{ overflow: 'hidden' }}>
                        <Box>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {param}
                          </Typography>
                          {paramSchema?.description && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {paramSchema.description.slice(0, 60)}
                              {paramSchema.description.length > 60 ? '...' : ''}
                            </Typography>
                          )}
                        </Box>
                      </TableCell>

                      <TableCell sx={{ overflow: 'hidden' }}>
                        <ParameterInput
                          param={param}
                          schema={displaySchema}
                          value={currentValue}
                          defaultValue={defaultValue}
                          onChange={handleLocalChange}
                          onAutoSave={handleAutoSave}
                          saveStatus={saveStatus}
                          configValues={config}
                          autoSaveEnabled={autoSaveEnabled}
                          disabled={!isParameterEditable(param)}
                        />
                      </TableCell>

                      <TableCell sx={{ overflow: 'hidden' }}>
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          noWrap
                          sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
                        >
                          {typeof defaultValue === 'object'
                            ? JSON.stringify(defaultValue).slice(0, 20)
                            : String(defaultValue)}
                        </Typography>
                      </TableCell>

                      <TableCell>
                        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                          {paramSchema?.reload_tier && (
                            <ReloadTierChip tier={paramSchema.reload_tier} size="small" />
                          )}
                          {paramSchema?.unit && (
                            <Chip label={paramSchema.unit} size="small" variant="outlined" />
                          )}
                          {hasPending && (
                            <Chip label="Unsaved" size="small" color="info" />
                          )}
                          {modified && !hasPending && (
                            <Chip label="Modified" size="small" color="warning" />
                          )}
                        </Box>
                      </TableCell>

                      <TableCell>
                        <Box sx={{ display: 'flex', gap: 0.5 }}>
                          <Tooltip title="Open detail editor">
                            <span>
                            <IconButton
                              size="small"
                              onClick={() => setSelectedParam(param)}
                              disabled={!isParameterEditable(param)}
                            >
                              <OpenInNew fontSize="small" />
                            </IconButton>
                            </span>
                          </Tooltip>
                          {hasPending && (
                            <Tooltip title="Save this parameter">
                              <span>
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={() => handleSave(param, currentValue)}
                                  disabled={!isParameterEditable(param) || saveStatus === 'saving'}
                                >
                                  <Save fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                          {modified && (
                            <Tooltip title="Revert to default">
                              <span>
                                <IconButton
                                  size="small"
                                  onClick={() => handleRevert(param)}
                                  disabled={!isParameterEditable(param) || saveStatus === 'saving'}
                                >
                                  <Undo fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          )}
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {/* Full-width specialized editors (Safety/Follower) */}
          {specializedParams.map((param) => (
            <ParameterCard
              key={param}
              param={param}
              schema={displaySchema}
              value={getValue(param)}
              defaultValue={defaultConfig[param] ?? parameters[param]?.default}
              saveStatus={saveStatuses[param]}
              onLocalChange={handleLocalChange}
              onAutoSave={handleAutoSave}
              onRevert={handleRevert}
              onOpenDetails={() => setSelectedParam(param)}
              configValues={config}
              autoSaveEnabled={autoSaveEnabled}
              disabled={!isParameterEditable(param)}
            />
          ))}
        </Box>
      )}

      {paramNames.length === 0 && (
        <Box sx={{ py: 4, textAlign: 'center' }}>
          <Typography color="text.secondary">
            No parameters in this section
          </Typography>
        </Box>
      )}

      {/* Parameter Detail Dialog */}
      <ParameterDetailDialog
        open={!!selectedParam}
        onClose={() => setSelectedParam(null)}
        param={selectedParam}
        paramSchema={selectedParam ? parameters[selectedParam] : null}
        currentValue={selectedParam ? getValue(selectedParam) : null}
        defaultValue={selectedParam ? (defaultConfig[selectedParam] ?? parameters[selectedParam]?.default) : null}
        onSave={handleDialogSave}
        onRevert={handleDialogRevert}
        saving={selectedParam ? (!isParameterEditable(selectedParam) || saveStatuses[selectedParam] === 'saving') : false}
        configValues={config}
      />
    </Paper>
  );
};

// PropTypes for ParameterInput (internal component)
ParameterInput.propTypes = {
  param: PropTypes.string.isRequired,
  schema: PropTypes.object,
  value: PropTypes.any,
  defaultValue: PropTypes.any,
  onChange: PropTypes.func.isRequired,
  onAutoSave: PropTypes.func.isRequired,
  saveStatus: PropTypes.oneOf(['idle', 'saving', 'saved', 'error']),
  mobileMode: PropTypes.bool,
  configValues: PropTypes.object,
  autoSaveEnabled: PropTypes.bool,
  disabled: PropTypes.bool,
};

// PropTypes for SectionEditor
SectionEditor.propTypes = {
  /** The section name to edit (e.g., 'Tracker', 'Follower') */
  sectionName: PropTypes.string.isRequired,
  /** Parameter name to scroll to and highlight (from search navigation) */
  highlightParam: PropTypes.string,
  /** Callback when highlight animation completes */
  onHighlightComplete: PropTypes.func,
  /** Callback when reboot/restart is required after parameter change */
  onRebootRequired: PropTypes.func,
  /** Callback for displaying messages (toast notifications) */
  onMessage: PropTypes.func,
  /** Whether auto-save on blur is enabled (v5.4.1+). When false, user must click Save All. */
  autoSaveEnabled: PropTypes.bool,
};

export default SectionEditor;
