// src/pages/LiveFeedPage.js

import React from 'react';
import { Container, Typography, CircularProgress } from '@mui/material';
import useWebSocket from '../hooks/useWebSocket';

const WEBSOCKET_VIDEO_URL = `ws://${process.env.REACT_APP_WEBSOCKET_HOST}:${process.env.REACT_APP_WEBSOCKET_VIDEO_PORT}/ws`;

const LiveFeedPage = () => {
  const { videoData } = useWebSocket(WEBSOCKET_VIDEO_URL);

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Live Video Feed</Typography>
      {videoData ? (
        <img src={`data:image/jpeg;base64,${videoData}`} alt="Live Feed" style={{ width: '100%', height: 'auto' }} />
      ) : (
        <CircularProgress />
      )}
    </Container>
  );
};

export default LiveFeedPage;
