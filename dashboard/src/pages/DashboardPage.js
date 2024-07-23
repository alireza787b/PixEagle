import React, { useState, useRef, useEffect } from 'react';
import { Container, Typography, CircularProgress, Box } from '@mui/material';
import ActionButtons from '../components/ActionButtons';
import BoundingBoxDrawer from '../components/BoundingBoxDrawer';
import { videoFeed, endpoints } from '../services/apiEndpoints';

const DashboardPage = () => {
  const [isTracking, setIsTracking] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [loading, setLoading] = useState(true);
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

      fetch(endpoints.startTracking, {
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
      fetch(endpoints.stopTracking, {
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

      if (endpoint === endpoints.quit) {
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

  useEffect(() => {
    const checkStream = setInterval(() => {
      const img = new Image();
      img.src = videoFeed;

      img.onload = () => {
        setLoading(false);
        clearInterval(checkStream);
      };

      img.onerror = () => {
        console.error('Error loading video feed');
      };
    }, 2000); // Check every 2 seconds

    return () => clearInterval(checkStream);
  }, []);

  return (
    <Container>
      <Typography variant="h4" gutterBottom align="center">Dashboard</Typography>
      {loading && (
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" minHeight="400px">
          <CircularProgress />
          <Typography variant="body1" align="center" sx={{ mt: 2 }}>
            Loading video feed, please wait...
          </Typography>
        </Box>
      )}
      {!loading && (
        <Box>
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
            videoSrc={videoFeed}
          />
        </Box>
      )}
    </Container>
  );
};

export default DashboardPage;
