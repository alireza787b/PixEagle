// dashboard/src/components/config/SectionEditor.js
import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Box, Paper, Typography, CircularProgress, Alert, Button, Divider,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, Chip, TextField, Switch, Select, MenuItem,
  FormControl, Snackbar
} from '@mui/material';
import {
  Refresh, Undo, Save, Check, Error as ErrorIcon, OpenInNew
} from '@mui/icons-material';

import { useConfigSection } from '../../hooks/useConfig';
import ParameterDetailDialog from './ParameterDetailDialog';
import ArrayEditor from './ArrayEditor';
import ObjectEditor from './ObjectEditor';

// Type-specific input component with proper ref tracking
const ParameterInput = ({ param, schema, value, defaultValue, onChange, onSave, saveStatus }) => {
  const paramSchema = schema?.parameters?.[param] || {};
  const type = paramSchema.type || 'string';
  const isModified = value !== defaultValue;

  // Use ref to track current input value for blur handling
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
    width: 150,
    '& .MuiOutlinedInput-root': {
      bgcolor: isModified ? 'warning.50' : undefined,
      borderColor: getBorderColor(),
      '& fieldset': {
        borderColor: getBorderColor(),
        borderWidth: saveStatus ? 2 : 1
      }
    }
  };

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
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        <TextField
          type="number"
          size="small"
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
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        <TextField
          type="number"
          size="small"
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

  // Enum/Select - immediate save
  if (type === 'enum' || paramSchema.options) {
    const options = paramSchema.options || [];
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <Select
            value={localInput ?? ''}
            onChange={(e) => {
              const newVal = e.target.value;
              handleInputChange(newVal);
              onSave(param, newVal);
            }}
            disabled={saveStatus === 'saving'}
            sx={{
              bgcolor: isModified ? 'warning.50' : undefined
            }}
          >
            {options.map((opt) => (
              <MenuItem key={opt.value || opt} value={opt.value || opt}>
                {opt.label || opt}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {saveStatus === 'saving' && <CircularProgress size={16} />}
        {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      </Box>
    );
  }

  // Array input - use ArrayEditor
  if (type === 'array') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, minWidth: 250 }}>
        <ArrayEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
          }}
          onBlur={handleBlur}
          disabled={saveStatus === 'saving'}
        />
        <Box sx={{ pt: 1 }}>
          {saveStatus === 'saving' && <CircularProgress size={16} />}
          {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
          {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
        </Box>
      </Box>
    );
  }

  // Object input - use ObjectEditor
  if (type === 'object') {
    return (
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, minWidth: 300 }}>
        <ObjectEditor
          value={localInput}
          onChange={(newVal) => {
            handleInputChange(newVal);
          }}
          onBlur={handleBlur}
          disabled={saveStatus === 'saving'}
        />
        <Box sx={{ pt: 1 }}>
          {saveStatus === 'saving' && <CircularProgress size={16} />}
          {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
          {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
        </Box>
      </Box>
    );
  }

  // Default: string input
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <TextField
        size="small"
        value={localInput ?? ''}
        onChange={(e) => handleInputChange(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={(e) => e.key === 'Enter' && handleBlur()}
        disabled={saveStatus === 'saving'}
        sx={{ ...inputSx, width: 200 }}
      />
      {saveStatus === 'saving' && <CircularProgress size={16} />}
      {saveStatus === 'saved' && <Check color="success" fontSize="small" />}
      {saveStatus === 'error' && <ErrorIcon color="error" fontSize="small" />}
    </Box>
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

        // Check if reboot required
        const paramSchema = schema?.parameters?.[param];
        if (paramSchema?.reboot_required) {
          onRebootRequired?.(sectionName, param);
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
    <Paper sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography variant="h5">
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

      {/* Parameters Table */}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 'bold' }}>Parameter</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>Value</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>Default</TableCell>
              <TableCell sx={{ fontWeight: 'bold' }}>Info</TableCell>
              <TableCell sx={{ fontWeight: 'bold', width: 120 }}>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paramNames.map((param) => {
              const paramSchema = parameters[param];
              const currentValue = getValue(param);
              const defaultValue = defaultConfig[param] ?? paramSchema?.default;
              const modified = currentValue !== defaultValue;
              const hasPending = param in pendingChanges;
              const saveStatus = saveStatuses[param];

              return (
                <TableRow
                  key={param}
                  sx={{
                    bgcolor: modified ? 'warning.50' : undefined,
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
                      {paramSchema?.reboot_required && (
                        <Tooltip title="Restart required after change">
                          <Chip label="Restart" size="small" color="warning" variant="outlined" />
                        </Tooltip>
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
      />
    </Paper>
  );
};

export default SectionEditor;
