// dashboard/src/components/StreamingStats.js
import React, { useState, useEffect, useRef } from 'react';
import {
  Card, CardContent, Typography, Box, LinearProgress, Chip, Collapse, IconButton
} from '@mui/material';
import { Speed, CloudQueue, Warning, ExpandMore, ExpandLess } from '@mui/icons-material';
import { useStreamingMediaHealth } from '../hooks/useStatuses';

const StreamingStats = () => {
  const [showLifetime, setShowLifetime] = useState(false);
  const { streamingStatus: statusData, loading } = useStreamingMediaHealth(3000);
  const stats = statusData?.frames || null;

  // Previous poll values for delta computation
  const prevStats = useRef(null);
  const prevTime = useRef(null);

  // Windowed (delta-computed) metrics
  const [windowedMetrics, setWindowedMetrics] = useState({
    recentFps: 0,
    recentDropRate: 0,
    recentBandwidthKbps: 0,
  });

  useEffect(() => {
    if (!stats) {
      return;
    }

    const now = Date.now();
    if (prevStats.current && prevTime.current) {
      const dt = (now - prevTime.current) / 1000; // seconds
      if (dt > 0.5) {
        const deltaFrames = (stats.frames_sent || 0) - (prevStats.current.frames_sent || 0);
        const deltaDropped = (stats.frames_dropped || 0) - (prevStats.current.frames_dropped || 0);
        const deltaBandwidthMB = (stats.total_bandwidth_mb || 0) - (prevStats.current.total_bandwidth_mb || 0);

        const recentFps = Math.round(deltaFrames / dt);
        const recentDropRate = deltaFrames > 0
          ? parseFloat(((deltaDropped / (deltaFrames + deltaDropped)) * 100).toFixed(1))
          : 0;
        const recentBandwidthKbps = Math.round((deltaBandwidthMB * 1024 * 8) / dt);

        setWindowedMetrics({
          recentFps: Math.max(0, recentFps),
          recentDropRate: Math.max(0, recentDropRate),
          recentBandwidthKbps: Math.max(0, recentBandwidthKbps),
        });
      }
    }

    prevStats.current = stats;
    prevTime.current = now;
  }, [stats]);

  if (loading || !stats) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Stream Performance
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Loading...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // Quality assessment based on recent drop rate
  const quality = windowedMetrics.recentDropRate < 1 ? 'excellent'
    : windowedMetrics.recentDropRate < 5 ? 'good' : 'poor';
  const qualityColor = quality === 'excellent' ? 'success' : quality === 'good' ? 'warning' : 'error';

  // Total active clients
  const totalClients = statusData ? statusData.totalClients : 0;

  // Current quality from adaptive engine
  const currentQuality = (() => {
    if (!statusData || !statusData.quality_engine || !statusData.quality_engine.clients) return null;
    const clients = Object.values(statusData.quality_engine.clients);
    if (clients.length === 0) return null;
    return Math.round(clients.reduce((sum, c) => sum + (c.quality || 60), 0) / clients.length);
  })();

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Stream Performance
        </Typography>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {/* Connection Status */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Clients:</Typography>
            <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
              <Chip
                icon={<CloudQueue />}
                label={totalClients}
                size="small"
                color="primary"
              />
              {statusData && statusData.active_method && (
                <Chip
                  label={statusData.active_method.toUpperCase()}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: '0.7rem' }}
                />
              )}
            </Box>
          </Box>

          {/* Recent FPS (windowed) */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">FPS (recent):</Typography>
            <Chip
              icon={<Speed />}
              label={windowedMetrics.recentFps}
              size="small"
              color={windowedMetrics.recentFps >= 15 ? 'success' : windowedMetrics.recentFps >= 5 ? 'warning' : 'error'}
            />
          </Box>

          {/* Current Quality Level */}
          {currentQuality !== null && (
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">JPEG Quality:</Typography>
              <Chip
                label={currentQuality}
                size="small"
                color={currentQuality >= 60 ? 'success' : currentQuality >= 35 ? 'warning' : 'error'}
              />
            </Box>
          )}

          {/* Recent Bandwidth */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">Bandwidth:</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
              {windowedMetrics.recentBandwidthKbps > 1024
                ? `${(windowedMetrics.recentBandwidthKbps / 1024).toFixed(1)} Mbps`
                : `${windowedMetrics.recentBandwidthKbps} kbps`
              }
            </Typography>
          </Box>

          {/* Drop Rate (windowed) */}
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
              <Typography variant="body2">Drop Rate:</Typography>
              <Chip
                label={`${windowedMetrics.recentDropRate}%`}
                size="small"
                color={qualityColor}
                icon={windowedMetrics.recentDropRate > 5 ? <Warning /> : <Speed />}
              />
            </Box>
            <LinearProgress
              variant="determinate"
              value={100 - windowedMetrics.recentDropRate}
              color={qualityColor}
              sx={{ height: 4, borderRadius: 2 }}
            />
          </Box>

          {/* Expandable lifetime totals */}
          <Box sx={{ display: 'flex', justifyContent: 'center' }}>
            <IconButton
              size="small"
              onClick={() => setShowLifetime(!showLifetime)}
              sx={{ p: 0.5 }}
            >
              {showLifetime ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
            </IconButton>
          </Box>

          <Collapse in={showLifetime}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, pt: 0.5, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" fontWeight="bold" color="text.secondary">
                Lifetime Totals
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">Frames Sent:</Typography>
                <Typography variant="caption" color="text.secondary">
                  {(stats.frames_sent || 0).toLocaleString()}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">Frames Dropped:</Typography>
                <Typography variant="caption" color="text.secondary">
                  {(stats.frames_dropped || 0).toLocaleString()}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">Total Bandwidth:</Typography>
                <Typography variant="caption" color="text.secondary">
                  {(stats.total_bandwidth_mb || 0).toFixed(1)} MB
                </Typography>
              </Box>
              {stats.cache_size > 0 && (
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="caption" color="text.secondary">Cache:</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {stats.cache_size} frames
                  </Typography>
                </Box>
              )}
            </Box>
          </Collapse>
        </Box>
      </CardContent>
    </Card>
  );
};

export default StreamingStats;
