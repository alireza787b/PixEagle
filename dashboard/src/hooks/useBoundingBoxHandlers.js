import { useState, useRef, useEffect, useCallback } from 'react';
import { endpoints } from '../services/apiEndpoints';

/**
 * Hook for bounding-box drag drawing (classic tracker) and smart-click (AI tracker).
 *
 * Uses Pointer Events with pointer capture so the rectangle tracks cleanly
 * even when the cursor/finger leaves the video container during a drag.
 */
const useBoundingBoxHandlers = (isTracking, setIsTracking, smartModeActive = false) => {
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);
  const imageRef = useRef(null);

  const defaultBoundingBoxSize =
    parseFloat(process.env.REACT_APP_DEFAULT_BOUNDING_BOX_SIZE) || 0.2;

  const timeoutRef = useRef(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const getDistance = (pos1, pos2) => {
    const dx = pos2.x - pos1.x;
    const dy = pos2.y - pos1.y;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const startTracking = useCallback(async (bbox) => {
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
  }, [isTracking, setIsTracking]);

  // ── Pointer handlers (unified mouse + touch + pen) ─────────────────

  const handlePointerDown = useCallback((e) => {
    if (smartModeActive) return;       // smart mode uses onClick instead
    if (e.button !== 0) return;        // left button only

    e.preventDefault();
    e.target.setPointerCapture(e.pointerId);
    draggingRef.current = true;

    const rect = imageRef.current.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);

    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setBoundingBox(null);
  }, [smartModeActive]);

  const handlePointerMove = useCallback((e) => {
    if (!draggingRef.current || smartModeActive) return;
    if (!imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    // Clamp to container bounds for clean drawing
    const x = Math.round(Math.max(0, Math.min(e.clientX - rect.left, rect.width)));
    const y = Math.round(Math.max(0, Math.min(e.clientY - rect.top, rect.height)));

    setCurrentPos({ x, y });
  }, [smartModeActive]);

  const handlePointerUp = useCallback(async (e) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;

    if (e.target.hasPointerCapture(e.pointerId)) {
      e.target.releasePointerCapture(e.pointerId);
    }

    // Read refs for the final computation
    const start = startPos;
    const current = currentPos;
    if (!start || !current || smartModeActive) {
      setStartPos(null);
      setCurrentPos(null);
      return;
    }

    const rect = imageRef.current.getBoundingClientRect();
    const distance = getDistance(start, current);
    let bbox;

    const dragThreshold = Math.max(5, (window.devicePixelRatio || 1) * 5);
    if (distance < dragThreshold) {
      // Click-to-center: create default-size box around click point
      const centerX = start.x;
      const centerY = start.y;
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

      setBoundingBox({
        left: Math.round(left),
        top: Math.round(top),
        width: Math.round(width),
        height: Math.round(height),
      });
    } else {
      // Drag: compute normalized bbox
      const x1 = start.x / rect.width;
      const y1 = start.y / rect.height;
      const x2 = current.x / rect.width;
      const y2 = current.y / rect.height;

      bbox = {
        x: Math.min(x1, x2),
        y: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1),
      };

      setBoundingBox({
        left: Math.round(Math.min(start.x, current.x)),
        top: Math.round(Math.min(start.y, current.y)),
        width: Math.round(Math.abs(current.x - start.x)),
        height: Math.round(Math.abs(current.y - start.y)),
      });
    }

    console.log('Normalized Bounding Box:', bbox);
    await startTracking(bbox);

    timeoutRef.current = setTimeout(() => {
      setBoundingBox(null);
    }, 500);

    setStartPos(null);
    setCurrentPos(null);
  }, [startPos, currentPos, smartModeActive, defaultBoundingBoxSize, startTracking]);

  return {
    imageRef,
    startPos,
    currentPos,
    boundingBox,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  };
};

export default useBoundingBoxHandlers;
