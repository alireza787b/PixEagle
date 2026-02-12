// dashboard/src/components/BoundingBoxDrawer.js
import React, { useEffect, useState, useCallback } from 'react';
import VideoStream from './VideoStream';
import { sendCommand } from '../services/apiService';

// Click feedback ripple keyframes (injected once)
const RIPPLE_STYLE_ID = 'smart-click-ripple-style';
if (typeof document !== 'undefined' && !document.getElementById(RIPPLE_STYLE_ID)) {
  const style = document.createElement('style');
  style.id = RIPPLE_STYLE_ID;
  style.textContent = `
    @keyframes smartClickPulse {
      0% { transform: translate(-50%, -50%) scale(0.3); opacity: 1; }
      100% { transform: translate(-50%, -50%) scale(1.5); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
}

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
  smartModeActive,
}) => {
  const [containerDimensions, setContainerDimensions] = useState({ width: 0, height: 0 });
  const [clickFeedback, setClickFeedback] = useState(null);

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

  // Clear click feedback after animation
  useEffect(() => {
    if (clickFeedback) {
      const timer = setTimeout(() => setClickFeedback(null), 400);
      return () => clearTimeout(timer);
    }
  }, [clickFeedback]);

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

  // Smart Mode Click Handler with visual feedback
  const handleSmartClick = useCallback(async (e) => {
    if (!smartModeActive || !imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const normX = clickX / rect.width;
    const normY = clickY / rect.height;

    // Show click feedback ripple
    setClickFeedback({ x: clickX, y: clickY });

    try {
      await sendCommand('smartClick', { x: normX, y: normY });
    } catch (err) {
      console.error('Smart click failed:', err);
    }
  }, [smartModeActive, imageRef]);

  return (
    <div
      ref={imageRef}
      style={{
        position: 'relative',
        display: 'inline-block',
        width: '100%',
        touchAction: 'none',
        cursor: smartModeActive ? 'crosshair' : (startPos ? 'crosshair' : 'cell'),
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

      {/* Mode Indicator Badge */}
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 10px',
          borderRadius: 4,
          backgroundColor: smartModeActive
            ? 'rgba(46, 125, 50, 0.85)'
            : 'rgba(21, 101, 192, 0.85)',
          color: '#fff',
          fontSize: 11,
          fontWeight: 700,
          fontFamily: '"Roboto Mono", monospace',
          letterSpacing: 0.8,
          textTransform: 'uppercase',
          pointerEvents: 'none',
          userSelect: 'none',
          zIndex: 10,
          backdropFilter: 'blur(2px)',
        }}
      >
        <span style={{ fontSize: 13 }}>
          {smartModeActive ? '\u25C9' : '\u2295'}
        </span>
        {smartModeActive ? 'AI MODE' : 'CLASSIC'}
      </div>

      {/* Smart Click Feedback Ripple */}
      {clickFeedback && (
        <div
          style={{
            position: 'absolute',
            left: clickFeedback.x,
            top: clickFeedback.y,
            width: 32,
            height: 32,
            borderRadius: '50%',
            border: '2px solid rgba(76, 175, 80, 0.9)',
            pointerEvents: 'none',
            zIndex: 11,
            animation: 'smartClickPulse 0.4s ease-out forwards',
          }}
        />
      )}

      {/* Classic Mode Bounding Box Drawing */}
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
