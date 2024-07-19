import React, { useState, useEffect } from 'react';
import { Container, Typography, CircularProgress, Box } from '@mui/material';
import WebRTCStream from '../components/WebRTCStream';
import { videoFeed } from '../services/apiEndpoints';

const LiveFeedPage = () => {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
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
    }, 5000); // Check every 5 seconds

    return () => clearInterval(checkStream);
  }, []);

  return (
    <Container>
      <Typography variant="h4" gutterBottom align="center">Live Video Feed</Typography>
      {loading && (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      )}
      {!loading && (
        <Box>
          <WebRTCStream protocol="http" src={videoFeed} />
        </Box>
      )}
    </Container>
  );
};

export default LiveFeedPage;
