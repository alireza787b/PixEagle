import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Typography,
  Box,
  Chip,
  IconButton,
  TablePagination,
  TextField,
  MenuItem,
  CircularProgress,
  Tooltip
} from '@mui/material';
import {
  Close as CloseIcon,
  Refresh as RefreshIcon,
  Edit as EditIcon,
  Upload as UploadIcon,
  Restore as RestoreIcon,
  Undo as UndoIcon
} from '@mui/icons-material';
import { endpoints } from '../../services/apiEndpoints';

const ACTION_ICONS = {
  update: <EditIcon fontSize="small" />,
  import: <UploadIcon fontSize="small" />,
  restore: <RestoreIcon fontSize="small" />,
  revert: <UndoIcon fontSize="small" />
};

const ACTION_COLORS = {
  update: 'primary',
  import: 'secondary',
  restore: 'warning',
  revert: 'info'
};

function formatTimestamp(isoString) {
  if (!isoString) return '-';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
  return date.toLocaleDateString();
}

function formatValue(value) {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function truncateValue(value, maxLen = 30) {
  const str = formatValue(value);
  if (str.length > maxLen) {
    return str.substring(0, maxLen) + '...';
  }
  return str;
}

export default function AuditLogDialog({ open, onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [sectionFilter, setSectionFilter] = useState('');
  const [actionFilter, setActionFilter] = useState('');
  const [sections, setSections] = useState([]);

  const fetchAuditLog = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: rowsPerPage,
        offset: page * rowsPerPage
      });
      if (sectionFilter) params.append('section', sectionFilter);
      if (actionFilter) params.append('action', actionFilter);

      const response = await fetch(`${endpoints.configAudit}?${params}`);
      const data = await response.json();

      if (data.success) {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Error fetching audit log:', error);
    } finally {
      setLoading(false);
    }
  }, [page, rowsPerPage, sectionFilter, actionFilter]);

  const fetchSections = useCallback(async () => {
    try {
      const response = await fetch(endpoints.configSections);
      const data = await response.json();
      if (data.success && data.sections) {
        setSections(data.sections.map(s => s.name));
      }
    } catch (error) {
      console.error('Error fetching sections:', error);
    }
  }, []);

  useEffect(() => {
    if (open) {
      fetchAuditLog();
      fetchSections();
    }
  }, [open, fetchAuditLog, fetchSections]);

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      PaperProps={{ sx: { minHeight: '70vh' } }}
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6">Configuration Audit Log</Typography>
          <Box>
            <IconButton onClick={fetchAuditLog} disabled={loading}>
              <RefreshIcon />
            </IconButton>
            <IconButton onClick={onClose}>
              <CloseIcon />
            </IconButton>
          </Box>
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        <Box sx={{ mb: 2, display: 'flex', gap: 2 }}>
          <TextField
            select
            label="Section"
            value={sectionFilter}
            onChange={(e) => { setSectionFilter(e.target.value); setPage(0); }}
            size="small"
            sx={{ minWidth: 150 }}
          >
            <MenuItem value="">All Sections</MenuItem>
            {sections.map((s) => (
              <MenuItem key={s} value={s}>{s}</MenuItem>
            ))}
          </TextField>
          <TextField
            select
            label="Action"
            value={actionFilter}
            onChange={(e) => { setActionFilter(e.target.value); setPage(0); }}
            size="small"
            sx={{ minWidth: 120 }}
          >
            <MenuItem value="">All Actions</MenuItem>
            <MenuItem value="update">Update</MenuItem>
            <MenuItem value="import">Import</MenuItem>
            <MenuItem value="restore">Restore</MenuItem>
            <MenuItem value="revert">Revert</MenuItem>
          </TextField>
          <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto', alignSelf: 'center' }}>
            {total} total entries
          </Typography>
        </Box>

        {loading ? (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        ) : entries.length === 0 ? (
          <Box display="flex" justifyContent="center" py={4}>
            <Typography color="text.secondary">No audit entries found</Typography>
          </Box>
        ) : (
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Time</TableCell>
                  <TableCell>Action</TableCell>
                  <TableCell>Section</TableCell>
                  <TableCell>Parameter</TableCell>
                  <TableCell>Old Value</TableCell>
                  <TableCell>New Value</TableCell>
                  <TableCell>Source</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entries.map((entry, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell>
                      <Tooltip title={entry.timestamp}>
                        <Typography variant="body2" noWrap>
                          {formatTimestamp(entry.timestamp)}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Chip
                        icon={ACTION_ICONS[entry.action]}
                        label={entry.action}
                        size="small"
                        color={ACTION_COLORS[entry.action] || 'default'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {entry.section}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace">
                        {entry.parameter || '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={formatValue(entry.old_value)}>
                        <Typography variant="body2" sx={{ color: 'error.main' }}>
                          {truncateValue(entry.old_value)}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Tooltip title={formatValue(entry.new_value)}>
                        <Typography variant="body2" sx={{ color: 'success.main' }}>
                          {truncateValue(entry.new_value)}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {entry.source}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={handleChangePage}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          rowsPerPageOptions={[10, 25, 50, 100]}
        />
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
