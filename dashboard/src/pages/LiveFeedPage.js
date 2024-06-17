// dashboard/src/pages/LiveFeedPage.js
import React from 'react';
import { Container, Typography } from '@mui/material';
import WebRTCStream from '../components/WebRTCStream';

const flaskHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
const flaskPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;

const LiveFeedPage = () => {
  const videoSrc = `http://${flaskHost}:${flaskPort}/video_feed`;

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Live Video Feed</Typography>
      <WebRTCStream protocol="http" src={videoSrc} />
    </Container>
  );
};

export default LiveFeedPage;
