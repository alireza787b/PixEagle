import React from 'react';
import { Box, Typography, Link } from '@mui/material';

const Footer = () => {
  return (
    <Box component="footer" sx={{ py: 2, textAlign: 'center', mt: 'auto', bgcolor: 'background.paper' }}>
      <Typography variant="body2">
        © 2025 <Link href="https://github.com/alireza787b/PixEagle" target="_blank" rel="noopener">PixEagle</Link> | All rights reserved | Developed by <Link href="https://www.linkedin.com/in/alireza787b/" target="_blank" rel="noopener">Alireza787b</Link>
      </Typography>
    </Box>
  );
};

export default Footer;
