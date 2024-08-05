//dashboard/src/hooks/useBoundingBoxHandlers.js
import { useState, useRef } from 'react';
import { endpoints } from '../services/apiEndpoints';

const useBoundingBoxHandlers = (isTracking, setIsTracking) => {
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const imageRef = useRef();

  const startTracking = async (bbox) => {
    try {
      if (isTracking) {
        // Stop existing tracking
        await fetch(endpoints.stopTracking, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
      }

      // Start new tracking
      const response = await fetch(endpoints.startTracking, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bbox)
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

      await startTracking(bbox);

      setStartPos(null);
      setCurrentPos(null);
    }
  };

  const handleMouseDown = (e) => handleStart(e.clientX, e.clientY);
  const handleMouseMove = (e) => handleMove(e.clientX, e.clientY);
  const handleMouseUp = handleEnd;
  const handleTouchStart = (e) => handleStart(e.touches[0].clientX, e.touches[0].clientY);
  const handleTouchMove = (e) => handleMove(e.touches[0].clientX, e.touches[0].clientY);
  const handleTouchEnd = handleEnd;

  return {
    imageRef,
    startPos,
    currentPos,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
  };
};

export default useBoundingBoxHandlers;
