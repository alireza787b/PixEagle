import React from 'react';
import WebRTCStream from './WebRTCStream';

const BoundingBoxDrawer = ({
  isTracking,
  imageRef,
  startPos,
  currentPos,
  handleMouseDown,
  handleMouseMove,
  handleMouseUp,
  videoSrc
}) => {
  return (
    <div 
      ref={imageRef}
      style={{ position: 'relative', display: 'inline-block', width: '100%' }}
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
  );
};

export default BoundingBoxDrawer;
