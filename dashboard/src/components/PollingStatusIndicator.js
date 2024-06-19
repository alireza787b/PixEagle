import React, { useState, useEffect } from 'react';

const PollingStatusIndicator = ({ status }) => {
  const [displayStatus, setDisplayStatus] = useState(status);

  useEffect(() => {
    if (status === 'success') {
      setDisplayStatus('success');
    } else if (status === 'error') {
      setDisplayStatus('error');
    } else {
      const timeout = setTimeout(() => {
        setDisplayStatus('idle');
      }, 1000);
      return () => clearTimeout(timeout);
    }
  }, [status]);

  const getColor = () => {
    switch (displayStatus) {
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
      <div style={{ width: '20px', height: '20px', backgroundColor: getColor(), marginRight: '10px' }} />
      <span>{displayStatus === 'idle' ? 'Waiting' : displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}</span>
    </div>
  );
};

export default PollingStatusIndicator;
