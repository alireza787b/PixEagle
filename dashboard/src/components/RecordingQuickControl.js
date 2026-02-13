// dashboard/src/components/RecordingQuickControl.js
/**
 * Compact recording control card for the dashboard streaming settings row.
 *
 * Features:
 * - Start/Pause/Stop recording buttons
 * - Animated recording indicator (pulsing red dot)
 * - Elapsed time display
 * - File size display
 * - Storage warning alert
 */

import React, { useState } from 'react';
import {
  Box,
  Button,
  Typography,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
  FormControlLabel,
  Switch,
} from '@mui/material';
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import StopIcon from '@mui/icons-material/Stop';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useRecording } from '../hooks/useRecording';
import { endpoints } from '../services/apiEndpoints';

/**
 * Format seconds into HH:MM:SS display.
 */
const formatDuration = (seconds) => {
  if (!seconds || seconds < 0) return '00:00:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
};

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

const RecordingQuickControl = () => {
  const {
    recordingStatus,
    storageStatus,
    loading,
    error,
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
  } = useRecording(1000); // Poll every 1s for responsive timer

  const [actionLoading, setActionLoading] = useState(false);

  const isRecording = recordingStatus?.is_recording === true;
  const isPaused = recordingStatus?.state === 'paused';
  const isActive = recordingStatus?.is_active === true;
  const storageWarning = storageStatus?.warning_level;

  const handleStart = async () => {
    setActionLoading(true);
    try {
      await startRecording();
    } catch (err) {
      console.error('Failed to start recording:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePause = async () => {
    setActionLoading(true);
    try {
      if (isPaused) {
        await resumeRecording();
      } else {
        await pauseRecording();
      }
    } catch (err) {
      console.error('Failed to pause/resume recording:', err);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      await stopRecording();
    } catch (err) {
      console.error('Failed to stop recording:', err);
    } finally {
      setActionLoading(false);
    }
  };

  if (loading && !recordingStatus) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', py: 1 }}>
        <CircularProgress size={16} />
      </Box>
    );
  }

  return (
    <Box>
      {/* Status + Controls Row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        {/* Recording indicator */}
        <FiberManualRecordIcon
          sx={{
            fontSize: 14,
            color: isRecording ? 'error.main' : isPaused ? 'warning.main' : 'text.disabled',
            ...(isRecording && {
              animation: 'recording-pulse 1.5s ease-in-out infinite',
              '@keyframes recording-pulse': {
                '0%, 100%': { opacity: 1 },
                '50%': { opacity: 0.3 },
              },
            }),
          }}
        />

        <Chip
          label={isRecording ? 'REC' : isPaused ? 'PAUSED' : 'OFF'}
          size="small"
          color={isRecording ? 'error' : isPaused ? 'warning' : 'default'}
          variant={isActive ? 'filled' : 'outlined'}
          sx={{ fontSize: 10, height: 20, fontWeight: 700 }}
        />

        {/* Elapsed time (when active) */}
        {isActive && (
          <Typography
            variant="caption"
            sx={{ fontFamily: 'monospace', fontWeight: 600, fontSize: 11 }}
          >
            {formatDuration(recordingStatus?.elapsed_seconds)}
          </Typography>
        )}

        {/* File size (when active) */}
        {isActive && recordingStatus?.file_size_bytes > 0 && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ fontSize: 10 }}
          >
            {formatSize(recordingStatus.file_size_bytes)}
          </Typography>
        )}
      </Box>

      {/* Action Buttons */}
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {!isActive ? (
          /* Start button */
          <Button
            size="small"
            variant="contained"
            color="error"
            onClick={handleStart}
            disabled={actionLoading}
            startIcon={<FiberManualRecordIcon sx={{ fontSize: '14px !important' }} />}
            sx={{
              flex: 1,
              fontSize: 11,
              py: 0.5,
              textTransform: 'none',
              minHeight: 28,
            }}
          >
            Record
          </Button>
        ) : (
          /* Pause + Stop buttons */
          <>
            <Tooltip title={isPaused ? 'Resume' : 'Pause'}>
              <IconButton
                size="small"
                onClick={handlePause}
                disabled={actionLoading}
                color="warning"
                sx={{ border: 1, borderColor: 'divider', borderRadius: 1, width: 28, height: 28 }}
              >
                {isPaused ? <PlayArrowIcon sx={{ fontSize: 16 }} /> : <PauseIcon sx={{ fontSize: 16 }} />}
              </IconButton>
            </Tooltip>
            <Button
              size="small"
              variant="contained"
              color="error"
              onClick={handleStop}
              disabled={actionLoading}
              startIcon={<StopIcon sx={{ fontSize: '14px !important' }} />}
              sx={{
                flex: 1,
                fontSize: 11,
                py: 0.5,
                textTransform: 'none',
                minHeight: 28,
              }}
            >
              Stop
            </Button>
          </>
        )}
      </Box>

      {/* OSD Toggle */}
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
            disabled={isActive}
          />
        }
        label={
          <Typography variant="caption" sx={{ fontSize: 11 }}>
            Include OSD
          </Typography>
        }
        sx={{ mt: 0.5, ml: 0, '& .MuiSwitch-root': { mr: 0.5 } }}
      />

      {/* Storage Warning */}
      {storageWarning && storageWarning !== 'ok' && (
        <Alert
          severity={storageWarning === 'critical' ? 'error' : 'warning'}
          sx={{ mt: 1, py: 0, fontSize: 10, '& .MuiAlert-icon': { fontSize: 16 } }}
        >
          {storageWarning === 'critical'
            ? `Critical: ${storageStatus?.free_mb?.toFixed(0) || 0} MB free`
            : `Low storage: ${storageStatus?.free_gb?.toFixed(1) || 0} GB free`}
        </Alert>
      )}

      {/* Error display */}
      {error && !isActive && (
        <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block', fontSize: 10 }}>
          Connection error
        </Typography>
      )}
    </Box>
  );
};

export default RecordingQuickControl;
