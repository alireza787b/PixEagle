import React from 'react';
import PropTypes from 'prop-types';
import { Box, Paper, Typography } from '@mui/material';

const RawDataLog = ({ rawData, title = 'Diagnostics Payloads' }) => {
  return (
    <Paper
      variant="outlined"
      sx={{
        mt: 2,
        maxHeight: { xs: 280, md: 360 },
        overflowY: 'auto',
        p: 1.5,
        bgcolor: 'background.default',
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        {title}
      </Typography>
      {rawData.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No diagnostic payloads captured yet.
        </Typography>
      ) : (
        rawData.slice().reverse().map((data, index) => (
          <Box
            key={`${rawData.length}-${index}`}
            component="pre"
            sx={{
              m: 0,
              mb: 1,
              p: 1,
              borderRadius: 1,
              bgcolor: 'background.paper',
              border: '1px solid',
              borderColor: 'divider',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              overflowWrap: 'anywhere',
            }}
          >
            {JSON.stringify(data, null, 2)}
          </Box>
        ))
      )}
    </Paper>
  );
};

RawDataLog.propTypes = {
  rawData: PropTypes.arrayOf(PropTypes.object).isRequired,
  title: PropTypes.string,
};

export default RawDataLog;
