// dashboard/src/pages/LiveFeedPage.js
import React, { useState, useEffect } from 'react';
import {
  Container,
  Typography,
  CircularProgress,
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import VideoStream from '../components/VideoStream';
import OSDToggle from '../components/OSDToggle';
import StreamingStatusIndicator from '../components/StreamingStatusIndicator';
import GStreamerQGCPanel from '../components/GStreamerQGCPanel';
import { videoFeed } from '../services/apiEndpoints';

const LiveFeedPage = () => {
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('auto'); // Default to 'auto'

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
        <VideoStream
          protocol={streamingProtocol}
          src={videoFeed}
          showStats={true}          // Show FPS, bandwidth, latency
          showQualityControl={true} // Show quality adjustment slider
        />
        </Box>
      )}
    </Container>
  );
};

export default LiveFeedPage;
