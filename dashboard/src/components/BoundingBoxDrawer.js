// dashboard/src/components/BoundingBoxDrawer.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { IconButton, Tooltip } from '@mui/material';
import FullscreenIcon from '@mui/icons-material/Fullscreen';
import FullscreenExitIcon from '@mui/icons-material/FullscreenExit';
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
  const [isFullscreen, setIsFullscreen] = useState(false);
  const smartSelectionQueueRef = useRef({
    latestSequence: 0,
    disposed: false,
    activeController: null,
  });
  const { hasScope } = useAuthSession();
  const canExecuteActions = hasScope('actions:execute');
  const smartModeKnown = typeof smartModeActive === 'boolean';
  const isSmartMode = smartModeActive === true;
  const targetSelectionArmed = canExecuteActions
    && smartModeKnown
    && !isSmartMode
    && Boolean(selectionArmed ?? isTracking);

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

  useEffect(() => {
    const updateFullscreenState = () => {
      const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
      setIsFullscreen(fullscreenElement === imageRef.current);
    };
    document.addEventListener('fullscreenchange', updateFullscreenState);
    document.addEventListener('webkitfullscreenchange', updateFullscreenState);
    return () => {
      document.removeEventListener('fullscreenchange', updateFullscreenState);
      document.removeEventListener('webkitfullscreenchange', updateFullscreenState);
    };
  }, [imageRef]);

  // Clear click feedback after animation
  useEffect(() => {
    const queue = smartSelectionQueueRef.current;
    queue.disposed = false;
    return () => {
      queue.disposed = true;
      queue.activeController?.abort();
      queue.activeController = null;
      queue.latestSequence += 1;
    };
  }, []);

  useEffect(() => {
    if (isSmartMode) return;
    const queue = smartSelectionQueueRef.current;
    queue.activeController?.abort();
    queue.activeController = null;
    queue.latestSequence += 1;
  }, [isSmartMode]);

  useEffect(() => {
    if (clickFeedback) {
      if (clickFeedback.status === 'pending') return undefined;
      const timer = setTimeout(
        () => setClickFeedback(null),
        clickFeedback.status === 'info' ? 2400 : 1400
      );
      return () => clearTimeout(timer);
    }
    return undefined;
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

  const enqueueSmartSelection = useCallback((selection) => {
    const queue = smartSelectionQueueRef.current;
    const sequence = queue.latestSequence + 1;
    queue.latestSequence = sequence;
    queue.activeController?.abort();
    const controller = typeof AbortController !== 'undefined'
      ? new AbortController()
      : null;
    queue.activeController = controller;
    setClickFeedback({
      x: selection.clickX,
      y: selection.clickY,
      status: 'pending',
      message: 'Selecting target',
    });
    // Submit every click immediately.  The sequence gate keeps late server
    // responses from replacing the operator's newest selection; the backend
    // applies the same latest-generation rule before mutating tracker state.
    void (async () => {
      const current = { ...selection, sequence };
      try {
        const data = await apiFetchJson(endpoints.smartClickAction, {
          method: 'POST',
          signal: controller?.signal,
          body: JSON.stringify({
            ...buildActionRequest('smart_click', { ui: 'dashboard_video_canvas' }),
            click: {
              coordinate_space: 'normalized',
              x: current.normalizedPoint.x,
              y: current.normalizedPoint.y,
            },
          }),
        });
        if (data?.status === 'failure') {
          throw new Error(data.error || 'Smart click action failed');
        }
        if (!queue.disposed && current.sequence === queue.latestSequence) {
          setClickFeedback({
            x: current.clickX,
            y: current.clickY,
            status: 'success',
            message: 'Target selected',
          });
        }
      } catch (error) {
        const aborted = error?.name === 'AbortError';
        if (!aborted && !queue.disposed && current.sequence === queue.latestSequence) {
          setClickFeedback({
            x: current.clickX,
            y: current.clickY,
            status: 'error',
            message: error?.message || 'Target selection failed',
          });
        }
      } finally {
        if (queue.activeController === controller) {
          queue.activeController = null;
        }
      }
    })();
  }, []);

  // Smart Mode Click Handler with visual feedback
  const handleSmartClick = useCallback((e) => {
    if (!isSmartMode || !imageRef.current) return;

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

    enqueueSmartSelection({ clickX, clickY, normalizedPoint });
  }, [isSmartMode, imageRef, canExecuteActions, enqueueSmartSelection]);

  const handleSurfaceClick = useCallback((e) => {
    if (!smartModeKnown) {
      return;
    }
    if (isSmartMode) {
      void handleSmartClick(e);
      return;
    }
    if (targetSelectionArmed || !imageRef.current) {
      return;
    }

    const rect = imageRef.current.getBoundingClientRect();
    setClickFeedback({
      x: Math.max(8, Math.min(rect.width - 8, e.clientX - rect.left)),
      y: Math.max(8, Math.min(rect.height - 8, e.clientY - rect.top)),
      status: 'info',
      message: 'Selection paused',
    });
  }, [handleSmartClick, imageRef, isSmartMode, smartModeKnown, targetSelectionArmed]);

  const fullscreenSupported = typeof document !== 'undefined' && Boolean(
    document.fullscreenEnabled
    || document.webkitFullscreenEnabled
    || imageRef.current?.requestFullscreen
    || imageRef.current?.webkitRequestFullscreen
  );

  const toggleFullscreen = useCallback(async (event) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      const fullscreenElement = document.fullscreenElement || document.webkitFullscreenElement;
      if (fullscreenElement === imageRef.current) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (exit) await exit.call(document);
        return;
      }
      const request = imageRef.current?.requestFullscreen
        || imageRef.current?.webkitRequestFullscreen;
      if (request) await request.call(imageRef.current);
    } catch (error) {
      setClickFeedback({
        x: containerDimensions.width / 2,
        y: 24,
        status: 'error',
        message: 'Fullscreen unavailable',
      });
    }
  }, [containerDimensions.width, imageRef]);

  const feedbackColor = clickFeedback?.status === 'error'
    ? 'rgba(211, 47, 47, 0.95)'
    : clickFeedback?.status === 'info'
      ? 'rgba(25, 118, 210, 0.95)'
      : clickFeedback?.status === 'pending'
        ? 'rgba(255, 179, 0, 0.95)'
        : 'rgba(76, 175, 80, 0.9)';

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
        cursor: canExecuteActions && smartModeKnown && (isSmartMode || targetSelectionArmed)
          ? 'crosshair'
          : 'default',
        backgroundColor: '#000',
        ...(isFullscreen ? {
          width: '100vw',
          height: '100vh',
        } : {}),
      }}
      onPointerDown={targetSelectionArmed ? handlePointerDown : undefined}
      onPointerMove={targetSelectionArmed ? handlePointerMove : undefined}
      onPointerUp={targetSelectionArmed ? handlePointerUp : undefined}
      onClick={handleSurfaceClick}
    >
      <VideoStream protocol={protocol} src={videoSrc} fillContainer={isFullscreen} />

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
          backgroundColor: !smartModeKnown
            ? 'rgba(97, 97, 97, 0.9)'
            : isSmartMode
              ? 'rgba(46, 125, 50, 0.85)'
              : 'rgba(21, 101, 192, 0.85)',
          color: '#fff',
          fontSize: 11,
          fontWeight: 700,
          fontFamily: '"Roboto Mono", monospace',
          letterSpacing: 0,
          textTransform: 'uppercase',
          pointerEvents: 'none',
          userSelect: 'none',
          zIndex: 10,
          backdropFilter: 'blur(2px)',
        }}
      >
        <span style={{ fontSize: 13 }}>
          {!smartModeKnown ? '?' : isSmartMode ? '\u25C9' : '\u2295'}
        </span>
        {!smartModeKnown ? 'Tracker mode: Unknown' : isSmartMode ? 'Tracker: AI' : 'Tracker: Classic'}
      </div>

      <Tooltip title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
        <span
          style={{
            position: 'absolute',
            right: 8,
            bottom: 8,
            zIndex: 14,
          }}
        >
          <IconButton
            aria-label={isFullscreen ? 'Exit fullscreen video' : 'Fullscreen video'}
            size="small"
            disabled={!fullscreenSupported}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={toggleFullscreen}
            sx={{
              color: '#fff',
              bgcolor: 'rgba(0, 0, 0, 0.58)',
              '&:hover': { bgcolor: 'rgba(0, 0, 0, 0.78)' },
            }}
          >
            {isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
          </IconButton>
        </span>
      </Tooltip>

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
            border: `2px solid ${feedbackColor}`,
            pointerEvents: 'none',
            zIndex: 11,
            animation: 'smartClickPulse 0.4s ease-out forwards',
          }}
        />
      )}

      {clickFeedback && (
        <div
          role={clickFeedback.status === 'error' ? 'alert' : 'status'}
          aria-live={clickFeedback.status === 'error' ? 'assertive' : 'polite'}
          style={{
            position: 'absolute',
            left: '50%',
            top: 8,
            transform: 'translateX(-50%)',
            maxWidth: 'min(220px, 70%)',
            padding: '4px 7px',
            borderRadius: 4,
            backgroundColor: clickFeedback.status === 'error'
              ? 'rgba(183, 28, 28, 0.92)'
              : clickFeedback.status === 'success'
                ? 'rgba(46, 125, 50, 0.92)'
                : clickFeedback.status === 'pending'
                  ? 'rgba(87, 62, 0, 0.92)'
                  : 'rgba(21, 101, 192, 0.92)',
            color: '#fff',
            fontSize: 11,
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
