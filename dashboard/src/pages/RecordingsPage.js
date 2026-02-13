// dashboard/src/pages/RecordingsPage.js
/**
 * Dedicated recording management page.
 *
 * Features:
 * - Storage summary with progress bar and estimated remaining time
 * - Recordings table with metadata (name, date, size, status)
 * - Download and delete actions with confirmation dialog
 * - Inline video playback in dialog
 * - Pagination for scalability
 */

import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  IconButton,
  Tooltip,
  Button,
  Chip,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Skeleton,
  Grid,
} from '@mui/material';
import VideocamIcon from '@mui/icons-material/Videocam';
import DownloadIcon from '@mui/icons-material/Download';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StorageIcon from '@mui/icons-material/Storage';
import RefreshIcon from '@mui/icons-material/Refresh';
import SettingsIcon from '@mui/icons-material/Settings';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';

import { useRecording, useRecordingsList } from '../hooks/useRecording';
import { endpoints } from '../services/apiEndpoints';

/**
 * Format bytes into human-readable size.
 */
const formatSize = (bytes) => {
  if (!bytes || bytes <= 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

/**
 * Format seconds into human-readable duration.
 */
const formatDuration = (seconds) => {
  if (!seconds || seconds <= 0) return '--';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
};

/**
 * Parse timestamp from filename.
 * Handles both old (YYYYMMDDTHHMMSSZ) and new (YYYY-MM-DDTHH-MM-SSZ) formats.
 */
const parseTimestamp = (isoStr) => {
  if (!isoStr) return '--';
  try {
    // New format: YYYY-MM-DDTHH-MM-SSZ → YYYY-MM-DD HH:MM:SS UTC
    if (isoStr.includes('-') && isoStr.includes('T')) {
      const [datePart, timePart] = isoStr.replace('Z', '').split('T');
      const time = timePart.replace(/-/g, ':');
      return `${datePart} ${time} UTC`;
    }
    // Old format: YYYYMMDDTHHMMSSZ
    if (isoStr.length >= 15) {
      const year = isoStr.substring(0, 4);
      const month = isoStr.substring(4, 6);
      const day = isoStr.substring(6, 8);
      const hour = isoStr.substring(9, 11);
      const min = isoStr.substring(11, 13);
      const sec = isoStr.substring(13, 15);
      return `${year}-${month}-${day} ${hour}:${min}:${sec} UTC`;
    }
    return isoStr;
  } catch {
    return isoStr;
  }
};

const RecordingsPage = () => {
  const { recordingStatus, storageStatus } = useRecording(3000);
  const { recordings, loading, error, refresh, deleteRecording, getDownloadUrl } = useRecordingsList();

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [deleteDialog, setDeleteDialog] = useState({ open: false, filename: null });
  const [playDialog, setPlayDialog] = useState({ open: false, url: null, filename: null });
  const [actionError, setActionError] = useState(null);

  const isRecording = recordingStatus?.is_active === true;

  const handleDelete = async () => {
    const { filename } = deleteDialog;
    setDeleteDialog({ open: false, filename: null });
    try {
      await deleteRecording(filename);
      setActionError(null);
    } catch (err) {
      setActionError(`Failed to delete ${filename}: ${err.message}`);
    }
  };

  const handlePlay = (filename) => {
    const url = getDownloadUrl(filename);
    setPlayDialog({ open: true, url, filename });
  };

  const handleDownload = (filename) => {
    const url = getDownloadUrl(filename);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const paginatedRecordings = recordings.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
        <VideocamIcon color="primary" />
        <Typography variant="h5" fontWeight={600}>
          Recordings
        </Typography>
        {isRecording && (
          <Chip
            icon={<FiberManualRecordIcon sx={{ fontSize: 12 }} />}
            label="Recording Active"
            color="error"
            size="small"
            variant="outlined"
          />
        )}
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Refresh">
          <IconButton onClick={refresh} size="small">
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Box>

      <Grid container spacing={3}>
        {/* Storage Summary Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <StorageIcon color="primary" sx={{ fontSize: 20 }} />
                <Typography variant="subtitle2" fontWeight={600}>
                  Storage
                </Typography>
              </Box>

              {storageStatus ? (
                <>
                  <Box sx={{ mb: 1.5 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        Disk Usage
                      </Typography>
                      <Typography variant="caption" fontWeight={600}>
                        {storageStatus.used_percent?.toFixed(1) || 0}%
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={storageStatus.used_percent || 0}
                      color={
                        storageStatus.warning_level === 'critical' ? 'error' :
                        storageStatus.warning_level === 'warning' ? 'warning' : 'primary'
                      }
                      sx={{ height: 6, borderRadius: 1 }}
                    />
                  </Box>

                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">Free Space</Typography>
                    <Typography variant="caption" fontFamily="monospace" fontWeight={600}>
                      {storageStatus.free_gb?.toFixed(1) || 0} GB
                    </Typography>
                  </Box>

                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">Total</Typography>
                    <Typography variant="caption" fontFamily="monospace">
                      {storageStatus.total_gb?.toFixed(1) || 0} GB
                    </Typography>
                  </Box>

                  {storageStatus.estimated_remaining_seconds && (
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="caption" color="text.secondary">Est. Remaining</Typography>
                      <Typography variant="caption" fontFamily="monospace">
                        {formatDuration(storageStatus.estimated_remaining_seconds)}
                      </Typography>
                    </Box>
                  )}

                  {storageStatus.warning_level && storageStatus.warning_level !== 'ok' && (
                    <Alert
                      severity={storageStatus.warning_level === 'critical' ? 'error' : 'warning'}
                      sx={{ mt: 1.5, py: 0 }}
                    >
                      {storageStatus.warning_level === 'critical'
                        ? 'Critical: Very low disk space!'
                        : 'Warning: Low disk space'}
                    </Alert>
                  )}
                </>
              ) : (
                <Skeleton variant="rectangular" height={80} />
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Recording Settings Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <SettingsIcon color="primary" sx={{ fontSize: 20 }} />
                <Typography variant="subtitle2" fontWeight={600}>
                  Recording Settings
                </Typography>
              </Box>

              <FormControlLabel
                control={
                  <Switch
                    size="small"
                    checked={recordingStatus?.include_osd !== false}
                    onChange={async (e) => {
                      try {
                        await fetch(endpoints.recordingIncludeOsd(e.target.checked), { method: 'POST' });
                      } catch (err) {
                        console.error('Failed to toggle OSD recording:', err);
                      }
                    }}
                    disabled={isRecording}
                  />
                }
                label={
                  <Typography variant="body2">
                    Include OSD in recordings
                  </Typography>
                }
                sx={{ ml: 0, '& .MuiSwitch-root': { mr: 1 } }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 5.5, mt: -0.5 }}>
                Burn mavlink data, battery, GPS overlays into video
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">Codec</Typography>
                  <Typography variant="caption" fontFamily="monospace" fontWeight={600}>
                    {recordingStatus?.codec?.toUpperCase() || '--'}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">Format</Typography>
                  <Typography variant="caption" fontFamily="monospace">
                    {recordingStatus?.container?.toUpperCase() || '--'}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="caption" color="text.secondary">Output</Typography>
                  <Typography variant="caption" fontFamily="monospace" sx={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {recordingStatus?.output_dir || '--'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Recording Info Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Typography variant="subtitle2" fontWeight={600}>
                  Recorded Files
                </Typography>
                <Chip
                  label={`${recordings.length} file${recordings.length !== 1 ? 's' : ''}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: 11 }}
                />
              </Box>

              {actionError && (
                <Alert severity="error" onClose={() => setActionError(null)} sx={{ mb: 1 }}>
                  {actionError}
                </Alert>
              )}

              {error && (
                <Alert severity="error" sx={{ mb: 1 }}>
                  Failed to load recordings: {error}
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Recordings Table */}
        <Grid item xs={12}>
          <Card variant="outlined">
            {loading ? (
              <Box sx={{ p: 3 }}>
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} variant="text" height={40} sx={{ mb: 0.5 }} />
                ))}
              </Box>
            ) : recordings.length === 0 ? (
              <Box sx={{ p: 4, textAlign: 'center' }}>
                <VideocamIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                <Typography color="text.secondary">
                  No recordings yet. Press R or use the dashboard controls to start recording.
                </Typography>
              </Box>
            ) : (
              <>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Filename</TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Date (UTC)</TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: 12 }} align="right">Size</TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Status</TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: 12 }} align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {paginatedRecordings.map((rec) => (
                        <TableRow key={rec.filename} hover>
                          <TableCell>
                            <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                              {rec.filename}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ fontSize: 12 }}>
                              {parseTimestamp(rec.created_at_iso)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                              {formatSize(rec.size_bytes)}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={rec.status || 'completed'}
                              size="small"
                              color={
                                rec.status === 'recovered' ? 'warning' :
                                rec.status === 'error' ? 'error' : 'success'
                              }
                              variant="outlined"
                              sx={{ fontSize: 10, height: 20 }}
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5 }}>
                              <Tooltip title="Play">
                                <IconButton size="small" onClick={() => handlePlay(rec.filename)}>
                                  <PlayArrowIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Download">
                                <IconButton size="small" onClick={() => handleDownload(rec.filename)}>
                                  <DownloadIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Delete">
                                <IconButton
                                  size="small"
                                  color="error"
                                  onClick={() => setDeleteDialog({ open: true, filename: rec.filename })}
                                >
                                  <DeleteIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </Tooltip>
                            </Box>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>

                <TablePagination
                  component="div"
                  count={recordings.length}
                  page={page}
                  onPageChange={(_, newPage) => setPage(newPage)}
                  rowsPerPage={rowsPerPage}
                  onRowsPerPageChange={(e) => {
                    setRowsPerPage(parseInt(e.target.value, 10));
                    setPage(0);
                  }}
                  rowsPerPageOptions={[10, 25, 50]}
                  sx={{ borderTop: 1, borderColor: 'divider' }}
                />
              </>
            )}
          </Card>
        </Grid>
      </Grid>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, filename: null })}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Delete Recording</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{deleteDialog.filename}</strong>?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, filename: null })}>
            Cancel
          </Button>
          <Button onClick={handleDelete} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Video Playback Dialog */}
      <Dialog
        open={playDialog.open}
        onClose={() => setPlayDialog({ open: false, url: null, filename: null })}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{playDialog.filename}</DialogTitle>
        <DialogContent>
          {playDialog.url && (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <video
                src={playDialog.url}
                controls
                autoPlay
                style={{ maxWidth: '100%', maxHeight: '60vh' }}
                onError={(e) => {
                  // Hide the broken video element on error
                  e.target.style.display = 'none';
                }}
              >
                <source src={playDialog.url} type="video/mp4" />
              </video>
              <Alert severity="info" sx={{ width: '100%' }}>
                <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                  If playback doesn't work in the browser:
                </Typography>
                <Typography variant="body2">
                  Download the file and open it in VLC, Windows Media Player, or any desktop video player.
                  The default mp4v codec is universally compatible with desktop players but may not
                  play inline in all browsers.
                </Typography>
              </Alert>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => handleDownload(playDialog.filename)}
            startIcon={<DownloadIcon />}
            variant="contained"
            color="primary"
          >
            Download
          </Button>
          <Button onClick={() => setPlayDialog({ open: false, url: null, filename: null })}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RecordingsPage;
