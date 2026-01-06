// dashboard/src/components/config/MobileBottomBar.js
/**
 * MobileBottomBar - Fixed bottom action bar for mobile (v5.4.0+)
 *
 * Provides:
 * - Save All button (when unsaved changes exist)
 * - View Changes button
 * - Touch-friendly 48px height with 44px touch targets
 */

import React from 'react';
import PropTypes from 'prop-types';
import { Box, Button, Badge, Typography, useTheme } from '@mui/material';
import { Save, CompareArrows, Check } from '@mui/icons-material';

import { useConfigGlobalState } from '../../hooks/useConfigGlobalState';

/**
 * MobileBottomBar - Fixed bottom action bar for mobile settings
 *
 * @param {Object} props
 * @param {number} [props.changesCount=0] - Number of changes from defaults
 * @param {Function} [props.onSaveAll] - Callback when Save All is clicked
 * @param {Function} [props.onViewChanges] - Callback when View Changes is clicked
 */
const MobileBottomBar = ({
  changesCount = 0,
  onSaveAll,
  onViewChanges,
}) => {
  const theme = useTheme();
  const globalState = useConfigGlobalState();

  const unsavedCount = globalState.totalUnsaved || 0;
  const allSaved = globalState.allSaved;
  const saveStatus = globalState.saveStatus;

  return (
    <Box
      sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        height: 64,
        bgcolor: 'background.paper',
        borderTop: 1,
        borderColor: 'divider',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        px: 2,
        zIndex: theme.zIndex.appBar,
        boxShadow: '0 -2px 8px rgba(0,0,0,0.1)',
      }}
    >
      {/* Save All Button */}
      {unsavedCount > 0 ? (
        <Button
          variant="contained"
          color="warning"
          startIcon={saveStatus === 'saving' ? null : <Save />}
          onClick={onSaveAll}
          disabled={saveStatus === 'saving'}
          sx={{
            minHeight: 44,
            minWidth: 140,
            flex: 1,
            maxWidth: 200,
          }}
        >
          <Badge badgeContent={unsavedCount} color="error" max={99}>
            <Typography variant="button" sx={{ pr: unsavedCount > 0 ? 1.5 : 0 }}>
              {saveStatus === 'saving' ? 'Saving...' : 'Save All'}
            </Typography>
          </Badge>
        </Button>
      ) : (
        <Button
          variant="outlined"
          color="success"
          startIcon={<Check />}
          disabled
          sx={{
            minHeight: 44,
            minWidth: 140,
            flex: 1,
            maxWidth: 200,
          }}
        >
          All Saved
        </Button>
      )}

      {/* View Changes Button */}
      <Button
        variant="outlined"
        startIcon={<CompareArrows />}
        onClick={onViewChanges}
        disabled={changesCount === 0}
        sx={{
          minHeight: 44,
          minWidth: 140,
          flex: 1,
          maxWidth: 200,
        }}
      >
        <Badge badgeContent={changesCount} color="info" max={99}>
          <Typography variant="button" sx={{ pr: changesCount > 0 ? 1.5 : 0 }}>
            Changes
          </Typography>
        </Badge>
      </Button>
    </Box>
  );
};

MobileBottomBar.propTypes = {
  /** Number of parameters that differ from defaults */
  changesCount: PropTypes.number,
  /** Callback when Save All is clicked */
  onSaveAll: PropTypes.func,
  /** Callback when View Changes is clicked */
  onViewChanges: PropTypes.func,
};

export default MobileBottomBar;
