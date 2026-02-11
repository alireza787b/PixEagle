// dashboard/src/components/StreamingStatusIndicator.js
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Chip, Collapse, Typography, LinearProgress, Tooltip
} from '@mui/material';
import {
  FiberManualRecord, ExpandMore, ExpandLess, Speed, Memory
} from '@mui/icons-material';
import { alpha } from '@mui/material/styles';
import axios from 'axios';
import { streamingStatus as streamingStatusEndpoint } from '../services/apiEndpoints';

const StreamingStatusIndicator = () => {
  const [status, setStatus] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [fetchError, setFetchError] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await axios.get(streamingStatusEndpoint);
      setStatus(response.data);
      setFetchError(false);
    } catch (err) {
      setFetchError(true);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (!status && !fetchError) return null;

  // Determine health color based on quality level and client count
  const getHealthColor = () => {
    if (fetchError || !status) return 'error';
    const engine = status.quality_engine || {};
    const clients = engine.clients || {};
    const clientIds = Object.keys(clients);
    if (clientIds.length === 0) return 'default';

    // Average quality across clients
    const avgQuality = clientIds.reduce((sum, id) => sum + (clients[id].quality || 60), 0) / clientIds.length;
    if (avgQuality >= 60) return 'success';
    if (avgQuality >= 35) return 'warning';
    return 'error';
  };

  // Determine dot color
  const getDotColor = () => {
    const health = getHealthColor();
    if (health === 'success') return '#4caf50';
    if (health === 'warning') return '#ff9800';
    if (health === 'error') return '#f44336';
    return '#9e9e9e';
  };

  const totalClients = status
    ? (status.http_clients || 0) + (status.websocket_clients || 0) + (status.webrtc_clients || 0)
    : 0;

  const methodLabel = status ? (status.active_method || 'none').toUpperCase() : '?';

  // Get representative quality (first client or config default)
  const getRepQuality = () => {
    if (!status || !status.quality_engine) return null;
    const clients = status.quality_engine.clients || {};
    const ids = Object.keys(clients);
    if (ids.length === 0) return null;
    return clients[ids[0]].quality;
  };

  const repQuality = getRepQuality();

  const chipLabel = repQuality !== null
    ? `${methodLabel} | Q:${repQuality}`
    : `${methodLabel} | ${totalClients} clients`;

  return (
    <Box sx={{ mt: 1 }}>
      {/* Compact indicator chip */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Chip
          icon={<FiberManualRecord sx={{ fontSize: 12, color: getDotColor() }} />}
          label={chipLabel}
          size="small"
          variant="outlined"
          onClick={() => setExpanded(!expanded)}
          deleteIcon={expanded ? <ExpandLess /> : <ExpandMore />}
          onDelete={() => setExpanded(!expanded)}
          sx={{ cursor: 'pointer', fontFamily: 'monospace', fontSize: '0.75rem' }}
        />
      </Box>

      {/* Expanded detail panel */}
      <Collapse in={expanded}>
        <Box
          sx={{
            mt: 1,
            p: 1.5,
            bgcolor: (theme) => alpha(theme.palette.background.paper, theme.palette.mode === 'dark' ? 0.72 : 0.9),
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider',
          }}
        >
          {fetchError ? (
            <Typography variant="caption" color="error">
              Unable to fetch streaming status
            </Typography>
          ) : status && (
            <>
              {/* Connection counts */}
              <Box sx={{ display: 'flex', gap: 2, mb: 1 }}>
                <Typography variant="caption" color="textSecondary">
                  HTTP: {status.http_clients || 0}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  WS: {status.websocket_clients || 0}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  WebRTC: {status.webrtc_clients || 0}
                </Typography>
              </Box>

              {/* CPU load */}
              {status.quality_engine && status.quality_engine.cpu_load !== undefined && (
                <Box sx={{ mb: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                    <Memory sx={{ fontSize: 14 }} />
                    <Typography variant="caption">
                      CPU: {status.quality_engine.cpu_load.toFixed(1)}%
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(status.quality_engine.cpu_load, 100)}
                    color={status.quality_engine.cpu_load > 80 ? 'error' : status.quality_engine.cpu_load > 60 ? 'warning' : 'success'}
                    sx={{ height: 3, borderRadius: 1 }}
                  />
                </Box>
              )}

              {/* Per-client details */}
              {status.quality_engine && status.quality_engine.clients && Object.keys(status.quality_engine.clients).length > 0 && (
                <Box>
                  <Typography variant="caption" fontWeight="bold" sx={{ mb: 0.5, display: 'block' }}>
                    Client Quality:
                  </Typography>
                  {Object.entries(status.quality_engine.clients).map(([clientId, client]) => (
                    <Box key={clientId} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.25 }}>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', fontSize: '0.7rem' }}>
                        {clientId.length > 12 ? `...${clientId.slice(-10)}` : clientId}
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Tooltip title="JPEG Quality">
                          <Chip label={`Q:${client.quality}`} size="small" sx={{ height: 18, fontSize: '0.65rem' }} />
                        </Tooltip>
                        {client.bandwidth_kbps !== undefined && (
                          <Tooltip title="Bandwidth">
                            <Chip
                              icon={<Speed sx={{ fontSize: 10 }} />}
                              label={`${client.bandwidth_kbps.toFixed(0)}kb/s`}
                              size="small"
                              sx={{ height: 18, fontSize: '0.65rem' }}
                            />
                          </Tooltip>
                        )}
                        {client.encoding_time_ms !== undefined && (
                          <Tooltip title="Encoding Time">
                            <Chip
                              label={`${client.encoding_time_ms.toFixed(1)}ms`}
                              size="small"
                              variant="outlined"
                              sx={{ height: 18, fontSize: '0.65rem' }}
                            />
                          </Tooltip>
                        )}
                      </Box>
                    </Box>
                  ))}
                </Box>
              )}

              {/* Adaptive quality status */}
              <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Typography variant="caption" color="textSecondary">
                  Adaptive: {status.adaptive_quality_enabled ? 'ON' : 'OFF'}
                </Typography>
                {status.config && (
                  <Typography variant="caption" color="textSecondary">
                    | {status.config.stream_width}x{status.config.stream_height} @ {status.config.stream_fps}fps
                  </Typography>
                )}
              </Box>
            </>
          )}
        </Box>
      </Collapse>
    </Box>
  );
};

export default StreamingStatusIndicator;
