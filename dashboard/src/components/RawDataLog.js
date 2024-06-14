import React from 'react';
import PropTypes from 'prop-types';
import { Paper, Typography, Box } from '@mui/material';

const RawDataLog = ({ rawData }) => (
  <Paper style={{ padding: '1em', maxHeight: '200px', overflow: 'auto' }}>
    <Typography variant="h6">Raw Data Log</Typography>
    <Box component="pre" style={{ whiteSpace: 'pre-wrap' }}>
      {rawData.map((data, index) => (
        <div key={index}>{data}</div>
      ))}
    </Box>
  </Paper>
);

RawDataLog.propTypes = {
  rawData: PropTypes.arrayOf(PropTypes.string).isRequired,
};

export default RawDataLog;
