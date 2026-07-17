import { useState, useRef, useEffect, useCallback } from 'react';
import { endpoints } from '../services/apiEndpoints';
import { apiFetchJson } from '../services/apiClient';
import { buildActionRequest } from '../services/actionRequests';
import { pointInsideVideoBounds, resolveVideoContentBounds } from '../utils/videoGeometry';

const CANVAS_ACTION_METADATA = { ui: 'dashboard_video_canvas' };
const FALLBACK_BOUNDING_BOX_SIZE = 0.04;
const MIN_DRAG_SIDE_CSS_PX = 5;

export const resolveDefaultBoundingBoxSize = (rawValue) => {
  const parsed = Number.parseFloat(rawValue);
  return Number.isFinite(parsed) && parsed > 0 && parsed <= 1
    ? parsed
    : FALLBACK_BOUNDING_BOX_SIZE;
};

const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

export const buildNormalizedBoundingBox = ({
  start,
  current,
  containerWidth,
  containerHeight,
  defaultSize,
  contentBounds = null,
}) => {
  if (!start || !current || containerWidth <= 0 || containerHeight <= 0) {
    return null;
  }

  const bounds = contentBounds || {
    left: 0,
    top: 0,
    width: containerWidth,
    height: containerHeight,
  };
  if (
    !Number.isFinite(bounds.left)
    || !Number.isFinite(bounds.top)
    || !Number.isFinite(bounds.width)
    || !Number.isFinite(bounds.height)
    || bounds.width <= 0
    || bounds.height <= 0
  ) {
    return null;
  }

  const maximumX = bounds.left + bounds.width;
  const maximumY = bounds.top + bounds.height;
  const startX = clamp(start.x, bounds.left, maximumX);
  const startY = clamp(start.y, bounds.top, maximumY);
  const currentX = clamp(current.x, bounds.left, maximumX);
  const currentY = clamp(current.y, bounds.top, maximumY);
  const deltaX = Math.abs(currentX - startX);
  const deltaY = Math.abs(currentY - startY);
  const distance = Math.hypot(deltaX, deltaY);

  if (
    distance < MIN_DRAG_SIDE_CSS_PX
    || deltaX < MIN_DRAG_SIDE_CSS_PX
    || deltaY < MIN_DRAG_SIDE_CSS_PX
  ) {
    const width = bounds.width * defaultSize;
    const height = bounds.height * defaultSize;
    const left = clamp(startX - width / 2, bounds.left, maximumX - width);
    const top = clamp(startY - height / 2, bounds.top, maximumY - height);
    return {
      bbox: {
        coordinate_space: 'normalized',
        x: (left - bounds.left) / bounds.width,
        y: (top - bounds.top) / bounds.height,
        width: defaultSize,
        height: defaultSize,
      },
      display: {
        left: Math.round(left),
        top: Math.round(top),
        width: Math.round(width),
        height: Math.round(height),
      },
    };
  }

  const left = Math.min(startX, currentX);
  const top = Math.min(startY, currentY);
  const width = Math.abs(currentX - startX);
  const height = Math.abs(currentY - startY);
  return {
    bbox: {
      coordinate_space: 'normalized',
      x: (left - bounds.left) / bounds.width,
      y: (top - bounds.top) / bounds.height,
      width: width / bounds.width,
      height: height / bounds.height,
    },
    display: {
      left: Math.round(left),
      top: Math.round(top),
      width: Math.round(width),
      height: Math.round(height),
    },
  };
};

const ensureActionSuccess = (data, label) => {
  if (data?.status === 'failure') {
    throw new Error(data.error || `${label} failed`);
  }
  return data;
};

/**
 * Hook for bounding-box drag drawing (classic tracker) and smart-click (AI tracker).
 *
 * Uses Pointer Events with pointer capture so the rectangle tracks cleanly
 * even when the cursor/finger leaves the video container during a drag.
 */
const useBoundingBoxHandlers = (
  selectionArmed,
  setSelectionArmed,
  smartModeActive = false,
  continuousSelection = true,
) => {
  const [startPos, setStartPos] = useState(null);
  const [currentPos, setCurrentPos] = useState(null);
  const [boundingBox, setBoundingBox] = useState(null);
  const [actionError, setActionError] = useState(null);
  const imageRef = useRef(null);

  const defaultBoundingBoxSize = resolveDefaultBoundingBoxSize(
    process.env.REACT_APP_DEFAULT_BOUNDING_BOX_SIZE
  );

  const timeoutRef = useRef(null);
  const startQueueRef = useRef({
    processing: false,
    pending: null,
    latestSequence: 0,
    disposed: false,
  });
  const draggingRef = useRef(false);
  const pointerGenerationRef = useRef(0);
  const startPosRef = useRef(null);
  const currentPosRef = useRef(null);
  const clearActionError = useCallback(() => setActionError(null), []);
  const clearPointerState = useCallback(() => {
    draggingRef.current = false;
    startPosRef.current = null;
    currentPosRef.current = null;
    setStartPos(null);
    setCurrentPos(null);
  }, []);

  useEffect(() => {
    const queue = startQueueRef.current;
    queue.disposed = false;
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      queue.disposed = true;
      if (queue.pending) queue.pending.resolve(null);
      queue.pending = null;
      queue.latestSequence += 1;
    };
  }, []);

  useEffect(() => {
    if (selectionArmed && !smartModeActive) return;
    const queue = startQueueRef.current;
    queue.latestSequence += 1;
    if (queue.pending) queue.pending.resolve(null);
    queue.pending = null;
    pointerGenerationRef.current += 1;
    clearPointerState();
    setBoundingBox(null);
  }, [clearPointerState, selectionArmed, smartModeActive]);

  const startTracking = useCallback((bbox) => new Promise((resolve) => {
    const queue = startQueueRef.current;
    const sequence = queue.latestSequence + 1;
    queue.latestSequence = sequence;
    if (queue.pending) queue.pending.resolve(null);
    queue.pending = { bbox, resolve, sequence };
    setActionError(null);
    if (queue.processing) return;

    queue.processing = true;
    void (async () => {
      try {
        while (queue.pending && !queue.disposed) {
          const current = queue.pending;
          queue.pending = null;
          try {
            const data = await apiFetchJson(endpoints.trackingStartAction, {
              method: 'POST',
              body: JSON.stringify({
                ...buildActionRequest('start_tracking_roi', CANVAS_ACTION_METADATA),
                bbox: current.bbox,
              }),
            });
            ensureActionSuccess(data, 'Starting tracker');
            const latest = current.sequence === queue.latestSequence;
            if (latest && !queue.disposed) {
              setSelectionArmed(Boolean(continuousSelection));
            }
            current.resolve(latest && !queue.disposed ? true : null);
          } catch (error) {
            const latest = current.sequence === queue.latestSequence;
            if (latest && !queue.disposed) {
              console.error('Error:', error);
              setActionError(error?.message || 'Failed to start tracking.');
            }
            current.resolve(latest && !queue.disposed ? false : null);
          }
        }
      } finally {
        queue.processing = false;
      }
    })();
  }), [continuousSelection, setSelectionArmed]);

  // ── Pointer handlers (unified mouse + touch + pen) ─────────────────

  const handlePointerDown = useCallback((e) => {
    if (smartModeActive || !selectionArmed) return;
    if (e.button !== 0) return;        // left button only
    if (!imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const contentBounds = resolveVideoContentBounds(imageRef.current);
    const point = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    if (!contentBounds || !pointInsideVideoBounds(point, contentBounds)) {
      return;
    }

    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    pointerGenerationRef.current += 1;

    const x = Math.round(point.x);
    const y = Math.round(point.y);

    const pointPosition = { x, y };
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    startPosRef.current = pointPosition;
    currentPosRef.current = pointPosition;
    setStartPos(pointPosition);
    setCurrentPos(pointPosition);
    setBoundingBox(null);
  }, [selectionArmed, smartModeActive]);

  const handlePointerMove = useCallback((e) => {
    if (!draggingRef.current || smartModeActive) return;
    if (!imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const contentBounds = resolveVideoContentBounds(imageRef.current);
    if (!contentBounds) return;
    const x = Math.round(clamp(
      e.clientX - rect.left,
      contentBounds.left,
      contentBounds.left + contentBounds.width,
    ));
    const y = Math.round(clamp(
      e.clientY - rect.top,
      contentBounds.top,
      contentBounds.top + contentBounds.height,
    ));

    const pointPosition = { x, y };
    currentPosRef.current = pointPosition;
    setCurrentPos(pointPosition);
  }, [smartModeActive]);

  const handlePointerUp = useCallback(async (e) => {
    if (!draggingRef.current) return;
    const pointerGeneration = pointerGenerationRef.current;
    draggingRef.current = false;

    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }

    const start = startPosRef.current;
    if (!start || smartModeActive || !imageRef.current) {
      clearPointerState();
      return;
    }

    const rect = imageRef.current.getBoundingClientRect();
    const contentBounds = resolveVideoContentBounds(imageRef.current);
    if (!contentBounds) {
      clearPointerState();
      return;
    }
    const current = {
      x: Math.round(clamp(
        e.clientX - rect.left,
        contentBounds.left,
        contentBounds.left + contentBounds.width,
      )),
      y: Math.round(clamp(
        e.clientY - rect.top,
        contentBounds.top,
        contentBounds.top + contentBounds.height,
      )),
    };
    currentPosRef.current = current;
    setCurrentPos(current);
    const selection = buildNormalizedBoundingBox({
      start,
      current,
      containerWidth: rect.width,
      containerHeight: rect.height,
      defaultSize: defaultBoundingBoxSize,
      contentBounds,
    });
    if (!selection) {
      clearPointerState();
      return;
    }

    setBoundingBox(selection.display);
    const started = await startTracking(selection.bbox);

    if (pointerGeneration !== pointerGenerationRef.current) {
      return;
    }

    if (started !== null) {
      timeoutRef.current = setTimeout(() => {
        setBoundingBox(null);
      }, started ? 500 : 1500);
    }

    clearPointerState();
  }, [clearPointerState, smartModeActive, defaultBoundingBoxSize, startTracking]);

  return {
    imageRef,
    startPos,
    currentPos,
    boundingBox,
    actionError,
    clearActionError,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
  };
};

export default useBoundingBoxHandlers;
