import { createLatestJpegFrameRenderer } from './latestJpegFrameRenderer';

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
};

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

const createCanvas = () => {
  const context = {
    clearRect: jest.fn(),
    drawImage: jest.fn(),
  };
  const canvas = {
    width: 0,
    height: 0,
    getContext: jest.fn(() => context),
  };
  return { canvas, context };
};

const originalCreateImageBitmap = global.createImageBitmap;
const originalImage = global.Image;
const originalCreateObjectURL = global.URL.createObjectURL;
const originalRevokeObjectURL = global.URL.revokeObjectURL;

afterEach(() => {
  if (originalCreateImageBitmap === undefined) {
    delete global.createImageBitmap;
  } else {
    global.createImageBitmap = originalCreateImageBitmap;
  }
  global.Image = originalImage;
  global.URL.createObjectURL = originalCreateObjectURL;
  global.URL.revokeObjectURL = originalRevokeObjectURL;
  jest.restoreAllMocks();
});

test('decodes with createImageBitmap, renders, and closes the bitmap', async () => {
  const decode = deferred();
  const bitmap = { width: 640, height: 480, close: jest.fn() };
  global.createImageBitmap = jest.fn(() => decode.promise);
  const { canvas, context } = createCanvas();
  const onRender = jest.fn();
  const { enqueue } = createLatestJpegFrameRenderer(canvas, { onRender });
  const metadata = { frameId: 12 };
  const jpeg = new Blob(['frame'], { type: 'image/jpeg' });

  expect(enqueue(jpeg, metadata)).toBe(true);
  await Promise.resolve();
  expect(global.createImageBitmap).toHaveBeenCalledWith(jpeg);

  decode.resolve(bitmap);
  await flushPromises();

  expect(canvas.width).toBe(640);
  expect(canvas.height).toBe(480);
  expect(context.clearRect).toHaveBeenCalledWith(0, 0, 640, 480);
  expect(context.drawImage).toHaveBeenCalledWith(bitmap, 0, 0);
  expect(onRender).toHaveBeenCalledWith(metadata);
  expect(bitmap.close).toHaveBeenCalledTimes(1);
});

test('keeps one decode active and renders only the newest pending frame', async () => {
  const firstDecode = deferred();
  const newestDecode = deferred();
  global.createImageBitmap = jest
    .fn()
    .mockImplementationOnce(() => firstDecode.promise)
    .mockImplementationOnce(() => newestDecode.promise);
  const { canvas, context } = createCanvas();
  const onRender = jest.fn();
  const { enqueue } = createLatestJpegFrameRenderer(canvas, { onRender });
  const first = new Blob(['first'], { type: 'image/jpeg' });
  const replaced = new Blob(['replaced'], { type: 'image/jpeg' });
  const newest = new Blob(['newest'], { type: 'image/jpeg' });
  const firstBitmap = { width: 320, height: 240, close: jest.fn() };
  const newestBitmap = { width: 800, height: 600, close: jest.fn() };

  enqueue(first, { frameId: 1 });
  await Promise.resolve();
  enqueue(replaced, { frameId: 2 });
  enqueue(newest, { frameId: 3 });

  expect(global.createImageBitmap).toHaveBeenCalledTimes(1);
  firstDecode.resolve(firstBitmap);
  await flushPromises();

  expect(context.drawImage).not.toHaveBeenCalled();
  expect(firstBitmap.close).toHaveBeenCalledTimes(1);
  expect(global.createImageBitmap).toHaveBeenCalledTimes(2);
  expect(global.createImageBitmap).toHaveBeenLastCalledWith(newest);

  newestDecode.resolve(newestBitmap);
  await flushPromises();

  expect(context.drawImage).toHaveBeenCalledTimes(1);
  expect(context.drawImage).toHaveBeenCalledWith(newestBitmap, 0, 0);
  expect(onRender).toHaveBeenCalledTimes(1);
  expect(onRender).toHaveBeenCalledWith({ frameId: 3 });
  expect(newestBitmap.close).toHaveBeenCalledTimes(1);
});

test('falls back to Image and revokes its object URL after rendering', async () => {
  delete global.createImageBitmap;
  const image = {
    width: 400,
    height: 300,
    naturalWidth: 400,
    naturalHeight: 300,
    onload: null,
    onerror: null,
    src: '',
  };
  global.Image = jest.fn(() => image);
  global.URL.createObjectURL = jest.fn(() => 'blob:pixeagle-frame');
  global.URL.revokeObjectURL = jest.fn();
  const { canvas, context } = createCanvas();
  const onRender = jest.fn();
  const { enqueue } = createLatestJpegFrameRenderer(canvas, { onRender });
  const metadata = { timestamp: 42 };
  const jpeg = new Uint8Array([0xff, 0xd8, 0xff]);

  enqueue(jpeg, metadata);

  expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1);
  expect(global.Image).toHaveBeenCalledTimes(1);
  expect(image.src).toBe('blob:pixeagle-frame');

  image.onload();
  await flushPromises();

  expect(context.drawImage).toHaveBeenCalledWith(image, 0, 0);
  expect(onRender).toHaveBeenCalledWith(metadata);
  expect(global.URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  expect(global.URL.revokeObjectURL).toHaveBeenCalledWith('blob:pixeagle-frame');
});

test('close discards pending work and disposes an in-flight decoded bitmap', async () => {
  const decode = deferred();
  const bitmap = { width: 640, height: 480, close: jest.fn() };
  global.createImageBitmap = jest.fn(() => decode.promise);
  const { canvas, context } = createCanvas();
  const onRender = jest.fn();
  const { close, enqueue } = createLatestJpegFrameRenderer(canvas, { onRender });

  enqueue(new Blob(['active']), { frameId: 1 });
  await Promise.resolve();
  enqueue(new Blob(['pending']), { frameId: 2 });
  close();
  expect(enqueue(new Blob(['closed']), { frameId: 3 })).toBe(false);

  decode.resolve(bitmap);
  await flushPromises();

  expect(global.createImageBitmap).toHaveBeenCalledTimes(1);
  expect(context.drawImage).not.toHaveBeenCalled();
  expect(onRender).not.toHaveBeenCalled();
  expect(bitmap.close).toHaveBeenCalledTimes(1);
});

test('continues with the newest pending frame after a decode error', async () => {
  const firstDecode = deferred();
  const nextBitmap = { width: 200, height: 100, close: jest.fn() };
  global.createImageBitmap = jest
    .fn()
    .mockImplementationOnce(() => firstDecode.promise)
    .mockResolvedValueOnce(nextBitmap);
  const { canvas, context } = createCanvas();
  const onError = jest.fn();
  const { enqueue } = createLatestJpegFrameRenderer(canvas, { onError });

  enqueue(new Blob(['broken']), { frameId: 1 });
  await Promise.resolve();
  enqueue(new Blob(['next']), { frameId: 2 });
  firstDecode.reject(new Error('decode failed'));
  await flushPromises();

  expect(onError).toHaveBeenCalledWith(
    expect.objectContaining({ message: 'decode failed' }),
    { frameId: 1 }
  );
  expect(context.drawImage).toHaveBeenCalledWith(nextBitmap, 0, 0);
  expect(nextBitmap.close).toHaveBeenCalledTimes(1);
});
