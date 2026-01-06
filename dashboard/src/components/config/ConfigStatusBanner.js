// dashboard/src/components/config/ConfigStatusBanner.js
/**
 * Persistent configuration status banner showing save state.
 * Displays all-saved, unsaved changes, saving progress, or errors.
 *
 * @version 5.4.0
 */

import React from 'react';
import PropTypes from 'prop-types';
import {
  Box, Typography, Chip, Button, LinearProgress, IconButton, Tooltip
} from '@mui/material';
import {
  CheckCircle, Warning, Error, Sync, Save, Schedule, Compare
} from '@mui/icons-material';
import { useConfigGlobalState, formatRelativeTime } from '../../hooks/useConfigGlobalState';

/**
 * Status colors and icons for different save states
 */
const statusConfig = {
  idle: {
    color: 'success.main',
    bgColor: 'success.lighter',
    borderColor: 'success.light',
    icon: CheckCircle,
    label: 'All Saved',
  },
  saving: {
    color: 'info.main',
    bgColor: 'info.lighter',
    borderColor: 'info.light',
    icon: Sync,
    label: 'Saving...',
  },
  saved: {
    color: 'success.main',
    bgColor: 'success.lighter',
    borderColor: 'success.light',
    icon: CheckCircle,
    label: 'Saved',
  },
  unsaved: {
    color: 'warning.main',
    bgColor: 'warning.lighter',
    borderColor: 'warning.light',
    icon: Warning,
    label: 'Unsaved Changes',
  },
  error: {
    color: 'error.main',
    bgColor: 'error.lighter',
    borderColor: 'error.light',
    icon: Error,
    label: 'Save Error',
  },
};

/**
 * ConfigStatusBanner - Persistent status indicator for configuration save state.
 *
 * Shows:
 * - All saved: Green checkmark with last save timestamp
 * - Unsaved changes: Yellow warning with param count and Save All button
 * - Saving: Blue spinner
 * - Error: Red alert with retry option
 *
 * @param {Object} props
 * @param {boolean} [props.compact=false] - Use compact mode for mobile
 * @param {Function} [props.onSaveAll] - Callback when Save All is clicked
 * @param {Function} [props.onViewChanges] - Callback when View Changes is clicked
 */
const ConfigStatusBanner = ({
  compact = false,
  onSaveAll,
  onViewChanges,
}) => {
  const {
    totalUnsaved,
    lastSaveTimestamp,
    sectionsWithChanges,
    unsavedParams,
    modifiedFromDefaults,
    saveStatus,
    lastError,
  } = useConfigGlobalState();

  // Determine effective status
  const getEffectiveStatus = () => {
    if (saveStatus === 'saving') return 'saving';
    if (saveStatus === 'error') return 'error';
    if (totalUnsaved > 0) return 'unsaved';
    if (saveStatus === 'saved') return 'saved';
    return 'idle';
  };

  const effectiveStatus = getEffectiveStatus();
  const config = statusConfig[effectiveStatus];
  const StatusIcon = config.icon;

  // Format param list for tooltip
  const getParamListTooltip = () => {
    if (unsavedParams.length === 0) return '';
    const list = unsavedParams.slice(0, 5).map(p => `${p.section}.${p.param}`);
    if (unsavedParams.length > 5) {
      list.push(`...and ${unsavedParams.length - 5} more`);
    }
    return list.join('\n');
  };

  // Compact mode for mobile
  if (compact) {
    return (
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: 0.75,
          bgcolor: config.bgColor,
          borderRadius: 1,
          border: 1,
          borderColor: config.borderColor,
        }}
      >
        <StatusIcon
          sx={{
            fontSize: 18,
            color: config.color,
            ...(effectiveStatus === 'saving' && {
              animation: 'spin 1s linear infinite',
              '@keyframes spin': {
                '0%': { transform: 'rotate(0deg)' },
                '100%': { transform: 'rotate(360deg)' },
              },
            }),
          }}
        />
        <Typography variant="body2" sx={{ color: config.color, fontWeight: 500 }}>
          {totalUnsaved > 0 ? `${totalUnsaved} unsaved` : config.label}
        </Typography>
        {totalUnsaved > 0 && onSaveAll && (
          <IconButton size="small" onClick={onSaveAll} sx={{ ml: 'auto', p: 0.5 }}>
            <Save fontSize="small" />
          </IconButton>
        )}
      </Box>
    );
  }

  // Full mode
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 2,
        py: 1,
        bgcolor: config.bgColor,
        borderRadius: 1,
        border: 1,
        borderColor: config.borderColor,
        flexWrap: 'wrap',
      }}
    >
      {/* Status Icon and Label */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <StatusIcon
          sx={{
            fontSize: 22,
            color: config.color,
            ...(effectiveStatus === 'saving' && {
              animation: 'spin 1s linear infinite',
              '@keyframes spin': {
                '0%': { transform: 'rotate(0deg)' },
                '100%': { transform: 'rotate(360deg)' },
              },
            }),
          }}
        />
        <Typography
          variant="body2"
          sx={{ color: config.color, fontWeight: 600 }}
        >
          {config.label}
        </Typography>
      </Box>

      {/* Saving progress bar */}
      {effectiveStatus === 'saving' && (
        <LinearProgress
          sx={{ width: 100, height: 4, borderRadius: 2 }}
          color="info"
        />
      )}

      {/* Unsaved details */}
      {effectiveStatus === 'unsaved' && (
        <>
          <Tooltip title={getParamListTooltip()} arrow placement="bottom">
            <Chip
              size="small"
              icon={<Warning sx={{ fontSize: 16 }} />}
              label={`${totalUnsaved} param${totalUnsaved > 1 ? 's' : ''}`}
              color="warning"
              variant="outlined"
            />
          </Tooltip>
          {sectionsWithChanges.length > 0 && (
            <Typography variant="caption" color="text.secondary">
              in {sectionsWithChanges.join(', ')}
            </Typography>
          )}
        </>
      )}

      {/* Last save timestamp */}
      {(effectiveStatus === 'idle' || effectiveStatus === 'saved') && lastSaveTimestamp && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <Schedule sx={{ fontSize: 16, color: 'text.secondary' }} />
          <Typography variant="caption" color="text.secondary">
            Last: {formatRelativeTime(lastSaveTimestamp)}
          </Typography>
        </Box>
      )}

      {/* Error details */}
      {effectiveStatus === 'error' && lastError && (
        <Typography variant="caption" color="error.main">
          {lastError.section}.{lastError.param}: {lastError.error}
        </Typography>
      )}

      {/* Spacer */}
      <Box sx={{ flexGrow: 1 }} />

      {/* Modified from defaults indicator */}
      {modifiedFromDefaults > 0 && (
        <Tooltip title="Parameters differing from factory defaults" arrow>
          <Chip
            size="small"
            icon={<Compare sx={{ fontSize: 16 }} />}
            label={`${modifiedFromDefaults} modified`}
            variant="outlined"
            onClick={onViewChanges}
            sx={{ cursor: onViewChanges ? 'pointer' : 'default' }}
          />
        </Tooltip>
      )}

      {/* Save All button */}
      {totalUnsaved > 0 && onSaveAll && (
        <Button
          size="small"
          variant="contained"
          color="warning"
          startIcon={<Save />}
          onClick={onSaveAll}
          sx={{ minWidth: 100 }}
        >
          Save All
        </Button>
      )}

      {/* View Changes button (when saved) */}
      {modifiedFromDefaults > 0 && onViewChanges && effectiveStatus === 'idle' && (
        <Button
          size="small"
          variant="outlined"
          startIcon={<Compare />}
          onClick={onViewChanges}
        >
          View Changes
        </Button>
      )}
    </Box>
  );
};

ConfigStatusBanner.propTypes = {
  /** Use compact mode for mobile */
  compact: PropTypes.bool,
  /** Callback when Save All is clicked */
  onSaveAll: PropTypes.func,
  /** Callback when View Changes is clicked */
  onViewChanges: PropTypes.func,
};

export default ConfigStatusBanner;
