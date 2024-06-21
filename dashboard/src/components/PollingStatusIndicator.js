import React from 'react';
import PropTypes from 'prop-types';
import { Typography } from '@mui/material';

const PollingStatusIndicator = ({ status }) => {
  const getColor = () => {
    switch (status) {
      case 'success':
        return 'green';
      case 'error':
        return 'red';
      default:
        return 'yellow';
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      <Typography variant="body1" style={{ marginRight: '10px' }}>
        {status === 'idle' ? 'Waiting' : status === 'success' ? 'Success' : 'Error'}
      </Typography>
      <div
        style={{
          width: '20px',
          height: '20px',
          backgroundColor: getColor(),
          borderRadius: '50%',
        }}
      />
    </div>
  );
};

PollingStatusIndicator.propTypes = {
  status: PropTypes.oneOf(['idle', 'success', 'error']).isRequired,
};

export default PollingStatusIndicator;
