// dashboard/src/hooks/useBoundingBoxHandlers.js
import { useState, useRef, useEffect } from 'react';
import { endpoints } from '../services/apiEndpoints';

const useBoundingBoxHandlers = (isTracking, setIsTracking) => {
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);
  const imageRef = useRef();

  // Read default bounding box size from .env
  const defaultBoundingBoxSize =
    parseFloat(process.env.REACT_APP_DEFAULT_BOUNDING_BOX_SIZE) || 0.2; // default to 20%

  // Helper function to compute distance
  const getDistance = (pos1, pos2) => {
    const dx = pos2.x - pos1.x;
    const dy = pos2.y - pos1.y;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const timeoutRef = useRef(null);

  // Clean up the timeout when the component unmounts
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const startTracking = async (bbox) => {
    try {
      if (isTracking) {
        // Stop existing tracking
        await fetch(endpoints.stopTracking, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
      }

      // Start new tracking
      const response = await fetch(endpoints.startTracking, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bbox),
      });
      const data = await response.json();
      console.log('Tracking started:', data);
      setIsTracking(true);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  const handleStart = (clientX, clientY) => {
    const rect = imageRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setBoundingBox(null); // Reset any existing bounding box
  };

  const handleMove = (clientX, clientY) => {
    if (startPos) {
      const rect = imageRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      setCurrentPos({ x, y });
    }
  };

  const handleEnd = async () => {
    if (startPos && currentPos) {
      const rect = imageRef.current.getBoundingClientRect();
      const distance = getDistance(startPos, currentPos);
      let bbox;

      if (distance < 5) {
        // Treat as click
        const centerX = startPos.x;
        const centerY = startPos.y;
        const width = rect.width * defaultBoundingBoxSize;
        const height = rect.height * defaultBoundingBoxSize;
        const left = centerX - width / 2;
        const top = centerY - height / 2;

        // Normalize coordinates
        bbox = {
          x: left / rect.width,
          y: top / rect.height,
          width: defaultBoundingBoxSize,
          height: defaultBoundingBoxSize,
        };

        // Set bounding box for rendering
        setBoundingBox({
          left,
          top,
          width,
          height,
        });
      } else {
        // Treat as drag
        const x1 = startPos.x / rect.width;
        const y1 = startPos.y / rect.height;
        const x2 = currentPos.x / rect.width;
        const y2 = currentPos.y / rect.height;

        bbox = {
          x: Math.min(x1, x2),
          y: Math.min(y1, y2),
          width: Math.abs(x2 - x1),
          height: Math.abs(y2 - y1),
        };

        // Set bounding box for rendering
        setBoundingBox({
          left: Math.min(startPos.x, currentPos.x),
          top: Math.min(startPos.y, currentPos.y),
          width: Math.abs(currentPos.x - startPos.x),
          height: Math.abs(currentPos.y - startPos.y),
        });
      }

      console.log('Normalized Bounding Box:', bbox);
      await startTracking(bbox);

      // Set timeout to clear boundingBox after 500ms
      timeoutRef.current = setTimeout(() => {
        setBoundingBox(null);
      }, 500);

      // Reset positions
      setStartPos(null);
      setCurrentPos(null);
    }
  };

  const handleMouseDown = (e) => handleStart(e.clientX, e.clientY);
  const handleMouseMove = (e) => handleMove(e.clientX, e.clientY);
  const handleMouseUp = handleEnd;

  const handleTouchStart = (e) => {
    e.preventDefault();
    handleStart(e.touches[0].clientX, e.touches[0].clientY);
  };
  const handleTouchMove = (e) => {
    e.preventDefault();
    handleMove(e.touches[0].clientX, e.touches[0].clientY);
  };
  const handleTouchEnd = (e) => {
    e.preventDefault();
    handleEnd();
  };

  return {
    imageRef,
    startPos,
    currentPos,
    boundingBox,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  };
};

export default useBoundingBoxHandlers;
