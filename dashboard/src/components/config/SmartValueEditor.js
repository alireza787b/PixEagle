// dashboard/src/components/config/SmartValueEditor.js
import React, { useMemo, useCallback, useState } from 'react';
import {
  Box, Typography, IconButton, Tooltip, Paper, Divider,
  TextField, Button, Chip
} from '@mui/material';
import {
  Undo, Redo, RestartAlt, Code, Edit, ExpandMore, ExpandLess
} from '@mui/icons-material';

import { analyzeSchema, PatternType } from '../../utils/schemaAnalyzer';
import { useUndoStack } from '../../hooks/useUndoStack';
import { useResponsive } from '../../hooks/useResponsive';
import TypeRendererRegistry from './renderers';

// Import renderers to ensure registry is populated
import './renderers';

/**
 * SmartValueEditor - Unified schema-driven editor for complex values
 *
 * Features:
 * - Auto-detects value patterns (PID, arrays, objects)
 * - Uses specialized renderers based on pattern
 * - Built-in undo/redo functionality
 * - Compact, inline, and full display modes
 * - Falls back to JSON editor for unknown types
 * - Dark mode compatible
 */

// JSON fallback editor for unknown/complex types
const JSONEditor = ({ value, onChange, disabled, compact, error }) => {
  const [localValue, setLocalValue] = useState(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  });
  const [parseError, setParseError] = useState(null);

  const handleChange = (e) => {
    setLocalValue(e.target.value);
    setParseError(null);
  };

  const handleBlur = () => {
    try {
      const parsed = JSON.parse(localValue);
      onChange(parsed);
      setParseError(null);
    } catch (err) {
      setParseError(`Invalid JSON: ${err.message}`);
    }
  };

  return (
    <Box>
      <TextField
        multiline
        fullWidth
        value={localValue}
        onChange={handleChange}
        onBlur={handleBlur}
        disabled={disabled}
        minRows={compact ? 2 : 4}
        maxRows={compact ? 4 : 12}
        error={!!parseError || !!error}
        helperText={parseError || error}
        sx={{
          '& .MuiOutlinedInput-root': {
            fontFamily: 'monospace',
            fontSize: compact ? '0.75rem' : '0.85rem'
          },
          '& textarea': {
            fontFamily: 'monospace'
          }
        }}
        InputProps={{
          startAdornment: (
            <Box sx={{ alignSelf: 'flex-start', pt: 1, pr: 1 }}>
              <Code fontSize="small" color="action" />
            </Box>
          )
        }}
      />
    </Box>
  );
};

// Preview chip showing value summary
const ValuePreview = ({ analysis, onClick, disabled }) => {
  return (
    <Tooltip title="Click to edit" arrow>
      <Chip
        label={analysis.previewText || 'Edit value'}
        onClick={onClick}
        disabled={disabled}
        size="small"
        icon={<Edit fontSize="small" />}
        variant="outlined"
        sx={{
          maxWidth: 200,
          '& .MuiChip-label': {
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }
        }}
      />
    </Tooltip>
  );
};

// Undo/Redo toolbar
const UndoRedoToolbar = ({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onReset,
  hasChanges,
  historyInfo,
  compact
}) => {
  if (compact) return null;

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        py: 0.5,
        px: 1,
        bgcolor: 'action.hover',
        borderRadius: 1,
        mb: 1
      }}
    >
      <Tooltip title={canUndo ? 'Undo' : 'Nothing to undo'}>
        <span>
          <IconButton size="small" onClick={onUndo} disabled={!canUndo}>
            <Undo fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      <Tooltip title={canRedo ? 'Redo' : 'Nothing to redo'}>
        <span>
          <IconButton size="small" onClick={onRedo} disabled={!canRedo}>
            <Redo fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      <Tooltip title="Reset to original">
        <span>
          <IconButton size="small" onClick={onReset} disabled={!hasChanges}>
            <RestartAlt fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      {hasChanges && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ ml: 'auto', fontSize: '0.7rem' }}
        >
          {historyInfo.position}/{historyInfo.total}
        </Typography>
      )}
    </Box>
  );
};

const SmartValueEditor = ({
  value,
  onChange,
  schema,
  mode = 'auto',  // 'compact' | 'inline' | 'full' | 'auto'
  disabled = false,
  showUndoRedo = true,
  onValidationError = null,
  label = '',
  showLabel = false
}) => {
  const { isMobile } = useResponsive();

  // Analyze schema to determine pattern
  const analysis = useMemo(() => {
    return analyzeSchema(schema, value);
  }, [schema, value]);

  // Determine display mode
  const displayMode = useMemo(() => {
    // Respect explicit mode request
    if (mode !== 'auto') return mode;

    // Auto-detect based on complexity (device-agnostic)
    switch (analysis.pattern) {
      case PatternType.PID_TRIPLET:
        return 'inline';
      case PatternType.AXIS_PID_GROUP:
        return 'full';
      case PatternType.SCALAR_ARRAY:
      case PatternType.STRING_ARRAY:
        return analysis.complexity > 5 ? 'full' : 'inline';
      case PatternType.FLAT_OBJECT:
        return analysis.complexity > 5 ? 'full' : 'inline';
      case PatternType.NESTED_OBJECT:
        return 'full';
      default:
        return 'inline';
    }
  }, [mode, analysis]);

  const isCompact = displayMode === 'compact';
  const isFull = displayMode === 'full';

  // Undo/redo stack (only for full mode)
  const {
    value: currentValue,
    push,
    undo,
    redo,
    resetToInitial,
    canUndo,
    canRedo,
    hasChanges,
    historyInfo
  } = useUndoStack(value);

  // Use undo stack in full mode, direct value otherwise
  const editValue = isFull && showUndoRedo ? currentValue : value;

  const handleChange = useCallback((newValue) => {
    if (isFull && showUndoRedo) {
      push(newValue);
    }
    onChange(newValue);
  }, [isFull, showUndoRedo, push, onChange]);

  const handleReset = useCallback(() => {
    resetToInitial();
    onChange(value);
  }, [resetToInitial, onChange, value]);

  // Get renderer for this pattern
  const Renderer = useMemo(() => {
    return TypeRendererRegistry.get(analysis.pattern);
  }, [analysis.pattern]);

  // State for inline expansion
  const [expanded, setExpanded] = useState(false);

  // Render content based on mode
  const renderContent = () => {
    // Use specialized renderer if available
    if (Renderer) {
      return (
        <Renderer
          value={editValue}
          onChange={handleChange}
          schema={schema}
          disabled={disabled}
          compact={isCompact}
          isMobile={isMobile}
        />
      );
    }

    // Fallback to JSON editor
    return (
      <JSONEditor
        value={editValue}
        onChange={handleChange}
        disabled={disabled}
        compact={isCompact}
      />
    );
  };

  // Compact mode - just show preview chip
  if (isCompact && !expanded) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <ValuePreview
          analysis={analysis}
          onClick={() => setExpanded(true)}
          disabled={disabled}
        />
        <IconButton size="small" onClick={() => setExpanded(true)}>
          <ExpandMore fontSize="small" />
        </IconButton>
      </Box>
    );
  }

  // Inline mode - render directly
  if (displayMode === 'inline') {
    return (
      <Box>
        {showLabel && label && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mb: 0.5, display: 'block' }}
          >
            {label}
          </Typography>
        )}
        {renderContent()}
      </Box>
    );
  }

  // Full mode with toolbar and panel
  return (
    <Box>
      {/* Label */}
      {showLabel && label && (
        <Typography
          variant="subtitle2"
          color="text.primary"
          sx={{ mb: 1 }}
        >
          {label}
        </Typography>
      )}

      {/* Pattern indicator */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Chip
          label={analysis.pattern.replace(/_/g, ' ')}
          size="small"
          color="primary"
          variant="outlined"
          sx={{ textTransform: 'capitalize', fontSize: '0.7rem' }}
        />
        {analysis.complexity > 0 && (
          <Typography variant="caption" color="text.secondary">
            Complexity: {analysis.complexity}
          </Typography>
        )}
      </Box>

      {/* Undo/Redo toolbar */}
      {showUndoRedo && (
        <UndoRedoToolbar
          canUndo={canUndo}
          canRedo={canRedo}
          onUndo={undo}
          onRedo={redo}
          onReset={handleReset}
          hasChanges={hasChanges}
          historyInfo={historyInfo}
          compact={isCompact}
        />
      )}

      {/* Main content */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          bgcolor: 'background.paper'
        }}
      >
        {renderContent()}
      </Paper>

      {/* Compact expand/collapse */}
      {isCompact && expanded && (
        <Box sx={{ mt: 1, textAlign: 'center' }}>
          <Button
            size="small"
            startIcon={<ExpandLess />}
            onClick={() => setExpanded(false)}
          >
            Collapse
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default SmartValueEditor;

// Also export for destructured imports
export { SmartValueEditor };
