// dashboard/src/components/BoundingBoxDrawer.js
import React, { useEffect, useState } from 'react';
import VideoStream from './VideoStream';
import { sendCommand } from '../services/apiService';

const BoundingBoxDrawer = ({
  isTracking,
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
  videoSrc,
  protocol,
  smartModeActive, // ✅ NEW prop
}) => {
  const [containerDimensions, setContainerDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const updateDimensions = () => {
      if (imageRef.current) {
        setContainerDimensions({
          width: imageRef.current.clientWidth,
          height: imageRef.current.clientHeight,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, [imageRef]);

  const isDrawing = (startPos && currentPos) || boundingBox;

  let left, top, width, height;
  let overlays = [];

  if (isDrawing && containerDimensions.width && containerDimensions.height) {
    left = boundingBox ? boundingBox.left : Math.min(startPos.x, currentPos.x);
    top = boundingBox ? boundingBox.top : Math.min(startPos.y, currentPos.y);
    width = boundingBox ? boundingBox.width : Math.abs(currentPos.x - startPos.x);
    height = boundingBox ? boundingBox.height : Math.abs(currentPos.y - startPos.y);

    const containerWidth = containerDimensions.width;
    const containerHeight = containerDimensions.height;

    left = Math.max(0, left);
    top = Math.max(0, top);
    width = Math.min(width, containerWidth - left);
    height = Math.min(height, containerHeight - top);

    overlays = [
      { top: 0, left: 0, width: containerWidth, height: top },
      { top: top + height, left: 0, width: containerWidth, height: containerHeight - (top + height) },
      { top: top, left: 0, width: left, height: height },
      { top: top, left: left + width, width: containerWidth - (left + width), height: height },
    ];
  }

  // ✅ Smart Mode Click Handler
  const handleSmartClick = async (e) => {
    if (!smartModeActive || !imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const normX = (e.clientX - rect.left) / rect.width;
    const normY = (e.clientY - rect.top) / rect.height;

    try {
      await sendCommand('smartClick', { x: normX, y: normY });
      console.log('Smart click sent:', { x: normX, y: normY });
    } catch (err) {
      console.error('Smart click failed:', err);
    }
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
      onMouseDown={!smartModeActive ? handleMouseDown : null}
      onMouseMove={!smartModeActive ? handleMouseMove : null}
      onMouseUp={!smartModeActive ? handleMouseUp : null}
      onTouchStart={!smartModeActive ? handleTouchStart : null}
      onTouchMove={!smartModeActive ? handleTouchMove : null}
      onTouchEnd={!smartModeActive ? handleTouchEnd : null}
      onClick={smartModeActive ? handleSmartClick : null}
    >
      <VideoStream protocol={protocol} src={videoSrc} />
      {isDrawing && !smartModeActive && (
        <>
          <div
            style={{
              position: 'absolute',
              border: '2px dashed red',
              left: left,
              top: top,
              width: width,
              height: height,
              pointerEvents: 'none',
            }}
          />
          {overlays.map((overlay, index) => (
            <div
              key={index}
              style={{
                position: 'absolute',
                top: overlay.top,
                left: overlay.left,
                width: overlay.width,
                height: overlay.height,
                backgroundColor: 'rgba(0, 0, 0, 0.5)',
                pointerEvents: 'none',
              }}
            />
          ))}
        </>
      )}
    </div>
  );
};

export default BoundingBoxDrawer;
