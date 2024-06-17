// dashboard/src/pages/LiveFeedPage.js
import React from 'react';
import { Container, Typography } from '@mui/material';
import WebRTCStream from '../components/WebRTCStream';

const LiveFeedPage = () => {
  return (
    <Container>
      <Typography variant="h4" gutterBottom>Live Video Feed</Typography>
      <WebRTCStream />
    </Container>
  );
};

export default LiveFeedPage;
