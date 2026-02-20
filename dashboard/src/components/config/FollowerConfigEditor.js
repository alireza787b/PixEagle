// dashboard/src/components/config/FollowerConfigEditor.js
/**
 * FollowerConfigEditor - Specialized editor for Follower operational config
 *
 * Provides a unified, schema-driven interface for editing:
 * - General: Default operational params for all followers (non-removable)
 * - FollowerOverrides: Per-follower operational overrides (sparse)
 *
 * Uses shared components from PropertyEditorShared for consistent UX.
 *
 * Features:
 * - Schema-driven property suggestions via followerConfigSchemaUtils
 * - Generic nested sub-section rendering (driven by NESTED_SUBSECTIONS registry)
 * - Non-removable properties in General mode
 * - Override left border + badge for FollowerOverrides
 * - Collapsible inherited-from-General summary
 * - Enum, boolean, and number type support
 */
import React, { useState, useMemo, useCallback } from 'react';
import {
  Box, Typography, Paper, Alert, Chip, Divider, Collapse,
  Table, TableBody, TableCell, TableHead, TableRow,
  IconButton, Tooltip, Button
} from '@mui/material';
import {
  Add, Delete, Info, Speed, Height, Tune,
  GpsOff, Navigation, RotateRight,
  KeyboardArrowDown, KeyboardArrowUp
} from '@mui/icons-material';

import {
  PROPERTY_CATEGORIES,
  GENERAL_DEFAULTS,
  NESTED_SUBSECTIONS,
  getAddableProperties,
  getPropertyByName,
  getSubsectionPropertyByName,
  getFollowersByType
} from '../../utils/followerConfigSchemaUtils';
import { FOLLOWER_TYPES } from '../../utils/safetySchemaUtils';
import { useResponsive } from '../../hooks/useResponsive';
import {
  PropertyRow, PropertyCard, AddPropertyDialog,
  FollowerSelector, EmptyFollowerState
} from './PropertyEditorShared';

// Category icons (Follower-specific)
const categoryIcons = {
  timing: <Speed fontSize="small" color="primary" />,
  smoothing: <Tune fontSize="small" color="info" />,
  target_loss: <GpsOff fontSize="small" color="error" />,
  guidance: <Navigation fontSize="small" color="warning" />,
  altitude: <Height fontSize="small" color="success" />,
  yaw_smoothing: <RotateRight fontSize="small" color="secondary" />
};

// Static label maps derived from schema constants
const propertyCategoryLabels = Object.fromEntries(
  Object.entries(PROPERTY_CATEGORIES).map(([k, v]) => [k, v.label])
);
const followerTypeLabels = Object.fromEntries(
  Object.entries(FOLLOWER_TYPES).map(([k, v]) => [k, v.label])
);

// Pre-compute the set of nested subsection keys for filtering
const nestedSubsectionKeys = new Set(Object.keys(NESTED_SUBSECTIONS));

/**
 * NestedSubsection - Generic collapsible accordion for a nested object sub-section.
 * Driven entirely by the NESTED_SUBSECTIONS registry — no hardcoded key names.
 */
const NestedSubsection = ({
  subsectionKey,
  data,
  referenceData,
  onChange,
  onRemove,
  showComparison,
  removable = true,
  disabled,
  useCardLayout
}) => {
  const [expanded, setExpanded] = useState(true);
  const config = NESTED_SUBSECTIONS[subsectionKey];

  // Merge with schema defaults so all sub-properties are always visible
  const mergedData = useMemo(() => ({
    ...config.defaults,
    ...(data || {})
  }), [data, config.defaults]);

  // Sparse write-back: only persist the changed key on top of original sparse data
  const handlePropChange = useCallback((propName, newValue) => {
    onChange({ ...(data || {}), [propName]: newValue });
  }, [data, onChange]);

  const entries = Object.entries(mergedData);
  const statusValue = config.statusKey ? mergedData[config.statusKey] : null;

  return (
    <Paper variant="outlined" sx={{ mt: 2 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 1.5,
          cursor: 'pointer',
          '&:hover': { bgcolor: 'action.hover' }
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {categoryIcons[config.category]}
          <Typography variant="subtitle2" color="secondary">
            {config.label}
          </Typography>
          {config.statusKey && (
            <Chip
              label={statusValue ? 'Active' : 'Disabled'}
              size="small"
              color={statusValue ? 'success' : 'default'}
              sx={{ height: 20, fontSize: '0.65rem' }}
            />
          )}
          {showComparison && (
            <Chip label="Override" size="small" color="warning" sx={{ height: 18, fontSize: '0.6rem' }} />
          )}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {removable && onRemove && (
            <Tooltip title={`Remove ${config.label} override`}>
              <IconButton
                size="small"
                onClick={(e) => { e.stopPropagation(); onRemove(); }}
                disabled={disabled}
              >
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {expanded ? <KeyboardArrowUp fontSize="small" /> : <KeyboardArrowDown fontSize="small" />}
        </Box>
      </Box>

      <Collapse in={expanded}>
        <Divider />
        <Box sx={{ p: useCardLayout ? 1 : 0 }}>
          {useCardLayout ? (
            <Box sx={{ pt: 1 }}>
              {entries.map(([propName, propValue]) => (
                <PropertyCard
                  key={propName}
                  propertyName={propName}
                  value={propValue}
                  referenceValue={referenceData?.[propName]}
                  onChange={handlePropChange}
                  showComparison={showComparison}
                  removable={false}
                  disabled={disabled}
                  propMetaOverride={getSubsectionPropertyByName(subsectionKey, propName)}
                  categoryIcons={categoryIcons}
                  referenceLabel="General"
                />
              ))}
            </Box>
          ) : (
            <Table size="small" sx={{ tableLayout: 'fixed', width: '100%' }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: showComparison ? '30%' : '40%' }}>Property</TableCell>
                  <TableCell sx={{ width: showComparison ? '25%' : '35%' }}>Value</TableCell>
                  {showComparison && <TableCell sx={{ width: '25%' }}>General Value</TableCell>}
                  <TableCell align="right" sx={{ width: showComparison ? '20%' : '25%' }}>&nbsp;</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entries.map(([propName, propValue]) => (
                  <PropertyRow
                    key={propName}
                    propertyName={propName}
                    value={propValue}
                    referenceValue={referenceData?.[propName]}
                    onChange={handlePropChange}
                    showComparison={showComparison}
                    removable={false}
                    disabled={disabled}
                    propMetaOverride={getSubsectionPropertyByName(subsectionKey, propName)}
                    categoryIcons={categoryIcons}
                    referenceLabel="General"
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </Box>
      </Collapse>
    </Paper>
  );
};

/**
 * Collapsible Inherited Properties Summary for FollowerOverrides.
 * Shows properties inherited from General that are NOT overridden.
 * Collapsed by default — expands on click.
 */
const InheritedSummary = ({ generalDefaults, overrideKeys }) => {
  const [expanded, setExpanded] = useState(false);

  const inheritedEntries = useMemo(() => {
    const allGeneral = { ...GENERAL_DEFAULTS, ...generalDefaults };
    return Object.entries(allGeneral).filter(
      ([key]) => !overrideKeys.includes(key) && !nestedSubsectionKeys.has(key)
    );
  }, [generalDefaults, overrideKeys]);

  if (inheritedEntries.length === 0) return null;

  return (
    <Paper variant="outlined" sx={{ mt: 2, bgcolor: 'action.hover' }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 2,
          py: 1.5,
          cursor: 'pointer',
          '&:hover': { bgcolor: 'action.selected' }
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Typography variant="subtitle2" color="text.secondary">
          Inherited from General ({inheritedEntries.length} properties)
        </Typography>
        {expanded ? <KeyboardArrowUp fontSize="small" /> : <KeyboardArrowDown fontSize="small" />}
      </Box>
      <Collapse in={expanded}>
        <Box sx={{ px: 2, pb: 2, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
          {inheritedEntries.map(([key, val]) => {
            const meta = getPropertyByName(key);
            const displayVal = meta?.type === 'boolean'
              ? (val ? 'ON' : 'OFF')
              : meta?.type === 'enum'
                ? String(val)
                : `${val}${meta?.unit ? ' ' + meta.unit : ''}`;
            return (
              <Chip
                key={key}
                label={`${key}: ${displayVal}`}
                size="small"
                variant="outlined"
                color="default"
                sx={{ fontSize: '0.7rem' }}
              />
            );
          })}
        </Box>
      </Collapse>
    </Paper>
  );
};

/**
 * Main FollowerConfigEditor Component
 */
const FollowerConfigEditor = ({
  type,                    // 'General' | 'FollowerOverrides'
  value,                   // Current object value
  onChange,                // Callback for changes
  generalDefaults = {},    // Reference for comparison (FollowerOverrides only)
  disabled = false
}) => {
  const isOverrides = type === 'FollowerOverrides';
  const [selectedFollower, setSelectedFollower] = useState('');
  const [addDialogOpen, setAddDialogOpen] = useState(false);

  const { isMobile, isTablet } = useResponsive();
  const useCardLayout = isMobile || isTablet;

  const followersByType = useMemo(() => getFollowersByType(), []);

  // Build effective value: merge GENERAL_DEFAULTS + all nested subsection defaults
  const effectiveValue = useMemo(() => {
    if (!isOverrides) {
      const base = { ...GENERAL_DEFAULTS };
      Object.entries(NESTED_SUBSECTIONS).forEach(([key, config]) => {
        base[key] = { ...config.defaults };
      });
      return { ...base, ...(value || {}) };
    }
    return value || {};
  }, [isOverrides, value]);

  const currentProperties = useMemo(() => {
    if (isOverrides) {
      return selectedFollower ? (effectiveValue?.[selectedFollower] || {}) : {};
    }
    return effectiveValue;
  }, [isOverrides, selectedFollower, effectiveValue]);

  // Separate flat properties from nested sub-sections (schema-driven)
  const { flatProperties, activeSubsections } = useMemo(() => {
    const flat = {};
    const nested = {};
    Object.entries(currentProperties).forEach(([key, val]) => {
      if (nestedSubsectionKeys.has(key) && typeof val === 'object' && val !== null && !Array.isArray(val)) {
        nested[key] = val;
      } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
        // Skip unknown nested objects to prevent corruption
      } else {
        flat[key] = val;
      }
    });
    return { flatProperties: flat, activeSubsections: nested };
  }, [currentProperties]);

  const followerOverrideCounts = useMemo(() => {
    if (!isOverrides || !effectiveValue) return {};
    const counts = {};
    Object.entries(effectiveValue).forEach(([follower, props]) => {
      counts[follower] = Object.keys(props || {}).length;
    });
    return counts;
  }, [isOverrides, effectiveValue]);

  const handlePropertyChange = useCallback((propName, newValue) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(effectiveValue?.[selectedFollower] || {}), [propName]: newValue };
      onChange({ ...effectiveValue, [selectedFollower]: followerProps });
    } else {
      onChange({ ...effectiveValue, [propName]: newValue });
    }
  }, [isOverrides, selectedFollower, effectiveValue, onChange]);

  const handlePropertyRemove = useCallback((propName) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(effectiveValue?.[selectedFollower] || {}) };
      delete followerProps[propName];
      if (Object.keys(followerProps).length === 0) {
        const newValue = { ...effectiveValue };
        delete newValue[selectedFollower];
        onChange(newValue);
      } else {
        onChange({ ...effectiveValue, [selectedFollower]: followerProps });
      }
    } else {
      const newValue = { ...effectiveValue };
      delete newValue[propName];
      onChange(newValue);
    }
  }, [isOverrides, selectedFollower, effectiveValue, onChange]);

  const handlePropertyAdd = useCallback((propName, propValue, followerFromDialog) => {
    if (isOverrides) {
      const targetFollower = followerFromDialog || selectedFollower;
      if (!targetFollower) return;
      if (followerFromDialog && followerFromDialog !== selectedFollower) {
        setSelectedFollower(followerFromDialog);
      }
      const followerProps = { ...(effectiveValue?.[targetFollower] || {}), [propName]: propValue };
      onChange({ ...effectiveValue, [targetFollower]: followerProps });
    } else {
      onChange({ ...effectiveValue, [propName]: propValue });
    }
  }, [isOverrides, selectedFollower, effectiveValue, onChange]);

  // Generic handler for any nested sub-section change
  const handleSubsectionChange = useCallback((subsectionKey, newData) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(effectiveValue?.[selectedFollower] || {}), [subsectionKey]: newData };
      onChange({ ...effectiveValue, [selectedFollower]: followerProps });
    } else {
      onChange({ ...effectiveValue, [subsectionKey]: newData });
    }
  }, [isOverrides, selectedFollower, effectiveValue, onChange]);

  // Generic handler for removing any nested sub-section override
  const handleSubsectionRemove = useCallback((subsectionKey) => {
    if (isOverrides) {
      if (!selectedFollower) return;
      const followerProps = { ...(effectiveValue?.[selectedFollower] || {}) };
      delete followerProps[subsectionKey];
      if (Object.keys(followerProps).length === 0) {
        const newValue = { ...effectiveValue };
        delete newValue[selectedFollower];
        onChange(newValue);
      } else {
        onChange({ ...effectiveValue, [selectedFollower]: followerProps });
      }
    }
  }, [isOverrides, selectedFollower, effectiveValue, onChange]);

  const handleRemoveFollower = useCallback(() => {
    if (!selectedFollower || !isOverrides) return;
    const newValue = { ...effectiveValue };
    delete newValue[selectedFollower];
    onChange(newValue);
    setSelectedFollower('');
  }, [selectedFollower, isOverrides, effectiveValue, onChange]);

  const flatEntries = Object.entries(flatProperties);
  const hasFlatProperties = flatEntries.length > 0;
  const hasActiveSubsections = Object.keys(activeSubsections).length > 0;
  const hasAnyContent = hasFlatProperties || hasActiveSubsections;

  const overrideKeys = useMemo(() => Object.keys(currentProperties), [currentProperties]);

  // Determine which sub-sections are missing (for "Add Override" buttons)
  const missingSubsections = useMemo(() => {
    if (!isOverrides || !selectedFollower) return [];
    return Object.entries(NESTED_SUBSECTIONS)
      .filter(([key]) => !(key in activeSubsections))
      .map(([key, config]) => ({ key, config }));
  }, [isOverrides, selectedFollower, activeSubsections]);

  // Reference data for nested sub-sections in overrides mode
  const getSubsectionReferenceData = useCallback((subsectionKey) => {
    if (!isOverrides) return null;
    return generalDefaults?.[subsectionKey] || NESTED_SUBSECTIONS[subsectionKey]?.defaults;
  }, [isOverrides, generalDefaults]);

  return (
    <Box>
      {/* Instructions */}
      <Alert severity="info" sx={{ mb: 2 }} icon={<Info />}>
        {isOverrides ? (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              Per-Follower Config Overrides
            </Typography>
            <Typography variant="caption">
              Override specific operational params for individual followers.
              Empty = uses General defaults. Only set what differs from General.
            </Typography>
          </Box>
        ) : (
          <Box>
            <Typography variant="body2" fontWeight="medium">
              General Follower Defaults
            </Typography>
            <Typography variant="caption">
              Shared operational parameters applied to all followers.
              Individual followers can override these via FollowerOverrides.
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
          hint="Or the FollowerOverrides section is empty (using General defaults for all)"
        />
      ) : (
        <Box>
          {/* Flat properties */}
          {hasFlatProperties ? (
            useCardLayout ? (
              <Box>
                {flatEntries.map(([propName, propValue]) => (
                  <PropertyCard
                    key={propName}
                    propertyName={propName}
                    value={propValue}
                    referenceValue={generalDefaults?.[propName]}
                    onChange={handlePropertyChange}
                    onRemove={handlePropertyRemove}
                    showComparison={isOverrides}
                    removable={isOverrides}
                    isOverride={isOverrides}
                    disabled={disabled}
                    getPropertyMeta={getPropertyByName}
                    categoryIcons={categoryIcons}
                    referenceLabel="General"
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
                      {isOverrides && <TableCell sx={{ width: '25%' }}>General Value</TableCell>}
                      <TableCell align="right" sx={{ width: isOverrides ? '20%' : '25%', whiteSpace: 'nowrap' }}>
                        {isOverrides ? 'Actions' : ''}
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {flatEntries.map(([propName, propValue]) => (
                      <PropertyRow
                        key={propName}
                        propertyName={propName}
                        value={propValue}
                        referenceValue={generalDefaults?.[propName]}
                        onChange={handlePropertyChange}
                        onRemove={handlePropertyRemove}
                        showComparison={isOverrides}
                        removable={isOverrides}
                        isOverride={isOverrides}
                        disabled={disabled}
                        getPropertyMeta={getPropertyByName}
                        categoryIcons={categoryIcons}
                        referenceLabel="General"
                      />
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            )
          ) : !hasActiveSubsections ? (
            <Paper variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                {isOverrides
                  ? 'No overrides configured for this follower.'
                  : 'No properties configured.'}
              </Typography>
              <Typography variant="caption" color="text.disabled">
                Click "Add Property" below to add config parameters.
              </Typography>
            </Paper>
          ) : null}

          {/* Nested sub-sections (schema-driven) */}
          {Object.entries(activeSubsections).map(([key, data]) => (
            <NestedSubsection
              key={key}
              subsectionKey={key}
              data={data}
              referenceData={getSubsectionReferenceData(key)}
              onChange={(newData) => handleSubsectionChange(key, newData)}
              onRemove={isOverrides ? () => handleSubsectionRemove(key) : undefined}
              showComparison={isOverrides}
              removable={isOverrides}
              disabled={disabled}
              useCardLayout={useCardLayout}
            />
          ))}

          {/* Inherited from General summary (FollowerOverrides only) */}
          {isOverrides && selectedFollower && (
            <InheritedSummary
              generalDefaults={generalDefaults}
              overrideKeys={overrideKeys}
            />
          )}

          {/* Action Buttons */}
          <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-start', flexWrap: 'wrap' }}>
            {isOverrides && (
              <Button
                variant="outlined"
                startIcon={<Add />}
                onClick={() => setAddDialogOpen(true)}
                disabled={disabled}
              >
                Add Property
              </Button>
            )}

            {/* Add override buttons for missing nested sub-sections */}
            {missingSubsections.map(({ key, config }) => (
              <Button
                key={key}
                variant="outlined"
                startIcon={categoryIcons[config.category]}
                onClick={() => handleSubsectionChange(key, {})}
                disabled={disabled}
              >
                Add {config.label} Override
              </Button>
            ))}

            {isOverrides && selectedFollower && hasAnyContent && (
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
          existingProperties={flatProperties}
          referenceDefaults={generalDefaults}
          showComparison={isOverrides}
          isOverrides={isOverrides}
          selectedFollower={selectedFollower}
          onFollowerChange={setSelectedFollower}
          followersByType={followersByType}
          getAddableProperties={getAddableProperties}
          getPropertyMeta={getPropertyByName}
          categoryIcons={categoryIcons}
          propertyCategoryLabels={propertyCategoryLabels}
          dialogTitle={isOverrides ? 'Add Follower Config Override' : 'Add Follower Config Property'}
          referenceLabel="General"
          followerTypeLabels={followerTypeLabels}
        />
      )}
    </Box>
  );
};

export default FollowerConfigEditor;
