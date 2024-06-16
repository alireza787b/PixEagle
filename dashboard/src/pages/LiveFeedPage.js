import React, { useEffect, useState } from 'react';
import { Container, Typography, CircularProgress } from '@mui/material';

const WEBSOCKET_VIDEO_URL = `ws://${process.env.REACT_APP_WEBSOCKET_HOST}:${process.env.REACT_APP_WEBSOCKET_PORT}${process.env.REACT_APP_VIDEO_STREAM_URI}`;

const LiveFeedPage = () => {
  const [videoData, setVideoData] = useState(null);

  useEffect(() => {
    const socket = new WebSocket(WEBSOCKET_VIDEO_URL);

    socket.onopen = () => {
      console.log('WebSocket connection established');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.frame) {
          setVideoData(data.frame);
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    socket.onclose = () => {
      console.log('WebSocket connection closed');
    };

    return () => {
      socket.close();
    };
  }, []);

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
