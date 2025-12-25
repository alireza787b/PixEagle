// dashboard/src/components/config/ObjectEditor.js
import React, { useState, useEffect } from 'react';
import {
  Box, TextField, IconButton, Typography, Tooltip,
  Table, TableBody, TableCell, TableRow, TableContainer,
  Paper, Collapse, Button
} from '@mui/material';
import {
  Add, Delete, Edit, Check, Close, Code, ViewList,
  ExpandMore, ExpandLess
} from '@mui/icons-material';

/**
 * ObjectEditor - Visual object/dictionary editing component
 *
 * Features:
 * - Key-value table editor
 * - Add/remove properties
 * - Inline editing
 * - JSON mode toggle
 * - Collapsible for large objects
 */
const ObjectEditor = ({
  value,
  onChange,
  onBlur,
  disabled = false,
  schema // Optional schema for property types
}) => {
  const [entries, setEntries] = useState([]);
  const [editingKey, setEditingKey] = useState(null);
  const [editKeyValue, setEditKeyValue] = useState('');
  const [editValueValue, setEditValueValue] = useState('');
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonValue, setJsonValue] = useState('');
  const [jsonError, setJsonError] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);

  // Initialize from value
  useEffect(() => {
    const obj = typeof value === 'object' && value !== null ? value : {};
    setEntries(Object.entries(obj));
    setJsonValue(JSON.stringify(obj, null, 2));
  }, [value]);

  // Check if object has nested objects/arrays
  const isComplex = entries.some(([_, v]) => typeof v === 'object' && v !== null);

  // Auto-switch to JSON mode for complex objects
  useEffect(() => {
    if (isComplex && !jsonMode) {
      setJsonMode(true);
    }
  }, [isComplex, jsonMode]);

  const handleEntriesChange = (newEntries) => {
    const newObj = Object.fromEntries(newEntries);
    setEntries(newEntries);
    setJsonValue(JSON.stringify(newObj, null, 2));
    onChange(newObj);
  };

  const handleAddProperty = () => {
    if (!newKey.trim()) return;

    // Parse value based on content
    let parsedValue;
    try {
      parsedValue = JSON.parse(newValue);
    } catch {
      // Treat as string if not valid JSON
      parsedValue = newValue;
    }

    const newEntries = [...entries, [newKey.trim(), parsedValue]];
    handleEntriesChange(newEntries);
    setNewKey('');
    setNewValue('');
    setShowAddForm(false);
  };

  const handleRemoveProperty = (key) => {
    const newEntries = entries.filter(([k]) => k !== key);
    handleEntriesChange(newEntries);
  };

  const handleStartEdit = (key, currentValue) => {
    setEditingKey(key);
    setEditKeyValue(key);
    setEditValueValue(
      typeof currentValue === 'object'
        ? JSON.stringify(currentValue)
        : String(currentValue)
    );
  };

  const handleConfirmEdit = () => {
    if (editingKey === null) return;

    // Parse value
    let parsedValue;
    try {
      parsedValue = JSON.parse(editValueValue);
    } catch {
      parsedValue = editValueValue;
    }

    // Update or rename key
    const newEntries = entries.map(([k, v]) => {
      if (k === editingKey) {
        return [editKeyValue, parsedValue];
      }
      return [k, v];
    });

    handleEntriesChange(newEntries);
    setEditingKey(null);
    setEditKeyValue('');
    setEditValueValue('');
  };

  const handleCancelEdit = () => {
    setEditingKey(null);
    setEditKeyValue('');
    setEditValueValue('');
  };

  const handleJsonChange = (e) => {
    const newJsonValue = e.target.value;
    setJsonValue(newJsonValue);

    try {
      const parsed = JSON.parse(newJsonValue);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setJsonError('Must be a valid JSON object');
        return;
      }
      setJsonError(null);
      setEntries(Object.entries(parsed));
      onChange(parsed);
    } catch {
      setJsonError('Invalid JSON syntax');
    }
  };

  const handleJsonBlur = () => {
    if (!jsonError) {
      onBlur?.();
    }
  };

  // Format value for display
  const formatValue = (val) => {
    if (val === null) return 'null';
    if (val === undefined) return 'undefined';
    if (typeof val === 'object') return JSON.stringify(val);
    if (typeof val === 'boolean') return val ? 'true' : 'false';
    return String(val);
  };

  // JSON mode for complex objects
  if (jsonMode) {
    return (
      <Box sx={{ width: '100%' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="caption" color="text.secondary">
            JSON Mode ({entries.length} properties)
          </Typography>
          {!isComplex && (
            <Tooltip title="Switch to visual mode">
              <IconButton size="small" onClick={() => setJsonMode(false)}>
                <ViewList fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>
        <TextField
          fullWidth
          multiline
          rows={6}
          value={jsonValue}
          onChange={handleJsonChange}
          onBlur={handleJsonBlur}
          error={!!jsonError}
          helperText={jsonError || 'Enter a valid JSON object'}
          disabled={disabled}
          InputProps={{
            sx: { fontFamily: 'monospace', fontSize: '0.75rem' }
          }}
        />
      </Box>
    );
  }

  // Visual mode
  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <IconButton size="small" onClick={() => setExpanded(!expanded)}>
            {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
          </IconButton>
          <Typography variant="caption" color="text.secondary">
            {entries.length} properties
          </Typography>
        </Box>
        <Box>
          <Tooltip title="Switch to JSON mode">
            <IconButton size="small" onClick={() => setJsonMode(true)}>
              <Code fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Add property">
            <IconButton
              size="small"
              color="primary"
              onClick={() => setShowAddForm(true)}
              disabled={disabled}
            >
              <Add fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      <Collapse in={expanded}>
        {/* Add property form */}
        {showAddForm && (
          <Paper variant="outlined" sx={{ p: 1, mb: 1, bgcolor: 'action.hover' }}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <TextField
                size="small"
                label="Key"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                sx={{ flex: 1 }}
              />
              <TextField
                size="small"
                label="Value"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                sx={{ flex: 2 }}
              />
              <IconButton size="small" color="success" onClick={handleAddProperty}>
                <Check fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => setShowAddForm(false)}>
                <Close fontSize="small" />
              </IconButton>
            </Box>
          </Paper>
        )}

        {entries.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              No properties. Click + to add.
            </Typography>
          </Paper>
        ) : (
          <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 250 }}>
            <Table size="small">
              <TableBody>
                {entries.map(([key, val]) => (
                  <TableRow key={key}>
                    {editingKey === key ? (
                      <>
                        <TableCell sx={{ width: '30%' }}>
                          <TextField
                            size="small"
                            value={editKeyValue}
                            onChange={(e) => setEditKeyValue(e.target.value)}
                            fullWidth
                            autoFocus
                          />
                        </TableCell>
                        <TableCell>
                          <TextField
                            size="small"
                            value={editValueValue}
                            onChange={(e) => setEditValueValue(e.target.value)}
                            fullWidth
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleConfirmEdit();
                              if (e.key === 'Escape') handleCancelEdit();
                            }}
                          />
                        </TableCell>
                        <TableCell sx={{ width: 80 }}>
                          <IconButton size="small" color="success" onClick={handleConfirmEdit}>
                            <Check fontSize="small" />
                          </IconButton>
                          <IconButton size="small" onClick={handleCancelEdit}>
                            <Close fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell sx={{ width: '30%' }}>
                          <Typography
                            variant="body2"
                            sx={{ fontFamily: 'monospace', fontWeight: 500 }}
                          >
                            {key}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography
                            variant="body2"
                            sx={{
                              fontFamily: 'monospace',
                              wordBreak: 'break-all',
                              color: typeof val === 'string' ? 'success.main' :
                                typeof val === 'number' ? 'info.main' :
                                  typeof val === 'boolean' ? 'warning.main' : 'text.primary'
                            }}
                          >
                            {formatValue(val)}
                          </Typography>
                        </TableCell>
                        <TableCell sx={{ width: 80 }}>
                          <Tooltip title="Edit">
                            <IconButton
                              size="small"
                              onClick={() => handleStartEdit(key, val)}
                              disabled={disabled}
                            >
                              <Edit fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Remove">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleRemoveProperty(key)}
                              disabled={disabled}
                            >
                              <Delete fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Collapse>
    </Box>
  );
};

export default ObjectEditor;
