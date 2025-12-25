// dashboard/src/components/config/ArrayEditor.js
import React, { useState, useEffect } from 'react';
import {
  Box, TextField, IconButton, Typography, Tooltip, Chip,
  List, ListItem, ListItemText, ListItemSecondaryAction,
  Button, Paper, Collapse, Alert
} from '@mui/material';
import {
  Add, Delete, Edit, Check, Close, Code, ViewList
} from '@mui/icons-material';

/**
 * ArrayEditor - Visual array editing component
 *
 * Features:
 * - Visual list with add/remove buttons
 * - Inline editing for each element
 * - Type inference from existing values
 * - JSON mode toggle for complex arrays
 * - Validation feedback
 */
const ArrayEditor = ({
  value,
  onChange,
  onBlur,
  disabled = false,
  itemType = 'string', // 'string', 'number', 'boolean'
  maxItems,
  minItems = 0
}) => {
  const [items, setItems] = useState([]);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonValue, setJsonValue] = useState('');
  const [jsonError, setJsonError] = useState(null);

  // Initialize from value
  useEffect(() => {
    const arr = Array.isArray(value) ? value : [];
    setItems(arr);
    setJsonValue(JSON.stringify(arr, null, 2));
  }, [value]);

  // Detect if array is complex (nested objects/arrays)
  const isComplexArray = items.some(
    item => typeof item === 'object' && item !== null
  );

  // Auto-switch to JSON mode for complex arrays
  useEffect(() => {
    if (isComplexArray && !jsonMode) {
      setJsonMode(true);
    }
  }, [isComplexArray, jsonMode]);

  const handleItemsChange = (newItems) => {
    setItems(newItems);
    setJsonValue(JSON.stringify(newItems, null, 2));
    onChange(newItems);
  };

  const handleAddItem = () => {
    const defaultValue = itemType === 'number' ? 0 : itemType === 'boolean' ? false : '';
    const newItems = [...items, defaultValue];
    handleItemsChange(newItems);
    setEditingIndex(newItems.length - 1);
    setEditValue(String(defaultValue));
  };

  const handleRemoveItem = (index) => {
    if (items.length <= minItems) return;
    const newItems = items.filter((_, i) => i !== index);
    handleItemsChange(newItems);
  };

  const handleStartEdit = (index) => {
    setEditingIndex(index);
    setEditValue(String(items[index]));
  };

  const handleConfirmEdit = () => {
    if (editingIndex === null) return;

    let parsedValue;
    if (itemType === 'number') {
      parsedValue = parseFloat(editValue) || 0;
    } else if (itemType === 'boolean') {
      parsedValue = editValue.toLowerCase() === 'true';
    } else {
      parsedValue = editValue;
    }

    const newItems = [...items];
    newItems[editingIndex] = parsedValue;
    handleItemsChange(newItems);
    setEditingIndex(null);
    setEditValue('');
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setEditValue('');
  };

  const handleJsonChange = (e) => {
    const newJsonValue = e.target.value;
    setJsonValue(newJsonValue);

    try {
      const parsed = JSON.parse(newJsonValue);
      if (!Array.isArray(parsed)) {
        setJsonError('Must be a valid JSON array');
        return;
      }
      setJsonError(null);
      setItems(parsed);
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

  // JSON mode for complex arrays
  if (jsonMode) {
    return (
      <Box sx={{ width: '100%' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="caption" color="text.secondary">
            JSON Mode ({items.length} items)
          </Typography>
          {!isComplexArray && (
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
          rows={4}
          value={jsonValue}
          onChange={handleJsonChange}
          onBlur={handleJsonBlur}
          error={!!jsonError}
          helperText={jsonError || 'Enter a valid JSON array'}
          disabled={disabled}
          InputProps={{
            sx: { fontFamily: 'monospace', fontSize: '0.75rem' }
          }}
        />
      </Box>
    );
  }

  // Visual mode for simple arrays
  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {items.length} items
          {maxItems && ` (max ${maxItems})`}
        </Typography>
        <Box>
          <Tooltip title="Switch to JSON mode">
            <IconButton size="small" onClick={() => setJsonMode(true)}>
              <Code fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Add item">
            <IconButton
              size="small"
              color="primary"
              onClick={handleAddItem}
              disabled={disabled || (maxItems && items.length >= maxItems)}
            >
              <Add fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {items.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 2, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            No items. Click + to add.
          </Typography>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ maxHeight: 200, overflow: 'auto' }}>
          <List dense disablePadding>
            {items.map((item, index) => (
              <ListItem
                key={index}
                sx={{
                  borderBottom: index < items.length - 1 ? '1px solid' : 'none',
                  borderColor: 'divider'
                }}
              >
                {editingIndex === index ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                    <TextField
                      size="small"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleConfirmEdit();
                        if (e.key === 'Escape') handleCancelEdit();
                      }}
                      autoFocus
                      fullWidth
                      type={itemType === 'number' ? 'number' : 'text'}
                    />
                    <IconButton size="small" color="success" onClick={handleConfirmEdit}>
                      <Check fontSize="small" />
                    </IconButton>
                    <IconButton size="small" onClick={handleCancelEdit}>
                      <Close fontSize="small" />
                    </IconButton>
                  </Box>
                ) : (
                  <>
                    <ListItemText
                      primary={
                        <Typography
                          variant="body2"
                          sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                        >
                          {String(item)}
                        </Typography>
                      }
                      secondary={
                        <Chip
                          label={index}
                          size="small"
                          variant="outlined"
                          sx={{ height: 16, fontSize: '0.65rem' }}
                        />
                      }
                    />
                    <ListItemSecondaryAction>
                      <Tooltip title="Edit">
                        <IconButton
                          size="small"
                          onClick={() => handleStartEdit(index)}
                          disabled={disabled}
                        >
                          <Edit fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Remove">
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleRemoveItem(index)}
                          disabled={disabled || items.length <= minItems}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </ListItemSecondaryAction>
                  </>
                )}
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {items.length > 0 && items.length <= minItems && (
        <Alert severity="info" sx={{ mt: 1, py: 0 }}>
          Minimum {minItems} items required
        </Alert>
      )}
    </Box>
  );
};

export default ArrayEditor;
