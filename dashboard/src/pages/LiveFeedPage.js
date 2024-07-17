import React, { useState, useRef } from 'react';
import { Container, Typography, Grid } from '@mui/material';
import WebRTCStream from '../components/WebRTCStream';
import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';

const apiHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
const apiPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;
const startTrackingEndpoint = `http://${apiHost}:${apiPort}/commands/start_tracking`;
const stopTrackingEndpoint = `http://${apiHost}:${apiPort}/commands/stop_tracking`;
const redetectEndpoint = `http://${apiHost}:${apiPort}/commands/redetect`;
const cancelActivitiesEndpoint = `http://${apiHost}:${apiPort}/commands/cancel_activities`;
const toggleSegmentationEndpoint = `http://${apiHost}:${apiPort}/commands/toggle_segmentation`;
const startOffboardModeEndpoint = `http://${apiHost}:${apiPort}/commands/start_offboard_mode`;
const stopOffboardModeEndpoint = `http://${apiHost}:${apiPort}/commands/stop_offboard_mode`;
const quitEndpoint = `http://${apiHost}:${apiPort}/commands/quit`;

const LiveFeedPage = () => {
  const videoSrc = `http://${apiHost}:${apiPort}/video_feed`;
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

      const bbox = {
        x: Math.min(x1, x2),
        y: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1)
      };

      console.log('Raw Bounding Box:', { startX: startPos.x, startY: startPos.y, endX: currentPos.x, endY: currentPos.y });
      console.log('Normalized Bounding Box:', bbox);

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

  const handleButtonClick = async (endpoint, updateTrackingState = false) => {
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
      });
      const data = await response.json();
      console.log(`Response from ${endpoint}:`, data);

      if (endpoint === quitEndpoint) {
        window.location.reload();  // Reload the page to ensure proper shutdown
      }

      if (updateTrackingState) {
        setIsTracking(false);
      }
    } catch (error) {
      console.error(`Error from ${endpoint}:`, error);
      alert(`Operation failed for endpoint ${endpoint}. Check console for details.`);
    }
  };

  return (
    <Container>
      <Typography variant="h4" gutterBottom>Live Video Feed</Typography>
      <ActionButtons 
        isTracking={isTracking} 
        handleTrackingToggle={handleTrackingToggle} 
        handleButtonClick={handleButtonClick} 
      />
      <BoundingBoxDrawer 
        isTracking={isTracking}
        imageRef={imageRef}
        startPos={startPos}
        currentPos={currentPos}
        handleMouseDown={handleMouseDown}
        handleMouseMove={handleMouseMove}
        handleMouseUp={handleMouseUp}
        videoSrc={videoSrc}
      />
    </Container>
  );
};

export default LiveFeedPage;
