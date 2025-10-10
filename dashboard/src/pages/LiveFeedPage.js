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
import WebRTCStream from '../components/WebRTCStream';
import OSDToggle from '../components/OSDToggle';
import { videoFeed } from '../services/apiEndpoints';

const LiveFeedPage = () => {
  const [loading, setLoading] = useState(true);
  const [streamingProtocol, setStreamingProtocol] = useState('websocket'); // Default to 'websocket'

  useEffect(() => {
    if (streamingProtocol === 'http') {
      // Check the HTTP video feed
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
    } else if (streamingProtocol === 'websocket') {
      // For WebSocket, assume the feed is available
      setLoading(false);
    }
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
          <MenuItem value="websocket">WebSocket</MenuItem>
          <MenuItem value="http">HTTP</MenuItem>
        </Select>
      </FormControl>

      {/* OSD Toggle Control */}
      <Box sx={{ mt: 2, mb: 2 }}>
        <OSDToggle />
      </Box>

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
        <WebRTCStream 
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
