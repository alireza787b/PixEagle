import React, { useState, useRef } from 'react';
import { Container, Typography, Button } from '@mui/material';
import WebRTCStream from '../components/WebRTCStream';

const flaskHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
const flaskPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;
const startTrackingEndpoint = `http://${flaskHost}:${flaskPort}/commands/start_tracking`;
const stopTrackingEndpoint = `http://${flaskHost}:${flaskPort}/commands/stop_tracking`;

const LiveFeedPage = () => {
  const videoSrc = `http://${flaskHost}:${flaskPort}/video_feed`;
  const [isTracking, setIsTracking] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const imageRef = useRef();

  const handleMouseDown = (e) => {
    if (isTracking) {
      const rect = imageRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setStartPos({ x, y });
      setCurrentPos({ x, y });
    }
  };

  const handleMouseMove = (e) => {
    if (isTracking && startPos) {
      const rect = imageRef.current.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setCurrentPos({ x, y });
    }
  };

  const handleMouseUp = () => {
    if (isTracking && startPos && currentPos) {
      const rect = imageRef.current.getBoundingClientRect();
      const x1 = startPos.x / rect.width;
      const y1 = startPos.y / rect.height;
      const x2 = currentPos.x / rect.width;
      const y2 = currentPos.y / rect.height;

      // Normalize and get bbox in OpenCV format (x, y, width, height)
      const bbox = {
        x: Math.min(x1, x2),
        y: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1)
      };

      // Log raw and normalized bounding box coordinates
      console.log('Raw Bounding Box:', { startX: startPos.x, startY: startPos.y, endX: currentPos.x, endY: currentPos.y });
      console.log('Normalized Bounding Box:', bbox);

      // Send the normalized bounding box to the start tracking endpoint
      fetch(startTrackingEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(bbox)
      })
      .then(response => response.json())
      .then(data => console.log('Tracking started:', data))
      .catch(error => console.error('Error:', error));

      setStartPos(null);
      setCurrentPos(null);
    }
  };

  const handleTrackingToggle = () => {
    if (isTracking) {
      // Stop tracking by sending a request to the stop tracking endpoint
      fetch(stopTrackingEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
      })
      .then(response => response.json())
      .then(data => console.log('Tracking stopped:', data))
      .catch(error => console.error('Error:', error));
    }
    setIsTracking(!isTracking);
  };

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Live Video Feed</Typography>
      <Button 
        variant="contained" 
        color={isTracking ? "secondary" : "primary"}
        onClick={handleTrackingToggle}
        sx={{ mb: 2 }}
      >
        {isTracking ? "Stop Tracking" : "Start Tracking"}
      </Button>
      <div 
        ref={imageRef}
        style={{ position: 'relative', display: 'inline-block' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
      >
        <WebRTCStream protocol="http" src={videoSrc} />
        {startPos && currentPos && (
          <div
            style={{
              position: 'absolute',
              border: '2px dashed red',
              left: Math.min(startPos.x, currentPos.x),
              top: Math.min(startPos.y, currentPos.y),
              width: Math.abs(currentPos.x - startPos.x),
              height: Math.abs(currentPos.y - startPos.y)
            }}
          />
        )}
      </div>
    </Container>
  );
};

export default LiveFeedPage;
