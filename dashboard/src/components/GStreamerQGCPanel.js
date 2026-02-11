// dashboard/src/components/GStreamerQGCPanel.js
// Compact panel for controlling GStreamer H.264/RTP output to QGC/ground stations.
// This is independent of dashboard streaming (HTTP/WebSocket/WebRTC).
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Typography, Chip, Switch, Collapse, IconButton, Tooltip, Alert
} from '@mui/material';
import {
  FlightTakeoff, ExpandMore, ExpandLess, Info, CheckCircle, Error as ErrorIcon
} from '@mui/icons-material';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

const GStreamerQGCPanel = () => {
  const [status, setStatus] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [toggleError, setToggleError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(endpoints.gstreamerStatus);
      setStatus(res.data);
    } catch {
      // API not available yet — leave status null
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleToggle = async () => {
    setToggling(true);
    setToggleError(null);
    try {
      const res = await axios.post(endpoints.toggleGstreamer);
      if (res.data.status === 'error') {
        setToggleError(res.data.message);
      }
      // Refresh status immediately
      await fetchStatus();
    } catch (err) {
      setToggleError(
        err.response?.data?.message || err.response?.data?.detail || 'Failed to toggle GStreamer output'
      );
    } finally {
      setToggling(false);
    }
  };

  if (!status) return null;

  const isEnabled = status.enabled;
  const encoderLabel = isEnabled
    ? `${status.encoder}${status.hardware_accelerated ? ' (GPU)' : ' (SW)'}`
    : 'Off';

  return (
    <Box sx={{ mt: 1 }}>
      {/* Compact header row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Tooltip title="H.264/RTP/UDP output for QGroundControl and other ground stations. Independent of dashboard streaming.">
          <Chip
            icon={<FlightTakeoff sx={{ fontSize: 16 }} />}
            label={`QGC Stream: ${isEnabled ? 'ON' : 'OFF'}`}
            size="small"
            color={isEnabled ? 'success' : 'default'}
            variant={isEnabled ? 'filled' : 'outlined'}
            sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
          />
        </Tooltip>

        <Switch
          checked={isEnabled}
          onChange={handleToggle}
          disabled={toggling}
          size="small"
          color="success"
        />

        {isEnabled && (
          <Chip
            label={encoderLabel}
            size="small"
            variant="outlined"
            sx={{ fontSize: '0.7rem', height: 22 }}
          />
        )}

        <IconButton
          size="small"
          onClick={() => setExpanded(!expanded)}
          sx={{ p: 0.5, ml: 'auto' }}
        >
          {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </IconButton>
      </Box>

      {/* Error feedback */}
      {toggleError && (
        <Alert severity="error" sx={{ mt: 0.5, py: 0, fontSize: '0.75rem' }} onClose={() => setToggleError(null)}>
          {toggleError}
        </Alert>
      )}

      {/* Expanded detail panel */}
      <Collapse in={expanded}>
        <Box sx={{
          mt: 1, p: 1.5, bgcolor: 'grey.50', borderRadius: 1,
          border: '1px solid', borderColor: 'grey.200'
        }}>
          {/* Status row */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            {isEnabled
              ? <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />
              : <ErrorIcon sx={{ fontSize: 16, color: 'grey.400' }} />
            }
            <Typography variant="caption" fontWeight="bold">
              {isEnabled ? 'Streaming to QGC' : 'QGC Output Disabled'}
            </Typography>
          </Box>

          {/* Configuration details */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            <DetailRow label="Destination" value={`${status.host}:${status.port}`} />
            <DetailRow label="Resolution" value={status.resolution} />
            <DetailRow label="Framerate" value={`${status.framerate} fps`} />
            <DetailRow label="Bitrate" value={`${status.bitrate_kbps} kbps`} />
            {isEnabled && (
              <DetailRow
                label="Encoder"
                value={`${status.encoder} ${status.hardware_accelerated ? '(hardware)' : '(software)'}`}
              />
            )}
          </Box>

          {/* QGC setup hint */}
          <Box sx={{
            mt: 1.5, p: 1, bgcolor: 'info.50', borderRadius: 1,
            border: '1px solid', borderColor: 'info.100',
            display: 'flex', gap: 0.5, alignItems: 'flex-start'
          }}>
            <Info sx={{ fontSize: 14, color: 'info.main', mt: 0.25 }} />
            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.4 }}>
              <strong>QGC Setup:</strong> Application Settings &rarr; Video &rarr;
              UDP Video Stream, port {status.port}.
              {!isEnabled && ' Enable the toggle above to start streaming.'}
            </Typography>
          </Box>
        </Box>
      </Collapse>
    </Box>
  );
};

const DetailRow = ({ label, value }) => (
  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
    <Typography variant="caption" color="text.secondary">{label}:</Typography>
    <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}>
      {value}
    </Typography>
  </Box>
);

export default GStreamerQGCPanel;
