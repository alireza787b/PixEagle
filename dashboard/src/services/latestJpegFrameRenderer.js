const toJpegBlob = (frame) => {
  if (frame instanceof Blob) {
    return frame;
  }

  if (frame instanceof ArrayBuffer || ArrayBuffer.isView(frame)) {
    return new Blob([frame], { type: 'image/jpeg' });
  }

  throw new TypeError('JPEG frame must be a Blob, ArrayBuffer, or typed array');
};

const once = (callback) => {
  let called = false;
  return () => {
    if (called) {
      return;
    }
    called = true;
    callback();
  };
};

const createBitmapDecodeTask = (blob, decodeBitmap) => {
  let cancelled = false;

  return {
    promise: Promise.resolve()
      .then(() => decodeBitmap(blob))
      .then((bitmap) => {
        const dispose = once(() => bitmap.close?.());
        if (cancelled) {
          dispose();
          return null;
        }

        return {
          drawable: bitmap,
          width: bitmap.width,
          height: bitmap.height,
          dispose,
        };
      }),
    cancel: () => {
      cancelled = true;
    },
  };
};

const createImageDecodeTask = (blob, ImageConstructor, urlApi) => {
  let cancelled = false;
  let image = null;
  let objectUrl = null;
  let decodedResource = null;
  let settle = null;

  const revokeObjectUrl = once(() => {
    if (objectUrl !== null) {
      urlApi.revokeObjectURL(objectUrl);
    }
  });

  const promise = new Promise((resolve, reject) => {
    settle = resolve;

    try {
      objectUrl = urlApi.createObjectURL(blob);
      image = new ImageConstructor();
      image.onload = () => {
        image.onload = null;
        image.onerror = null;

        const dispose = once(revokeObjectUrl);
        decodedResource = {
          drawable: image,
          width: image.naturalWidth || image.width,
          height: image.naturalHeight || image.height,
          dispose,
        };

        if (cancelled) {
          dispose();
          resolve(null);
          return;
        }

        resolve(decodedResource);
      };
      image.onerror = () => {
        image.onload = null;
        image.onerror = null;
        revokeObjectUrl();
        reject(new Error('JPEG frame could not be decoded'));
      };
      image.src = objectUrl;
    } catch (error) {
      revokeObjectUrl();
      reject(error);
    }
  });

  return {
    promise,
    cancel: () => {
      cancelled = true;
      decodedResource?.dispose();

      if (image && !decodedResource) {
        image.onload = null;
        image.onerror = null;
        image.src = '';
        revokeObjectUrl();
        settle?.(null);
      }
    },
  };
};

/**
 * Creates a latest-only JPEG renderer for a canvas-like element.
 *
 * @param {HTMLCanvasElement|OffscreenCanvas} canvas
 * @param {{onRender?: Function, onError?: Function}} options
 * @returns {{enqueue: Function, close: Function}}
 */
export const createLatestJpegFrameRenderer = (
  canvas,
  { onRender, onError } = {}
) => {
  if (!canvas || typeof canvas.getContext !== 'function') {
    throw new TypeError('A canvas with a 2D context is required');
  }

  const context = canvas.getContext('2d');
  if (!context) {
    throw new Error('Canvas 2D context is unavailable');
  }

  const decodeBitmap = typeof window.createImageBitmap === 'function'
    ? window.createImageBitmap.bind(window)
    : null;
  const ImageConstructor = window.Image;
  const urlApi = window.URL;

  let closed = false;
  let activeTask = null;
  let pendingFrame = null;
  let nextSequence = 0;

  const reportError = (error, metadata) => {
    if (typeof onError === 'function') {
      onError(error, metadata);
    }
  };

  const createDecodeTask = (blob) => {
    if (decodeBitmap) {
      return createBitmapDecodeTask(blob, decodeBitmap);
    }

    if (
      typeof ImageConstructor !== 'function' ||
      typeof urlApi?.createObjectURL !== 'function' ||
      typeof urlApi?.revokeObjectURL !== 'function'
    ) {
      throw new Error('No browser JPEG decoder is available');
    }

    return createImageDecodeTask(blob, ImageConstructor, urlApi);
  };

  const startDecode = (frame) => {
    let task;
    try {
      task = createDecodeTask(frame.blob);
    } catch (error) {
      reportError(error, frame.metadata);
      if (!closed && pendingFrame) {
        const nextFrame = pendingFrame;
        pendingFrame = null;
        startDecode(nextFrame);
      }
      return;
    }

    activeTask = task;
    task.promise
      .then((resource) => {
        if (!resource) {
          return;
        }

        try {
          const newerFrameIsPending =
            pendingFrame && pendingFrame.sequence > frame.sequence;
          if (closed || newerFrameIsPending) {
            return;
          }

          if (canvas.width !== resource.width) {
            canvas.width = resource.width;
          }
          if (canvas.height !== resource.height) {
            canvas.height = resource.height;
          }
          context.clearRect(0, 0, canvas.width, canvas.height);
          context.drawImage(resource.drawable, 0, 0);

          if (typeof onRender === 'function') {
            onRender(frame.metadata);
          }
        } catch (error) {
          reportError(error, frame.metadata);
        } finally {
          resource.dispose();
        }
      })
      .catch((error) => {
        if (!closed) {
          reportError(error, frame.metadata);
        }
      })
      .finally(() => {
        if (activeTask === task) {
          activeTask = null;
        }

        if (!closed && pendingFrame) {
          const nextFrame = pendingFrame;
          pendingFrame = null;
          startDecode(nextFrame);
        }
      });
  };

  return {
    enqueue: (jpegFrame, metadata) => {
      if (closed) {
        return false;
      }

      const frame = {
        blob: toJpegBlob(jpegFrame),
        metadata,
        sequence: ++nextSequence,
      };

      if (activeTask) {
        pendingFrame = frame;
      } else {
        startDecode(frame);
      }

      return true;
    },
    close: () => {
      if (closed) {
        return;
      }

      closed = true;
      pendingFrame = null;
      activeTask?.cancel();
    },
  };
};
