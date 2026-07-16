import {
  normalizePointWithinVideo,
  pointInsideVideoBounds,
  resolveVideoContentBounds,
} from './videoGeometry';

const makeContainer = ({ width = 1600, height = 900, media = null } = {}) => ({
  getBoundingClientRect: () => ({ left: 10, top: 20, width, height }),
  querySelector: () => media,
});

test('uses the full interaction container when no media element is exposed', () => {
  expect(resolveVideoContentBounds(makeContainer({ width: 200, height: 100 }))).toEqual({
    left: 0,
    top: 0,
    width: 200,
    height: 100,
  });
});

test('returns no target-selection bounds before the first frame is ready', () => {
  const media = { dataset: { frameReady: 'false' }, width: 1920, height: 1080 };
  expect(resolveVideoContentBounds(makeContainer({ media }))).toBeNull();
});

test('calculates horizontal letterboxing for a portrait source', () => {
  const media = { dataset: { frameReady: 'true' }, videoWidth: 900, videoHeight: 1600 };
  const bounds = resolveVideoContentBounds(makeContainer({ media }));

  expect(bounds).toEqual({ left: 546.875, top: 0, width: 506.25, height: 900 });
  expect(pointInsideVideoBounds({ x: 200, y: 450 }, bounds)).toBe(false);
  expect(normalizePointWithinVideo({ x: 800, y: 450 }, bounds)).toEqual({ x: 0.5, y: 0.5 });
});

test('calculates vertical letterboxing for a four-by-three source', () => {
  const media = { dataset: { frameReady: 'true' }, naturalWidth: 640, naturalHeight: 480 };
  const bounds = resolveVideoContentBounds(makeContainer({ media }));

  expect(bounds).toEqual({ left: 200, top: 0, width: 1200, height: 900 });
  expect(normalizePointWithinVideo({ x: 800, y: 450 }, bounds)).toEqual({ x: 0.5, y: 0.5 });
});
