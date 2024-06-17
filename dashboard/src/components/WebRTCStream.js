// dashboard/src/components/WebRTCStream.js
import React from 'react';

const WebRTCStream = ({ protocol = 'http', src }) => {
  if (protocol === 'http') {
    return <img src={src} alt="Live Stream" style={{ width: '100%' }} />;
  }

  // Add more protocols here as needed

  return null; // Return null if protocol is not supported
};

export default WebRTCStream;
