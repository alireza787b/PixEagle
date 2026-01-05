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
import ParameterDetailDialog from './ParameterDetailDialog';
import { isPIDTriplet } from '../../utils/schemaAnalyzer';
import SmartValueEditor from './SmartValueEditor';
import SafetyLimitsEditor from './SafetyLimitsEditor';
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

// Type-specific input component with proper ref tracking
const ParameterInput = ({ param, schema, value, defaultValue, onChange, onSave, saveStatus, mobileMode = false, configValues = {} }) => {
  const { touchTargetSize } = useResponsive();
  const paramSchema = schema?.parameters?.[param] || {};
  const type = paramSchema.type || 'string';
  const isModified = !isDeepEqual(value, defaultValue);

  // Use ref to track current input value for blur handling (must be called unconditionally)
  const currentValueRef = useRef(value);
  const [localInput, setLocalInput] = useState(value);
  const [validationError, setValidationError] = useState(null);

  // Sync local input with prop value when it changes externally
  useEffect(() => {
    setLocalInput(value);
    currentValueRef.current = value;
    setValidationError(null);
  }, [value]);

  // Validate value based on schema constraints
  const validateValue = useCallback((val) => {
    if (type === 'integer' || type === 'float') {
      const numValue = type === 'integer' ? parseInt(val, 10) : parseFloat(val);
      if (isNaN(numValue)) return 'Invalid number';
      if (paramSchema.min !== undefined && numValue < paramSchema.min) {
        return `Min: ${paramSchema.min}`;
      }
      if (paramSchema.max !== undefined && numValue > paramSchema.max) {
        return `Max: ${paramSchema.max}`;
      }
    }
    return null;
  }, [type, paramSchema]);

  // Build helper text showing constraints
  const getHelperText = () => {
    if (validationError) return validationError;
    if (type === 'integer' || type === 'float') {
      const parts = [];
      if (paramSchema.min !== undefined) parts.push(`Min: ${paramSchema.min}`);
      if (paramSchema.max !== undefined) parts.push(`Max: ${paramSchema.max}`);
      if (paramSchema.unit) parts.push(paramSchema.unit);
      return parts.length > 0 ? parts.join(' | ') : undefined;
    }
    return undefined;
  };

  const handleInputChange = (newValue) => {
    setLocalInput(newValue);
    currentValueRef.current = newValue;
    const error = validateValue(newValue);
    setValidationError(error);
    onChange(param, newValue);
  };

  const handleBlur = () => {
    const currentValue = currentValueRef.current;
    // Only save if value actually changed and no validation error
    if (!validationError && (currentValue !== value || (currentValue !== defaultValue && saveStatus !== 'saved'))) {
      onSave(param, currentValue);
    }
  };

  // Determine border color based on save status
  const getBorderColor = () => {
    if (saveStatus === 'saving') return 'info.main';
    if (saveStatus === 'saved') return 'success.main';
    if (saveStatus === 'error') return 'error.main';
    if (isModified) return 'warning.main';
    return undefined;
  };

  const inputSx = {
    width: mobileMode ? '100%' : 150,
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
  const isSafetyParameter = param === 'GlobalLimits' || param === 'FollowerOverrides';
  if (isSafetyParameter && type === 'object') {
    const safetyType = param === 'GlobalLimits' ? 'GlobalLimits' : 'FollowerOverrides';
    const globalLimits = param === 'FollowerOverrides' ? (configValues.GlobalLimits || {}) : {};

    return (
      <Box sx={{ width: '100%', minWidth: mobileMode ? '100%' : 400 }}>
        <SafetyLimitsEditor
          type={safetyType}
          value={value || {}}
          onChange={(newVal) => {
            onChange(param, newVal);
            setTimeout(() => onSave(param, newVal), 100);
          }}
          globalLimits={globalLimits}
          disabled={saveStatus === 'saving'}
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
            onSave(param, newVal);
          }}
          color={isModified ? 'warning' : 'primary'}
          disabled={saveStatus === 'saving'}
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
          onChange={(e) => handleInputChange(parseInt(e.target.value, 10) || 0)}
          onBlur={handleBlur}
          onKeyDown={(e) => e.key === 'Enter' && handleBlur()}
          disabled={saveStatus === 'saving'}
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
          onChange={(e) => handleInputChange(parseFloat(e.target.value) || 0)}
          onBlur={handleBlur}
          onKeyDown={(e) => e.key === 'Enter' && handleBlur()}
          disabled={saveStatus === 'saving'}
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

  // Enum/Select - immediate save with custom value support
  if (type === 'enum' || paramSchema.options) {
    const options = paramSchema.options || [];
    const isValueInOptions = options.some(opt => (opt.value || opt) === localInput);

    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
        <FormControl size={touchTargetSize} fullWidth={mobileMode} sx={{ minWidth: mobileMode ? 0 : 200 }}>
          <Select
            value={isValueInOptions ? localInput : (localInput ? '__custom_current__' : '')}
            onChange={(e) => {
              const newVal = e.target.value;
              if (newVal === '__custom__') {
                // Prompt for custom value
                const customVal = window.prompt('Enter custom value:', localInput || '');
                if (customVal !== null && customVal !== '') {
                  handleInputChange(customVal);
                  onSave(param, customVal);
                }
              } else if (newVal !== '__custom_current__') {
                handleInputChange(newVal);
                onSave(param, newVal);
              }
            }}
            disabled={saveStatus === 'saving'}
            sx={{
              bgcolor: isModified ? 'action.hover' : undefined
            }}
            renderValue={(selected) => {
              if (selected === '__custom_current__') {
                return `${localInput} (custom)`;
              }
              const opt = options.find(o => (o.value || o) === selected);
              return opt?.label || opt || selected;
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
                key={opt.value || opt}
                value={opt.value || opt}
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  py: opt.description ? 1 : 0.5
                }}
              >
                <Typography variant="body2" fontWeight={500}>
                  {opt.label || opt}
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

            {/* Custom value option */}
            <Divider />
            <MenuItem value="__custom__">
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Edit fontSize="small" color="primary" />
                <Typography color="primary" fontStyle="italic" variant="body2">
                  Enter custom value...
                </Typography>
              </Box>
            </MenuItem>
          </Select>
        </FormControl>
        {saveStatus === 'saving' && <CircularProgress size={16} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      </Box>
    );
  }

  // Array input - use SmartValueEditor inline
  if (type === 'array') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, minWidth: mobileMode ? '100%' : 280 }}>
        <SmartValueEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
            setTimeout(() => onSave(param, newVal), 100);
          }}
          schema={paramSchema}
          mode="inline"
          disabled={saveStatus === 'saving'}
          showUndoRedo={false}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  // Object input - use SmartValueEditor inline
  if (type === 'object') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, minWidth: mobileMode ? '100%' : 320 }}>
        <SmartValueEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
            setTimeout(() => onSave(param, newVal), 100);
          }}
          schema={paramSchema}
          mode="inline"
          disabled={saveStatus === 'saving'}
          showUndoRedo={false}
        />
        {saveStatus === 'saving' && <CircularProgress size={16} sx={{ mt: 1 }} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" sx={{ mt: 1 }} />}
        {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" sx={{ mt: 1 }} />}
      </Box>
    );
  }

  // Default: string input
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: mobileMode ? '100%' : 'auto' }}>
      <TextField
        size={touchTargetSize}
        fullWidth={mobileMode}
        value={localInput ?? ''}
        onChange={(e) => handleInputChange(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={(e) => e.key === 'Enter' && handleBlur()}
        disabled={saveStatus === 'saving'}
        sx={{ ...inputSx, width: mobileMode ? '100%' : 200 }}
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
  onSave,
  onRevert,
  onOpenDetails,
  configValues = {}
}) => {
  const { buttonSize } = useResponsive();
  const paramSchema = schema?.parameters?.[param] || {};
  const isModified = !isDeepEqual(value, defaultValue);
  const type = paramSchema.type || 'string';

  return (
    <Card
      variant="outlined"
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
            onSave={onSave}
            saveStatus={saveStatus}
            mobileMode={true}
            configValues={configValues}
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
          >
            Details
          </Button>

          {isModified && (
            <Button
              size={buttonSize}
              variant="outlined"
              startIcon={<Undo />}
              onClick={() => onRevert(param)}
              disabled={saveStatus === 'saving'}
            >
              Revert
            </Button>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

const SectionEditor = ({ sectionName, onRebootRequired, onMessage }) => {
  const {
    config,
    defaultConfig,
    schema,
    loading,
    error,
    updateParameter,
    revertParameter,
    revertSection,
    refetch
  } = useConfigSection(sectionName);
  const { isMobile, isTablet, spacing } = useResponsive();
  // Use card layout on mobile/tablet, OR always for Safety section (has complex embedded editors)
  const isSafetySection = sectionName === 'Safety' || sectionName === 'SafetyLimits';
  const useCardLayout = isMobile || isTablet || isSafetySection;

  const [localValues, setLocalValues] = useState({});
  const [saveStatuses, setSaveStatuses] = useState({}); // 'saving' | 'saved' | 'error' | null
  const [pendingChanges, setPendingChanges] = useState({}); // Track unsaved changes
  const [selectedParam, setSelectedParam] = useState(null); // For detail dialog

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
    setLocalValues({});
    setSaveStatuses({});
    setPendingChanges({});
    setSelectedParam(null);
  }, [sectionName]);

  const handleLocalChange = useCallback((param, value) => {
    setLocalValues(prev => ({ ...prev, [param]: value }));
    setPendingChanges(prev => ({ ...prev, [param]: value }));
  }, []);

  const handleSave = useCallback(async (param, value) => {
    // Set saving status
    setSaveStatuses(prev => ({ ...prev, [param]: 'saving' }));

    try {
      const result = await updateParameter(param, value);

      if (result.success && result.saved !== false) {
        // Successfully saved
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

        // Check if restart required based on reload_tier
        const paramSchema = schema?.parameters?.[param];
        const reloadTier = paramSchema?.reload_tier || 'system_restart';
        if (reloadTier !== 'immediate') {
          onRebootRequired?.(sectionName, param, reloadTier);
        }

        onMessage?.(`${param} saved`, 'success');
      } else {
        // Save failed
        setSaveStatuses(prev => ({ ...prev, [param]: 'error' }));
        const errorMsg = result.error ||
          (result.saved === false ? 'Failed to write to config file' : 'Validation failed');
        onMessage?.(`Error saving ${param}: ${errorMsg}`, 'error');
      }
    } catch (err) {
      setSaveStatuses(prev => ({ ...prev, [param]: 'error' }));
      onMessage?.(`Error saving ${param}: ${err.message}`, 'error');
    }
  }, [updateParameter, schema, sectionName, onRebootRequired, onMessage]);

  const handleRevert = useCallback(async (param) => {
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
      onMessage?.('Parameter reverted to default', 'info');
    }
  }, [revertParameter, onMessage]);

  const handleRevertAll = useCallback(async () => {
    const success = await revertSection();
    if (success) {
      setLocalValues({});
      setPendingChanges({});
      setSaveStatuses({});
      onMessage?.('Section reverted to defaults', 'info');
    }
  }, [revertSection, onMessage]);

  const handleSaveAll = useCallback(async () => {
    const params = Object.keys(pendingChanges);
    for (const param of params) {
      await handleSave(param, pendingChanges[param]);
    }
  }, [pendingChanges, handleSave]);

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

  const parameters = schema?.parameters || {};
  const paramNames = Object.keys(parameters);
  const hasUnsavedChanges = Object.keys(pendingChanges).length > 0;

  // Use local values if changed, otherwise use config values
  const getValue = (param) => {
    return localValues[param] !== undefined ? localValues[param] : config[param];
  };

  return (
    <Paper sx={{ p: { xs: 2, md: 3 } }}>
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
          <Typography variant={{ xs: 'h6', md: 'h5' }}>
            {schema?.display_name || sectionName}
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
            size="small"
          >
            Revert All
          </Button>
        </Box>
      </Box>

      {/* Unsaved changes warning */}
      {hasUnsavedChanges && (
        <Alert severity="info" sx={{ mb: 2 }}>
          You have unsaved changes. Click "Save All" or press Enter/blur from a field to save individual changes.
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
              schema={schema}
              value={getValue(param)}
              defaultValue={defaultConfig[param] ?? parameters[param]?.default}
              saveStatus={saveStatuses[param]}
              onLocalChange={handleLocalChange}
              onSave={handleSave}
              onRevert={handleRevert}
              onOpenDetails={() => setSelectedParam(param)}
              configValues={config}
            />
          ))}
        </Box>
      ) : (
        // Desktop (>= 900px): Table Layout with responsive overflow
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 650 }}>
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 'bold', minWidth: 180 }}>Parameter</TableCell>
                <TableCell sx={{ fontWeight: 'bold', minWidth: 150 }}>Value</TableCell>
                <TableCell sx={{ fontWeight: 'bold', minWidth: 100 }}>Default</TableCell>
                <TableCell sx={{ fontWeight: 'bold', minWidth: 100 }}>Info</TableCell>
                <TableCell sx={{ fontWeight: 'bold', minWidth: 100, whiteSpace: 'nowrap' }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paramNames.map((param) => {
              const paramSchema = parameters[param];
              const currentValue = getValue(param);
              const defaultValue = defaultConfig[param] ?? paramSchema?.default;
              const modified = !isDeepEqual(currentValue, defaultValue);
              const hasPending = param in pendingChanges;
              const saveStatus = saveStatuses[param];

              return (
                <TableRow
                  key={param}
                  sx={{
                    bgcolor: modified ? 'action.selected' : undefined,
                    '&:hover': { bgcolor: 'action.hover' }
                  }}
                >
                  <TableCell>
                    <Box>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {param}
                      </Typography>
                      {paramSchema?.description && (
                        <Typography variant="caption" color="text.secondary">
                          {paramSchema.description.slice(0, 60)}
                          {paramSchema.description.length > 60 ? '...' : ''}
                        </Typography>
                      )}
                    </Box>
                  </TableCell>

                  <TableCell>
                    <ParameterInput
                      param={param}
                      schema={schema}
                      value={currentValue}
                      defaultValue={defaultValue}
                      onChange={handleLocalChange}
                      onSave={handleSave}
                      saveStatus={saveStatus}
                      configValues={config}
                    />
                  </TableCell>

                  <TableCell>
                    <Typography
                      variant="body2"
                      color="text.secondary"
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
                        <IconButton
                          size="small"
                          onClick={() => setSelectedParam(param)}
                        >
                          <OpenInNew fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      {hasPending && (
                        <Tooltip title="Save this parameter">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={() => handleSave(param, currentValue)}
                            disabled={saveStatus === 'saving'}
                          >
                            <Save fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                      {modified && (
                        <Tooltip title="Revert to default">
                          <IconButton
                            size="small"
                            onClick={() => handleRevert(param)}
                            disabled={saveStatus === 'saving'}
                          >
                            <Undo fontSize="small" />
                          </IconButton>
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
        saving={selectedParam ? saveStatuses[selectedParam] === 'saving' : false}
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
  onSave: PropTypes.func.isRequired,
  saveStatus: PropTypes.oneOf(['idle', 'saving', 'saved', 'error']),
  mobileMode: PropTypes.bool,
  configValues: PropTypes.object,
};

// PropTypes for SectionEditor
SectionEditor.propTypes = {
  /** The section name to edit (e.g., 'Tracker', 'Follower') */
  sectionName: PropTypes.string.isRequired,
  /** Callback when reboot/restart is required after parameter change */
  onRebootRequired: PropTypes.func,
  /** Callback for displaying messages (toast notifications) */
  onMessage: PropTypes.func,
};

SectionEditor.defaultProps = {
  onRebootRequired: null,
  onMessage: null,
};

export default SectionEditor;
