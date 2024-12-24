// dashboard/src/components/BoundingBoxDrawer.js
import React, { useEffect, useState } from 'react';
import WebRTCStream from './WebRTCStream';

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
    left = boundingBox
      ? boundingBox.left
      : Math.min(startPos.x, currentPos.x);
    top = boundingBox
      ? boundingBox.top
      : Math.min(startPos.y, currentPos.y);
    width = boundingBox
      ? boundingBox.width
      : Math.abs(currentPos.x - startPos.x);
    height = boundingBox
      ? boundingBox.height
      : Math.abs(currentPos.y - startPos.y);

    const containerWidth = containerDimensions.width;
    const containerHeight = containerDimensions.height;

    // Bound checks
    left = Math.max(0, left);
    top = Math.max(0, top);
    width = Math.min(width, containerWidth - left);
    height = Math.min(height, containerHeight - top);

    // Overlays for dark areas
    overlays = [
      {
        top: 0,
        left: 0,
        width: containerWidth,
        height: top,
      },
      {
        top: top + height,
        left: 0,
        width: containerWidth,
        height: containerHeight - (top + height),
      },
      {
        top: top,
        left: 0,
        width: left,
        height: height,
      },
      {
        top: top,
        left: left + width,
        width: containerWidth - (left + width),
        height: height,
      },
    ];
  }

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

      {isDrawing && (
        <>
          <div
            style={{
              position: 'absolute',
              border: '2px dashed red',
              left,
              top,
              width,
              height,
              pointerEvents: 'none',
            }}
          />
          {overlays.map((overlay, i) => (
            <div
              key={i}
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
