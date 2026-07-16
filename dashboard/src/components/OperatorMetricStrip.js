import React from 'react';
import { Box, Grid, Paper, Typography } from '@mui/material';

const OperatorMetricStrip = ({ items }) => (
  <Paper variant="outlined" sx={{ overflow: 'hidden', borderRadius: 1 }}>
    <Grid
      container
      sx={{
        '& > .MuiGrid-item': {
          borderBottom: 1,
          borderColor: 'divider',
        },
        '& > .MuiGrid-item:nth-of-type(odd)': {
          borderRight: 1,
          borderColor: 'divider',
        },
        '& > .MuiGrid-item:nth-of-type(n+3)': {
          borderBottom: 0,
        },
        '@media (min-width: 1200px)': {
          '& > .MuiGrid-item': {
            borderBottom: 0,
            borderRight: 1,
            borderColor: 'divider',
          },
          '& > .MuiGrid-item:last-of-type': {
            borderRight: 0,
          },
        },
      }}
    >
      {items.map(({ icon, label, value, detail, color = 'primary', muted = false }) => (
        <Grid item xs={6} lg={3} key={label}>
          <Box
            sx={{
              p: { xs: 1, sm: 1.25 },
              minHeight: { xs: 86, sm: 92 },
              display: 'flex',
              alignItems: 'flex-start',
              gap: 1,
            }}
          >
            <Box sx={{ color: `${color}.main`, pt: 0.25, flex: '0 0 auto' }}>
              {icon}
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', textTransform: 'uppercase', fontWeight: 600 }}
              >
                {label}
              </Typography>
              <Typography
                sx={{
                  mt: 0.1,
                  fontFamily: 'monospace',
                  fontSize: { xs: '0.88rem', sm: '1rem' },
                  lineHeight: 1.25,
                  overflowWrap: 'anywhere',
                  color: muted ? 'text.secondary' : 'text.primary',
                }}
              >
                {value}
              </Typography>
              {detail && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                  {detail}
                </Typography>
              )}
            </Box>
          </Box>
        </Grid>
      ))}
    </Grid>
  </Paper>
);

export default OperatorMetricStrip;
