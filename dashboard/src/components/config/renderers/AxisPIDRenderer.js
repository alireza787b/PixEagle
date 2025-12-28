// dashboard/src/components/config/renderers/AxisPIDRenderer.js
import React, { useState, useCallback, useMemo } from 'react';
import {
  Box, Typography, Collapse, IconButton, Paper,
  Tooltip, Chip, TextField, InputAdornment
} from '@mui/material';
import {
  ExpandMore, ExpandLess, Search
} from '@mui/icons-material';
import PIDRenderer from './PIDRenderer';
import { groupPIDAxes } from '../../../utils/schemaAnalyzer';

/**
 * AxisPIDRenderer - Grid layout for multiple PID axes
 *
 * Features:
 * - Collapsible axis groups (Position, Rate, Velocity, etc.)
 * - Each axis shows PIDRenderer inline
 * - Descriptions from schema
 * - Search/filter functionality
 * - Responsive layout
 */

// Axis label formatting
const formatAxisLabel = (key) => {
  // Convert snake_case and camelCase to readable labels
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b(deg|s|mc|fw|mcar)\b/gi, (m) => m.toUpperCase())
    .replace(/\bvel\b/gi, 'Velocity')
    .trim();
};

// Get description for an axis from schema
const getAxisDescription = (key, schema) => {
  return schema?.properties?.[key]?.description || null;
};

const AxisGroup = ({
  group,
  value,
  onChange,
  schema,
  disabled,
  compact,
  defaultExpanded
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Paper
      variant="outlined"
      sx={{
        mb: 1,
        overflow: 'hidden',
        bgcolor: 'background.paper'
      }}
    >
      {/* Group Header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          px: 1.5,
          py: 1,
          cursor: 'pointer',
          bgcolor: 'action.hover',
          '&:hover': { bgcolor: 'action.selected' }
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography variant="subtitle2" fontWeight="bold">
            {group.label}
          </Typography>
          <Chip
            label={`${group.axes.length} axes`}
            size="small"
            variant="outlined"
            sx={{ height: 20, fontSize: '0.7rem' }}
          />
        </Box>
        <IconButton size="small">
          {expanded ? <ExpandLess /> : <ExpandMore />}
        </IconButton>
      </Box>

      {/* Axes List */}
      <Collapse in={expanded}>
        <Box sx={{ p: 1.5 }}>
          {group.axes.map(({ key, value: axisValue }, idx) => (
            <Box
              key={key}
              sx={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 2,
                py: 1,
                borderBottom: idx < group.axes.length - 1 ? '1px solid' : 'none',
                borderColor: 'divider'
              }}
            >
              {/* Axis Label */}
              <Box sx={{ minWidth: compact ? 100 : 150, pt: 0.5 }}>
                <Tooltip
                  title={getAxisDescription(key, schema) || 'No description'}
                  arrow
                  placement="left"
                >
                  <Typography
                    variant="body2"
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: compact ? '0.75rem' : '0.85rem',
                      color: 'text.secondary',
                      cursor: 'help'
                    }}
                  >
                    {formatAxisLabel(key)}
                  </Typography>
                </Tooltip>
              </Box>

              {/* PID Editor */}
              <Box sx={{ flex: 1 }}>
                <PIDRenderer
                  value={axisValue}
                  onChange={(newPID) => onChange(key, newPID)}
                  schema={schema?.properties?.[key]}
                  disabled={disabled}
                  compact={compact}
                />
              </Box>
            </Box>
          ))}
        </Box>
      </Collapse>
    </Paper>
  );
};

const AxisPIDRenderer = ({
  value,
  onChange,
  schema,
  disabled = false,
  compact = false
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandAll, setExpandAll] = useState(true);

  // Group axes by category
  const groups = useMemo(() => {
    const allAxes = value || {};
    return groupPIDAxes(allAxes);
  }, [value]);

  // Filter axes by search query
  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groups;

    const query = searchQuery.toLowerCase();
    return groups
      .map(group => ({
        ...group,
        axes: group.axes.filter(({ key }) =>
          key.toLowerCase().includes(query) ||
          formatAxisLabel(key).toLowerCase().includes(query)
        )
      }))
      .filter(group => group.axes.length > 0);
  }, [groups, searchQuery]);

  // Handle single axis change
  const handleAxisChange = useCallback((axisKey, newPID) => {
    onChange({
      ...value,
      [axisKey]: newPID
    });
  }, [value, onChange]);

  // Total axis count
  const totalAxes = useMemo(() => {
    return Object.keys(value || {}).length;
  }, [value]);

  return (
    <Box>
      {/* Header with search */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          mb: 1.5,
          flexWrap: 'wrap'
        }}
      >
        <TextField
          size="small"
          placeholder="Search axes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ minWidth: 180, flex: 1 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" color="action" />
              </InputAdornment>
            ),
            sx: { height: 32, fontSize: '0.85rem' }
          }}
        />

        <Chip
          label={`${totalAxes} total axes`}
          size="small"
          color="primary"
          variant="outlined"
        />

        <Tooltip title={expandAll ? 'Collapse all' : 'Expand all'}>
          <IconButton
            size="small"
            onClick={() => setExpandAll(!expandAll)}
          >
            {expandAll ? <ExpandLess /> : <ExpandMore />}
          </IconButton>
        </Tooltip>
      </Box>

      {/* Axis Groups */}
      {filteredGroups.length > 0 ? (
        filteredGroups.map((group, idx) => (
          <AxisGroup
            key={group.label}
            group={group}
            value={value}
            onChange={handleAxisChange}
            schema={schema}
            disabled={disabled}
            compact={compact}
            defaultExpanded={expandAll || idx === 0}
          />
        ))
      ) : (
        <Paper
          variant="outlined"
          sx={{ p: 2, textAlign: 'center', bgcolor: 'action.hover' }}
        >
          <Typography color="text.secondary" variant="body2">
            {searchQuery
              ? `No axes matching "${searchQuery}"`
              : 'No PID axes configured'}
          </Typography>
        </Paper>
      )}
    </Box>
  );
};

export default AxisPIDRenderer;
