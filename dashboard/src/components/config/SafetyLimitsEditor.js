// dashboard/src/components/config/SafetyLimitsEditor.js
/**
 * SafetyLimitsEditor - Specialized editor for Safety configuration
 *
 * Provides a unified, schema-driven interface for editing:
 * - GlobalLimits: Default safety limits for all followers
 * - FollowerOverrides: Per-follower limit overrides
 *
 * Uses shared components from PropertyEditorShared for consistent UX.
 */
import React, { useState, useMemo, useCallback } from 'react';
import {
  Box, Typography, Paper, Alert, Button,
  Table, TableBody, TableCell, TableHead, TableRow
} from '@mui/material';
import { Add, Delete, Info, Speed, Height, RotateRight } from '@mui/icons-material';

import {
  PROPERTY_CATEGORIES,
  FOLLOWER_TYPES,
  getAddableProperties,
  getPropertyByName,
  getFollowersByType
} from '../../utils/safetySchemaUtils';
import { useResponsive } from '../../hooks/useResponsive';
import {
  PropertyRow, PropertyCard, AddPropertyDialog,
  FollowerSelector, EmptyFollowerState
} from './PropertyEditorShared';

// Category icons (Safety-specific)
const categoryIcons = {
  altitude: <Height fontSize="small" color="success" />,
  velocity: <Speed fontSize="small" color="primary" />,
  rates: <RotateRight fontSize="small" color="warning" />
};

// Static label maps derived from schema constants
const propertyCategoryLabels = Object.fromEntries(
  Object.entries(PROPERTY_CATEGORIES).map(([k, v]) => [k, v.label])
);
const followerTypeLabels = Object.fromEntries(
  Object.entries(FOLLOWER_TYPES).map(([k, v]) => [k, v.label])
);

/**
 * Main SafetyLimitsEditor Component
 */
const SafetyLimitsEditor = ({
  type,                    // 'GlobalLimits' | 'FollowerOverrides'
  value,                   // Current object value
  onChange,                // Callback for changes
  globalLimits = {},       // Reference for comparison (FollowerOverrides only)
  disabled = false
}) => {
  const isOverrides = type === 'FollowerOverrides';
  const [selectedFollower, setSelectedFollower] = useState('');
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  const { isMobile, isTablet } = useResponsive();
  const useCardLayout = isMobile || isTablet;

  const followersByType = useMemo(() => getFollowersByType(), []);

  const currentProperties = useMemo(() => {
    if (isOverrides) {
      return selectedFollower ? (value?.[selectedFollower] || {}) : {};
    }
    return value || {};
  }, [isOverrides, selectedFollower, value]);

  const followerOverrideCounts = useMemo(() => {
    if (!isOverrides || !value) return {};
    const counts = {};
    Object.entries(value).forEach(([follower, props]) => {
      counts[follower] = Object.keys(props || {}).length;
    });
    return counts;
  }, [isOverrides, value]);

  const handlePropertyChange = useCallback((propName, newValue) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(value?.[selectedFollower] || {}), [propName]: newValue };
      onChange({ ...value, [selectedFollower]: followerProps });
    } else {
      onChange({ ...value, [propName]: newValue });
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handlePropertyRemove = useCallback((propName) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(value?.[selectedFollower] || {}) };
      delete followerProps[propName];
      if (Object.keys(followerProps).length === 0) {
        const newValue = { ...value };
        delete newValue[selectedFollower];
        onChange(newValue);
      } else {
        onChange({ ...value, [selectedFollower]: followerProps });
      }
    } else {
      const newValue = { ...value };
      delete newValue[propName];
      onChange(newValue);
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handlePropertyAdd = useCallback((propName, propValue, followerFromDialog) => {
    if (isOverrides) {
      const targetFollower = followerFromDialog || selectedFollower;
      if (!targetFollower) return;
      if (followerFromDialog && followerFromDialog !== selectedFollower) {
        setSelectedFollower(followerFromDialog);
      }
      const followerProps = { ...(value?.[targetFollower] || {}), [propName]: propValue };
      onChange({ ...value, [targetFollower]: followerProps });
    } else {
      onChange({ ...value, [propName]: propValue });
    }
  }, [isOverrides, selectedFollower, value, onChange]);

  const handleRemoveFollower = useCallback(() => {
    if (!selectedFollower || !isOverrides) return;
    const newValue = { ...value };
    delete newValue[selectedFollower];
    onChange(newValue);
    setSelectedFollower('');
  }, [selectedFollower, isOverrides, value, onChange]);

  const propertyEntries = Object.entries(currentProperties);
  const hasProperties = propertyEntries.length > 0;

  return (
    <Box>
      {/* Instructions */}
      <Alert severity="info" sx={{ mb: 2 }} icon={<Info />}>
        {isOverrides ? (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              Per-Follower Safety Overrides
            </Typography>
            <Typography variant="caption">
              Override specific limits for individual followers. Empty = uses GlobalLimits.
              This is an advanced feature for specialized configurations.
            </Typography>
          </Box>
        ) : (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              Global Safety Limits
            </Typography>
            <Typography variant="caption">
              Set default safety limits applied to all followers. These are the single source
              of truth for safety-critical parameters.
            </Typography>
          </Box>
        )}
      </Alert>

      {/* Follower Selector (FollowerOverrides only) */}
      {isOverrides && (
        <FollowerSelector
          selectedFollower={selectedFollower}
          onFollowerChange={setSelectedFollower}
          followersByType={followersByType}
          followerOverrideCounts={followerOverrideCounts}
          followerTypeLabels={followerTypeLabels}
        />
      )}

      {/* Properties Display */}
      {(isOverrides && !selectedFollower) ? (
        <EmptyFollowerState
          message="Select a follower above to configure overrides"
          hint="Or the FollowerOverrides section is empty (using GlobalLimits for all)"
        />
      ) : (
        <Box>
          {hasProperties ? (
            useCardLayout ? (
              <Box>
                {propertyEntries.map(([propName, propValue]) => (
                  <PropertyCard
                    key={propName}
                    propertyName={propName}
                    value={propValue}
                    referenceValue={globalLimits?.[propName]}
                    onChange={handlePropertyChange}
                    onRemove={handlePropertyRemove}
                    showComparison={isOverrides}
                    disabled={disabled}
                    getPropertyMeta={getPropertyByName}
                    categoryIcons={categoryIcons}
                    referenceLabel="Global"
                  />
                ))}
              </Box>
            ) : (
              <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
                <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: isOverrides ? '30%' : '40%' }}>Property</TableCell>
                      <TableCell sx={{ width: isOverrides ? '25%' : '35%' }}>Value</TableCell>
                      {isOverrides && <TableCell sx={{ width: '25%' }}>Global Value</TableCell>}
                      <TableCell align="right" sx={{ width: isOverrides ? '20%' : '25%', whiteSpace: 'nowrap' }}>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {propertyEntries.map(([propName, propValue]) => (
                      <PropertyRow
                        key={propName}
                        propertyName={propName}
                        value={propValue}
                        referenceValue={globalLimits?.[propName]}
                        onChange={handlePropertyChange}
                        onRemove={handlePropertyRemove}
                        showComparison={isOverrides}
                        disabled={disabled}
                        getPropertyMeta={getPropertyByName}
                        categoryIcons={categoryIcons}
                        referenceLabel="Global"
                      />
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            )
          ) : (
            <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                {isOverrides
                  ? 'No overrides configured for this follower.'
                  : 'No properties configured.'}
              </Typography>
              <Typography variant="caption" color="text.disabled">
                Click "Add Property" below to add limits.
              </Typography>
            </Paper>
          )}

          {/* Action Buttons */}
          <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start', flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              startIcon={<Add />}
              onClick={() => setAddDialogOpen(true)}
              disabled={disabled}
            >
              Add Property
            </Button>

            {isOverrides && selectedFollower && hasProperties && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<Delete />}
                onClick={handleRemoveFollower}
                disabled={disabled}
              >
                Remove All Overrides
              </Button>
            )}
          </Box>
        </Box>
      )}

      {/* Add Property Dialog */}
      {addDialogOpen && (
        <AddPropertyDialog
          open={addDialogOpen}
          onClose={() => setAddDialogOpen(false)}
          onAdd={handlePropertyAdd}
          existingProperties={currentProperties}
          referenceDefaults={globalLimits}
          showComparison={isOverrides}
          isOverrides={isOverrides}
          selectedFollower={selectedFollower}
          onFollowerChange={setSelectedFollower}
          followersByType={followersByType}
          getAddableProperties={getAddableProperties}
          getPropertyMeta={getPropertyByName}
          categoryIcons={categoryIcons}
          propertyCategoryLabels={propertyCategoryLabels}
          dialogTitle={isOverrides ? 'Add Follower Override Property' : 'Add Safety Limit Property'}
          referenceLabel="Global"
          followerTypeLabels={followerTypeLabels}
        />
      )}
    </Box>
  );
};

export default SafetyLimitsEditor;
