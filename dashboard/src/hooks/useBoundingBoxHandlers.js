import { useState, useRef, useEffect } from 'react';
import { endpoints } from '../services/apiEndpoints';

const useBoundingBoxHandlers = (isTracking, setIsTracking, smartModeActive = false) => {
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);
  const imageRef = useRef();

  const defaultBoundingBoxSize =
    parseFloat(process.env.REACT_APP_DEFAULT_BOUNDING_BOX_SIZE) || 0.2;

  const timeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const getDistance = (pos1, pos2) => {
    const dx = pos2.x - pos1.x;
    const dy = pos2.y - pos1.y;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const startTracking = async (bbox) => {
    try {
      if (isTracking) {
        await fetch(endpoints.stopTracking, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
      }

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

  const sendSmartClick = async (normX, normY) => {
    try {
      const res = await fetch(endpoints.smartClick, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: normX, y: normY }),
      });
      const data = await res.json();
      console.log('Smart click sent:', data);
    } catch (err) {
      console.error('Failed to send smart click:', err);
    }
  };

  const handleStart = (clientX, clientY) => {
    const rect = imageRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    if (smartModeActive) {
      // Send normalized smart click
      const normX = x / rect.width;
      const normY = y / rect.height;
      sendSmartClick(normX, normY);
      return;
    }

    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setBoundingBox(null);
  };

  const handleMove = (clientX, clientY) => {
    if (startPos && !smartModeActive) {
      const rect = imageRef.current.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      setCurrentPos({ x, y });
    }
  };

  const handleEnd = async () => {
    if (!startPos || !currentPos || smartModeActive) return;

    const rect = imageRef.current.getBoundingClientRect();
    const distance = getDistance(startPos, currentPos);
    let bbox;

    const dragThreshold = Math.max(5, (window.devicePixelRatio || 1) * 5);
    if (distance < dragThreshold) {
      const centerX = startPos.x;
      const centerY = startPos.y;
      const width = rect.width * defaultBoundingBoxSize;
      const height = rect.height * defaultBoundingBoxSize;
      const left = centerX - width / 2;
      const top = centerY - height / 2;

      bbox = {
        x: left / rect.width,
        y: top / rect.height,
        width: defaultBoundingBoxSize,
        height: defaultBoundingBoxSize,
      };

      setBoundingBox({ left, top, width, height });
    } else {
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

      setBoundingBox({
        left: Math.min(startPos.x, currentPos.x),
        top: Math.min(startPos.y, currentPos.y),
        width: Math.abs(currentPos.x - startPos.x),
        height: Math.abs(currentPos.y - startPos.y),
      });
    }

    console.log('Normalized Bounding Box:', bbox);
    await startTracking(bbox);

    timeoutRef.current = setTimeout(() => {
      setBoundingBox(null);
    }, 500);

    setStartPos(null);
    setCurrentPos(null);
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
