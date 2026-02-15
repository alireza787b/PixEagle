// dashboard/src/pages/LiveFeedPage.js
import React, { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Typography,
  CircularProgress,
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Card,
  CardContent,
  Grid,
  Chip,
  Divider,
} from '@mui/material';
import VideoStream from '../components/VideoStream';
import OSDToggle from '../components/OSDToggle';
import StreamingStatusIndicator from '../components/StreamingStatusIndicator';
import GStreamerQGCPanel from '../components/GStreamerQGCPanel';
import StreamingStats from '../components/StreamingStats';
import RecordingQuickControl from '../components/RecordingQuickControl';
import RecordingIndicator from '../components/RecordingIndicator';
import { videoFeed, endpoints } from '../services/apiEndpoints';

const LiveFeedPage = () => {
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('auto'); // Default to 'auto'
  const [streamDebug, setStreamDebug] = useState({
    requestedProtocol: 'auto',
    effectiveProtocol: 'websocket',
    isConnecting: false,
    hasReceivedFrame: false,
    error: null,
    reconnectAttempts: 0,
    qualitySetting: 60,
    fps: 0,
    streamQuality: 60,
    bandwidthKbps: 0,
    latencyMs: 0,
    frameCount: 0,
    lastFrameTime: 0,
    websocketReadyState: null,
    webrtcIceState: null,
    updatedAt: null,
  });

  const formatBandwidth = (kbps) => {
    if (!Number.isFinite(kbps) || kbps <= 0) {
      return '0 kbps';
    }
    if (kbps >= 1024) {
      return `${(kbps / 1024).toFixed(2)} Mbps`;
    }
    return `${Math.round(kbps)} kbps`;
  };

  const getConnectionState = () => {
    if (streamDebug.error) {
      return { label: 'Degraded', color: 'error' };
    }
    if (streamDebug.isConnecting) {
      return { label: 'Connecting', color: 'warning' };
    }
    if (streamDebug.hasReceivedFrame) {
      return { label: 'Live', color: 'success' };
    }
    return { label: 'Idle', color: 'default' };
  };

  const wsStateLabel = (() => {
    const map = {
      0: 'CONNECTING',
      1: 'OPEN',
      2: 'CLOSING',
      3: 'CLOSED',
    };
    return map[streamDebug.websocketReadyState] || 'N/A';
  })();

  const connectionState = getConnectionState();

  // Keyboard shortcut: R = toggle recording
  const handleKeyboardShortcut = useCallback((e) => {
    const tag = e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) return;
    if (e.key.toLowerCase() === 'r') {
      fetch(endpoints.recordingToggle, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }).catch((err) => console.error('Recording toggle failed:', err));
    }
  }, []);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyboardShortcut);
    return () => window.removeEventListener('keydown', handleKeyboardShortcut);
  }, [handleKeyboardShortcut]);

  useEffect(() => {
    if (streamingProtocol === 'websocket' || streamingProtocol === 'webrtc' || streamingProtocol === 'auto') {
      // WebSocket/WebRTC/Auto manage their own connection state
      setLoading(false);
      return;
    }

    // Only probe HTTP endpoint when protocol is 'http'
    const checkStream = setInterval(() => {
      const img = new Image();
      img.src = videoFeed;

      img.onload = () => {
        setLoading(false);
        clearInterval(checkStream);
      };

      img.onerror = () => {
        console.error('Error loading video feed');
      };
    }, 2000); // Check every 2 seconds

    return () => clearInterval(checkStream);
  }, [streamingProtocol]);

  return (
    <Container>
      <Typography variant="h4" gutterBottom align="center">
        Live Video Feed
      </Typography>

      {/* Dropdown for selecting streaming protocol */}
      <FormControl variant="outlined" fullWidth margin="normal">
        <InputLabel id="streaming-protocol-label">Streaming Protocol</InputLabel>
        <Select
          labelId="streaming-protocol-label"
          value={streamingProtocol}
          onChange={(e) => {
            setLoading(true); // Reset loading state when protocol changes
            setStreamingProtocol(e.target.value);
          }}
          label="Streaming Protocol"
        >
          <MenuItem value="auto">Auto (Best Available)</MenuItem>
          <MenuItem value="webrtc">WebRTC (Low Latency)</MenuItem>
          <MenuItem value="websocket">WebSocket</MenuItem>
          <MenuItem value="http">HTTP (Fallback)</MenuItem>
        </Select>
      </FormControl>

      {/* OSD Toggle Control */}
      <Box sx={{ mt: 2, mb: 2 }}>
        <OSDToggle />
      </Box>

      {/* Streaming Status Indicator */}
      <StreamingStatusIndicator />

      {/* GStreamer QGC Output Control */}
      <GStreamerQGCPanel />

      {loading ? (
        <Box
          display="flex"
          flexDirection="column"
          alignItems="center"
          justifyContent="center"
          minHeight="400px"
        >
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      ) : (
        <Box>
        <Box sx={{ position: 'relative' }}>
          <RecordingIndicator />
        <VideoStream
          protocol={streamingProtocol}
          src={videoFeed}
          showStats={true}          // Show FPS, bandwidth, latency
          showQualityControl={true} // Show quality adjustment slider
          onStreamDebugUpdate={setStreamDebug}
        />
        </Box>

        {/* Recording Quick Controls */}
        <Box sx={{ mt: 2 }}>
          <Card variant="outlined">
            <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  fontWeight: 700,
                  color: 'text.secondary',
                  textTransform: 'uppercase',
                  letterSpacing: 1,
                  mb: 1,
                  fontSize: 11,
                }}
              >
                Recording
              </Typography>
              <RecordingQuickControl />
            </CardContent>
          </Card>
        </Box>

        <Box sx={{ mt: 2 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <StreamingStats />
            </Grid>
            <Grid item xs={12} md={6}>
              <Card variant="outlined" sx={{ height: '100%' }}>
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h6">Stream Diagnostics</Typography>
                    <Chip label={connectionState.label} color={connectionState.color} size="small" />
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    Runtime transport and player-side telemetry for quick troubleshooting.
                  </Typography>

                  <Grid container spacing={1}>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">Requested Protocol</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {String(streamDebug.requestedProtocol || 'n/a').toUpperCase()}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">Active Protocol</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {String(streamDebug.effectiveProtocol || 'n/a').toUpperCase()}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">WebSocket State</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {wsStateLabel}
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">WebRTC ICE State</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {streamDebug.webrtcIceState || 'N/A'}
                      </Typography>
                    </Grid>
                  </Grid>

                  <Divider sx={{ my: 1.5 }} />

                  <Grid container spacing={1}>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">FPS</Typography>
                      <Typography variant="body2">{streamDebug.fps || 0}</Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">Quality</Typography>
                      <Typography variant="body2">
                        {streamDebug.streamQuality || 0} (set {streamDebug.qualitySetting || 0})
                      </Typography>
                    </Grid>
                    <Grid item xs={4}>
                      <Typography variant="caption" color="text.secondary">Latency</Typography>
                      <Typography variant="body2">{streamDebug.latencyMs || 0} ms</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">Bandwidth</Typography>
                      <Typography variant="body2">{formatBandwidth(streamDebug.bandwidthKbps)}</Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="caption" color="text.secondary">Frames Rendered</Typography>
                      <Typography variant="body2">{(streamDebug.frameCount || 0).toLocaleString()}</Typography>
                    </Grid>
                  </Grid>

                  <Divider sx={{ my: 1.5 }} />

                  <Typography variant="caption" color="text.secondary">Source</Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all', mb: 0.5 }}>
                    {videoFeed}
                  </Typography>
                  {streamDebug.error && (
                    <Typography variant="body2" color="error">
                      Last Error: {streamDebug.error}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
        </Box>
      )}
    </Container>
  );
};

export default LiveFeedPage;
