// dashboard/src/components/BoundingBoxDrawer.js
import React, { useEffect, useState, useCallback } from 'react';
import VideoStream from './VideoStream';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';
import { useAuthSession } from '../context/AuthSessionContext';
import {
  normalizePointWithinVideo,
  resolveVideoContentBounds,
} from '../utils/videoGeometry';

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
  selectionArmed,
  imageRef,
  startPos,
  currentPos,
  boundingBox,
  handlePointerDown,
  handlePointerMove,
  handlePointerUp,
  videoSrc,
  protocol,
  smartModeActive,
}) => {
  const [containerDimensions, setContainerDimensions] = useState({ width: 0, height: 0 });
  const [clickFeedback, setClickFeedback] = useState(null);
  const { hasScope } = useAuthSession();
  const canExecuteActions = hasScope('actions:execute');
  const targetSelectionArmed = selectionArmed ?? isTracking;

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

    // Update dimensions after a short delay to account for video loading
    const timeout = setTimeout(updateDimensions, 100);

    return () => {
      window.removeEventListener('resize', updateDimensions);
      clearTimeout(timeout);
    };
  }, [imageRef, protocol]);

  // Clear click feedback after animation
  useEffect(() => {
    if (clickFeedback) {
      const timer = setTimeout(
        () => setClickFeedback(null),
        clickFeedback.status === 'pending' ? 5000 : 1400
      );
      return () => clearTimeout(timer);
    }
  }, [clickFeedback]);

  const isDrawing = (startPos && currentPos) || boundingBox;

  let left = 0, top = 0, width = 0, height = 0;

  if (isDrawing && containerDimensions.width && containerDimensions.height) {
    left = boundingBox ? boundingBox.left : Math.round(Math.min(startPos.x, currentPos.x));
    top = boundingBox ? boundingBox.top : Math.round(Math.min(startPos.y, currentPos.y));
    width = boundingBox ? boundingBox.width : Math.round(Math.abs(currentPos.x - startPos.x));
    height = boundingBox ? boundingBox.height : Math.round(Math.abs(currentPos.y - startPos.y));

    const containerWidth = containerDimensions.width;
    const containerHeight = containerDimensions.height;

    left = Math.max(0, left);
    top = Math.max(0, top);
    width = Math.min(width, containerWidth - left);
    height = Math.min(height, containerHeight - top);
  }

  // Smart Mode Click Handler with visual feedback
  const handleSmartClick = useCallback(async (e) => {
    if (!smartModeActive || !imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const contentBounds = resolveVideoContentBounds(imageRef.current);
    const normalizedPoint = normalizePointWithinVideo(
      { x: clickX, y: clickY },
      contentBounds,
    );

    if (!contentBounds || !normalizedPoint) {
      setClickFeedback({
        x: clickX,
        y: clickY,
        status: 'error',
        message: contentBounds ? 'Select within the visible video' : 'Video frame unavailable',
      });
      return;
    }

    if (!canExecuteActions) {
      setClickFeedback({
        x: clickX,
        y: clickY,
        status: 'error',
        message: 'Action permission required',
      });
      return;
    }

    setClickFeedback({
      x: clickX,
      y: clickY,
      status: 'pending',
      message: 'Selecting target',
    });

    try {
      const data = await apiFetchJson(endpoints.smartClickAction, {
        method: 'POST',
        body: JSON.stringify({
          ...buildActionRequest('smart_click', { ui: 'dashboard_video_canvas' }),
          click: {
            coordinate_space: 'normalized',
            x: normalizedPoint.x,
            y: normalizedPoint.y,
          },
        }),
      });
      if (data?.status === 'failure') {
        throw new Error(data.error || 'Smart click action failed');
      }
      setClickFeedback({
        x: clickX,
        y: clickY,
        status: 'success',
        message: 'Target selected',
      });
    } catch (err) {
      setClickFeedback({
        x: clickX,
        y: clickY,
        status: 'error',
        message: err?.message || 'Target selection failed',
      });
    }
  }, [smartModeActive, imageRef, canExecuteActions]);

  return (
    <div
      data-testid="bounding-box-draw-surface"
      ref={imageRef}
      style={{
        position: 'relative',
        display: 'block',
        width: '100%',
        touchAction: 'none',
        userSelect: 'none',
        WebkitUserSelect: 'none',
        cursor: smartModeActive || targetSelectionArmed ? 'crosshair' : 'default',
      }}
      onPointerDown={!smartModeActive && targetSelectionArmed ? handlePointerDown : undefined}
      onPointerMove={!smartModeActive && targetSelectionArmed ? handlePointerMove : undefined}
      onPointerUp={!smartModeActive && targetSelectionArmed ? handlePointerUp : undefined}
      onClick={smartModeActive ? handleSmartClick : undefined}
    >
      <VideoStream protocol={protocol} src={videoSrc} />

      {/* Mode Indicator Badge */}
      <div
        data-testid="tracker-mode-badge"
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
        {smartModeActive ? 'Tracker: AI' : 'Tracker: Classic'}
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
            border: `2px solid ${
              clickFeedback.status === 'error'
                ? 'rgba(211, 47, 47, 0.95)'
                : 'rgba(76, 175, 80, 0.9)'
            }`,
            pointerEvents: 'none',
            zIndex: 11,
            animation: 'smartClickPulse 0.4s ease-out forwards',
          }}
        />
      )}

      {clickFeedback?.status === 'error' && (
        <div
          role="status"
          style={{
            position: 'absolute',
            left: Math.max(8, clickFeedback.x + 18),
            top: Math.max(8, clickFeedback.y - 18),
            maxWidth: 'min(260px, calc(100% - 16px))',
            padding: '5px 8px',
            borderRadius: 4,
            backgroundColor: 'rgba(183, 28, 28, 0.92)',
            color: '#fff',
            fontSize: 12,
            fontWeight: 600,
            lineHeight: 1.3,
            pointerEvents: 'none',
            zIndex: 12,
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.24)',
          }}
        >
          {clickFeedback.message}
        </div>
      )}

      {/* Classic Mode Bounding Box Drawing */}
      {isDrawing && !smartModeActive && (
        <div
          style={{
            position: 'absolute',
            left,
            top,
            width,
            height,
            border: '2px solid #ff5722',
            borderRadius: 1,
            backgroundColor: 'rgba(255, 87, 34, 0.08)',
            pointerEvents: 'none',
            zIndex: 5,
            boxShadow: '0 0 0 1px rgba(255, 87, 34, 0.3)',
          }}
        />
      )}
    </div>
  );
};

export default BoundingBoxDrawer;
