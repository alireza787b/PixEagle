const isPositiveFinite = (value) => Number.isFinite(value) && value > 0;

const readIntrinsicSize = (mediaElement) => {
  if (!mediaElement) return null;

  const candidates = [
    [mediaElement.videoWidth, mediaElement.videoHeight],
    [mediaElement.naturalWidth, mediaElement.naturalHeight],
    [mediaElement.width, mediaElement.height],
  ];
  const match = candidates.find(([width, height]) => (
    isPositiveFinite(Number(width)) && isPositiveFinite(Number(height))
  ));
  if (!match) return null;
  return { width: Number(match[0]), height: Number(match[1]) };
};

const fullContainerBounds = (containerRect) => ({
  left: 0,
  top: 0,
  width: containerRect.width,
  height: containerRect.height,
});

/**
 * Returns the visible media rectangle relative to the interaction container.
 * A null result means a media element exists but no frame is ready for target
 * selection. Missing media elements fall back to the full container so simple
 * embedding and test doubles remain usable.
 */
export const resolveVideoContentBounds = (container) => {
  if (!container || typeof container.getBoundingClientRect !== 'function') {
    return null;
  }

  const containerRect = container.getBoundingClientRect();
  if (!isPositiveFinite(containerRect.width) || !isPositiveFinite(containerRect.height)) {
    return null;
  }

  const mediaElement = container.querySelector?.('[data-video-media="true"]') || null;
  if (!mediaElement) {
    return fullContainerBounds(containerRect);
  }
  if (mediaElement.dataset?.frameReady === 'false') {
    return null;
  }

  const intrinsic = readIntrinsicSize(mediaElement);
  if (!intrinsic) {
    return fullContainerBounds(containerRect);
  }

  const containerAspect = containerRect.width / containerRect.height;
  const mediaAspect = intrinsic.width / intrinsic.height;
  if (mediaAspect > containerAspect) {
    const height = containerRect.width / mediaAspect;
    return {
      left: 0,
      top: (containerRect.height - height) / 2,
      width: containerRect.width,
      height,
    };
  }

  const width = containerRect.height * mediaAspect;
  return {
    left: (containerRect.width - width) / 2,
    top: 0,
    width,
    height: containerRect.height,
  };
};

export const pointInsideVideoBounds = (point, bounds) => Boolean(
  point
  && bounds
  && point.x >= bounds.left
  && point.x <= bounds.left + bounds.width
  && point.y >= bounds.top
  && point.y <= bounds.top + bounds.height
);

export const normalizePointWithinVideo = (point, bounds) => {
  if (!pointInsideVideoBounds(point, bounds)) return null;
  return {
    x: (point.x - bounds.left) / bounds.width,
    y: (point.y - bounds.top) / bounds.height,
  };
};
