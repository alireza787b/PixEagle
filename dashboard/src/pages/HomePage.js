import React from 'react';
import { Container, Typography } from '@mui/material';

const HomePage = () => {
  return (
    <Container>
      <Typography variant="h4" gutterBottom>
        Welcome to My Web App
      </Typography>
      <Typography variant="body1">
        This is the home page.
      </Typography>
    </Container>
  );
};

export default HomePage;
