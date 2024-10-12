// dashboard/src/components/BoundingBoxDrawer.js
import React, { useState, useRef } from 'react';
import WebRTCStream from './WebRTCStream';

const BoundingBoxDrawer = ({ videoSrc, protocol }) => {
  const imageRef = useRef(null);
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);

  // Read default bounding box size from .env
  const defaultBoundingBoxSize =
    parseFloat(process.env.REACT_APP_DEFAULT_BOUNDING_BOX_SIZE) || 0.2; // default to 20%

  // Helper function to compute distance
  const getDistance = (pos1, pos2) => {
    const dx = pos2.x - pos1.x;
    const dy = pos2.y - pos1.y;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const handleMouseDown = (e) => {
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setBoundingBox(null); // Reset any existing bounding box
  };

  const handleMouseMove = (e) => {
    if (!startPos) return;
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setCurrentPos({ x, y });
  };

  const handleMouseUp = (e) => {
    if (!startPos) return;
    const rect = imageRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setCurrentPos({ x, y });

    // Compute distance to determine if it's a click
    const distance = getDistance(startPos, { x, y });
    if (distance < 5) {
      // Treat as click
      const centerX = x;
      const centerY = y;
      const width = rect.width * defaultBoundingBoxSize;
      const height = rect.height * defaultBoundingBoxSize;
      const left = centerX - width / 2;
      const top = centerY - height / 2;

      setBoundingBox({ left, top, width, height });
    } else {
      // Treat as drag
      const left = Math.min(startPos.x, currentPos.x);
      const top = Math.min(startPos.y, currentPos.y);
      const width = Math.abs(currentPos.x - startPos.x);
      const height = Math.abs(currentPos.y - startPos.y);

      setBoundingBox({ left, top, width, height });
    }

    // Reset positions
    setStartPos(null);
    setCurrentPos(null);
  };

  // Touch event handlers (similar logic to mouse handlers)
  const handleTouchStart = (e) => {
    e.preventDefault();
    const touch = e.touches[0];
    const rect = imageRef.current.getBoundingClientRect();
    const x = touch.clientX - rect.left;
    const y = touch.clientY - rect.top;
    setStartPos({ x, y });
    setCurrentPos({ x, y });
    setBoundingBox(null); // Reset any existing bounding box
  };

  const handleTouchMove = (e) => {
    e.preventDefault();
    if (!startPos) return;
    const touch = e.touches[0];
    const rect = imageRef.current.getBoundingClientRect();
    const x = touch.clientX - rect.left;
    const y = touch.clientY - rect.top;
    setCurrentPos({ x, y });
  };

  const handleTouchEnd = (e) => {
    e.preventDefault();
    if (!startPos || !currentPos) return;

    // Compute distance to determine if it's a tap
    const distance = getDistance(startPos, currentPos);
    if (distance < 5) {
      // Treat as tap
      const centerX = startPos.x;
      const centerY = startPos.y;
      const width = imageRef.current.clientWidth * defaultBoundingBoxSize;
      const height = imageRef.current.clientHeight * defaultBoundingBoxSize;
      const left = centerX - width / 2;
      const top = centerY - height / 2;

      setBoundingBox({ left, top, width, height });
    } else {
      // Treat as drag
      const left = Math.min(startPos.x, currentPos.x);
      const top = Math.min(startPos.y, currentPos.y);
      const width = Math.abs(currentPos.x - startPos.x);
      const height = Math.abs(currentPos.y - startPos.y);

      setBoundingBox({ left, top, width, height });
    }

    // Reset positions
    setStartPos(null);
    setCurrentPos(null);
  };

  return (
    <div
      ref={imageRef}
      style={{
        position: 'relative',
        display: 'inline-block',
        width: '100%',
        touchAction: 'none',
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      <WebRTCStream protocol={protocol} src={videoSrc} />
      {(startPos && currentPos) || boundingBox ? (
        <div
          style={{
            position: 'absolute',
            border: '2px dashed red',
            left: boundingBox
              ? boundingBox.left
              : Math.min(startPos.x, currentPos.x),
            top: boundingBox
              ? boundingBox.top
              : Math.min(startPos.y, currentPos.y),
            width: boundingBox
              ? boundingBox.width
              : Math.abs(currentPos.x - startPos.x),
            height: boundingBox
              ? boundingBox.height
              : Math.abs(currentPos.y - startPos.y),
          }}
        />
      ) : null}
    </div>
  );
};

export default BoundingBoxDrawer;
