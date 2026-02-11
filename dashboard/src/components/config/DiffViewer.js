// dashboard/src/components/config/DiffViewer.js
import React, { useState, useMemo } from 'react';
import {
  Box, Typography, Paper, Chip, Checkbox,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, TextField, InputAdornment,
} from '@mui/material';
import {
  Add, Remove, Edit, ExpandMore, ExpandLess, Search,
  CheckBox, CheckBoxOutlineBlank, Undo
} from '@mui/icons-material';

/**
 * DiffViewer - Visual diff comparison for configuration changes
 *
 * Features:
 * - Side-by-side value comparison
 * - Color-coded change types (added, removed, changed)
 * - Collapsible sections
 * - Search/filter
 * - Selective checkbox for import
 */
const DiffViewer = ({
  differences = [],
  selectable = false,
  selectedChanges = [],
  onSelectionChange,
  showFilter = true,
  compact = false,
  onRevert = null  // v5.4.2: Callback for selective revert (section, parameter)
}) => {
  const [expandedSections, setExpandedSections] = useState({});
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('all'); // all, added, removed, changed

  // Group differences by section
  const groupedDiffs = useMemo(() => {
    const grouped = {};
    differences.forEach(diff => {
      if (!grouped[diff.section]) {
        grouped[diff.section] = [];
      }
      grouped[diff.section].push(diff);
    });
    return grouped;
  }, [differences]);

  // Filter differences
  const filteredDiffs = useMemo(() => {
    if (!filter && typeFilter === 'all') {
      return groupedDiffs;
    }

    const result = {};
    Object.entries(groupedDiffs).forEach(([section, diffs]) => {
      const filtered = diffs.filter(diff => {
        // Type filter
        if (typeFilter !== 'all' && diff.change_type !== typeFilter) {
          return false;
        }
        // Text filter
        if (filter) {
          const searchLower = filter.toLowerCase();
          return (
            section.toLowerCase().includes(searchLower) ||
            diff.parameter.toLowerCase().includes(searchLower) ||
            String(diff.old_value).toLowerCase().includes(searchLower) ||
            String(diff.new_value).toLowerCase().includes(searchLower)
          );
        }
        return true;
      });
      if (filtered.length > 0) {
        result[section] = filtered;
      }
    });
    return result;
  }, [groupedDiffs, filter, typeFilter]);

  // Calculate totals
  const totals = useMemo(() => {
    let added = 0, removed = 0, changed = 0;
    differences.forEach(diff => {
      if (diff.change_type === 'added') added++;
      else if (diff.change_type === 'removed') removed++;
      else changed++;
    });
    return { added, removed, changed, total: differences.length };
  }, [differences]);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const isSelected = (diff) => {
    return selectedChanges.some(
      s => s.section === diff.section && s.parameter === diff.parameter
    );
  };

  const toggleSelection = (diff) => {
    if (!onSelectionChange) return;

    if (isSelected(diff)) {
      onSelectionChange(
        selectedChanges.filter(
          s => !(s.section === diff.section && s.parameter === diff.parameter)
        )
      );
    } else {
      onSelectionChange([...selectedChanges, diff]);
    }
  };

  const toggleSectionSelection = (section, diffs) => {
    if (!onSelectionChange) return;

    const allSelected = diffs.every(d => isSelected(d));
    if (allSelected) {
      // Deselect all in section
      onSelectionChange(
        selectedChanges.filter(s => s.section !== section)
      );
    } else {
      // Select all in section
      const existing = selectedChanges.filter(s => s.section !== section);
      onSelectionChange([...existing, ...diffs]);
    }
  };

  const selectAll = () => {
    if (!onSelectionChange) return;
    onSelectionChange([...differences]);
  };

  const selectNone = () => {
    if (!onSelectionChange) return;
    onSelectionChange([]);
  };

  const getChangeIcon = (changeType) => {
    switch (changeType) {
      case 'added':
        return <Add fontSize="small" sx={{ color: 'success.main' }} />;
      case 'removed':
        return <Remove fontSize="small" sx={{ color: 'error.main' }} />;
      default:
        return <Edit fontSize="small" sx={{ color: 'warning.main' }} />;
    }
  };

  const formatValue = (value) => {
    if (value === null || value === undefined) {
      return <Typography component="span" color="text.disabled">null</Typography>;
    }
    if (typeof value === 'object') {
      return JSON.stringify(value).slice(0, 50);
    }
    if (typeof value === 'boolean') {
      return value ? 'true' : 'false';
    }
    return String(value).slice(0, 50);
  };

  if (differences.length === 0) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <Typography color="text.secondary">
          No differences found
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Summary chips */}
      <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap', alignItems: 'center' }}>
        <Chip
          label={`${totals.total} total`}
          size="small"
          variant="outlined"
          onClick={() => setTypeFilter('all')}
          color={typeFilter === 'all' ? 'primary' : 'default'}
        />
        {totals.added > 0 && (
          <Chip
            icon={<Add fontSize="small" />}
            label={`${totals.added} added`}
            size="small"
            color={typeFilter === 'added' ? 'success' : 'default'}
            variant={typeFilter === 'added' ? 'filled' : 'outlined'}
            onClick={() => setTypeFilter(typeFilter === 'added' ? 'all' : 'added')}
          />
        )}
        {totals.removed > 0 && (
          <Chip
            icon={<Remove fontSize="small" />}
            label={`${totals.removed} removed`}
            size="small"
            color={typeFilter === 'removed' ? 'error' : 'default'}
            variant={typeFilter === 'removed' ? 'filled' : 'outlined'}
            onClick={() => setTypeFilter(typeFilter === 'removed' ? 'all' : 'removed')}
          />
        )}
        {totals.changed > 0 && (
          <Chip
            icon={<Edit fontSize="small" />}
            label={`${totals.changed} changed`}
            size="small"
            color={typeFilter === 'changed' ? 'warning' : 'default'}
            variant={typeFilter === 'changed' ? 'filled' : 'outlined'}
            onClick={() => setTypeFilter(typeFilter === 'changed' ? 'all' : 'changed')}
          />
        )}

        {selectable && (
          <>
            <Box sx={{ flexGrow: 1 }} />
            <Chip
              icon={<CheckBox fontSize="small" />}
              label="Select All"
              size="small"
              variant="outlined"
              onClick={selectAll}
              sx={{ cursor: 'pointer' }}
            />
            <Chip
              icon={<CheckBoxOutlineBlank fontSize="small" />}
              label="Select None"
              size="small"
              variant="outlined"
              onClick={selectNone}
              sx={{ cursor: 'pointer' }}
            />
          </>
        )}
      </Box>

      {/* Search filter */}
      {showFilter && (
        <TextField
          fullWidth
          size="small"
          placeholder="Filter changes..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ mb: 2 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" />
              </InputAdornment>
            )
          }}
        />
      )}

      {/* Diff table */}
      <TableContainer
        component={Paper}
        variant="outlined"
        sx={{
          maxWidth: '100%',
          overflowX: 'auto',
          overflowY: 'hidden'
        }}
      >
        <Table
          size="small"
          sx={{
            tableLayout: 'fixed',
            width: '100%'
          }}
        >
          <TableHead>
            <TableRow>
              {selectable && <TableCell padding="checkbox" sx={{ width: 42 }} />}
              <TableCell sx={{ fontWeight: 'bold', width: 40, whiteSpace: 'nowrap' }}>Type</TableCell>
              <TableCell sx={{ fontWeight: 'bold', width: compact ? (onRevert ? '60%' : '70%') : (onRevert ? '28%' : '32%') }}>Parameter</TableCell>
              {!compact && (
                <>
                  <TableCell sx={{ fontWeight: 'bold', width: onRevert ? '28%' : '32%' }}>Current Value</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', width: onRevert ? '28%' : '32%' }}>Default Value</TableCell>
                </>
              )}
              {onRevert && <TableCell sx={{ fontWeight: 'bold', width: 50, whiteSpace: 'nowrap' }}>Action</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {Object.entries(filteredDiffs).map(([section, diffs]) => {
              const isExpanded = expandedSections[section] !== false; // Default expanded
              const sectionSelected = diffs.every(d => isSelected(d));
              const sectionPartial = !sectionSelected && diffs.some(d => isSelected(d));

              return (
                <React.Fragment key={section}>
                  {/* Section header */}
                  <TableRow
                    sx={{
                      bgcolor: 'action.hover',
                      cursor: 'pointer',
                      '&:hover': { bgcolor: 'action.selected' }
                    }}
                    onClick={() => toggleSection(section)}
                  >
                    {selectable && (
                      <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={sectionSelected}
                          indeterminate={sectionPartial}
                          onChange={() => toggleSectionSelection(section, diffs)}
                          size="small"
                        />
                      </TableCell>
                    )}
                    <TableCell colSpan={compact ? (onRevert ? 3 : 2) : (onRevert ? 5 : 4)}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <IconButton size="small">
                          {isExpanded ? <ExpandLess /> : <ExpandMore />}
                        </IconButton>
                        <Typography variant="subtitle2" fontWeight="bold">
                          {section}
                        </Typography>
                        <Chip
                          label={`${diffs.length} changes`}
                          size="small"
                          variant="outlined"
                        />
                      </Box>
                    </TableCell>
                  </TableRow>

                  {/* Section parameters */}
                  {isExpanded && diffs.map((diff) => (
                    <TableRow
                      key={`${section}.${diff.parameter}`}
                      sx={{
                        bgcolor: isSelected(diff) ? 'action.selected' : undefined,
                        '&:hover': { bgcolor: 'action.hover' }
                      }}
                    >
                      {selectable && (
                        <TableCell padding="checkbox">
                          <Checkbox
                            checked={isSelected(diff)}
                            onChange={() => toggleSelection(diff)}
                            size="small"
                          />
                        </TableCell>
                      )}
                      <TableCell>
                        <Tooltip title={diff.change_type}>
                          {getChangeIcon(diff.change_type)}
                        </Tooltip>
                      </TableCell>
                      <TableCell sx={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        <Tooltip title={diff.parameter} placement="top-start">
                          <Typography
                            variant="body2"
                            sx={{
                              fontFamily: 'monospace',
                              pl: 2,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap'
                            }}
                          >
                            {diff.parameter}
                          </Typography>
                        </Tooltip>
                      </TableCell>
                      {!compact && (
                        <>
                          <TableCell sx={{ overflow: 'hidden' }}>
                            <Tooltip title={diff.change_type === 'added' ? '-' : String(formatValue(diff.new_value))} placement="top">
                              <Typography
                                variant="body2"
                                noWrap
                                sx={{
                                  fontFamily: 'monospace',
                                  color: diff.change_type === 'added' ? 'text.disabled' : 'error.main',
                                  textDecoration: diff.change_type !== 'added' ? 'line-through' : 'none',
                                  opacity: diff.change_type === 'added' ? 0.5 : 1,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis'
                                }}
                              >
                                {diff.change_type === 'added' ? '-' : formatValue(diff.new_value)}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                          <TableCell sx={{ overflow: 'hidden' }}>
                            <Tooltip title={diff.change_type === 'removed' ? '-' : String(formatValue(diff.old_value))} placement="top">
                              <Typography
                                variant="body2"
                                noWrap
                                sx={{
                                  fontFamily: 'monospace',
                                  color: diff.change_type === 'removed' ? 'text.disabled' : 'success.main',
                                  opacity: diff.change_type === 'removed' ? 0.5 : 1,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis'
                                }}
                              >
                                {diff.change_type === 'removed' ? '-' : formatValue(diff.old_value)}
                              </Typography>
                            </Tooltip>
                          </TableCell>
                        </>
                      )}
                      {onRevert && (
                        <TableCell>
                          <Tooltip title="Revert to default">
                            <IconButton
                              size="small"
                              onClick={() => onRevert(diff.section, diff.parameter)}
                              color="primary"
                              disabled={diff.change_type === 'added'}
                            >
                              <Undo fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Selection summary */}
      {selectable && selectedChanges.length > 0 && (
        <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
          <Chip
            label={`${selectedChanges.length} of ${differences.length} selected`}
            color="primary"
            variant="outlined"
          />
        </Box>
      )}
    </Box>
  );
};

export default DiffViewer;
