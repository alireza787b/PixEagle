import { useCallback, useEffect, useRef, useState } from 'react';

// Repeats completed, server-bounded steps. Never queue a second movement request.
export default function useGimbalHold(control, parametersFor) {
  const latest = useRef({ control, parametersFor });
  latest.current = { control, parametersFor };
  const gesture = useRef(null);
  const suppressedClick = useRef(false);
  const [activeKey, setActiveKey] = useState(null);

  const stop = useCallback(() => {
    const current = latest.current.control;
    if (current.canOperate('stop')) void current.execute('stop', {}).catch(() => {});
  }, []);

  const finish = useCallback((abort = false, requestStop = true) => {
    const held = gesture.current;
    if (!held) return;
    gesture.current = null;
    held.released = true;
    cancelAnimationFrame(held.frame);
    setActiveKey(null);
    if (held.element?.hasPointerCapture?.(held.pointerId)) {
      held.element.releasePointerCapture(held.pointerId);
    }
    // A quick tap completes one step. A repeat/abort requests Stop; every
    // in-flight step also stops itself server-side even if requests cross.
    if (requestStop && (abort || held.steps > 1)) stop();
  }, [stop]);

  const start = (operation, direction, input = {}) => {
    if (gesture.current || !control.canOperate(operation)) return;
    const held = { operation, direction, ...input, steps: 0, released: false,
      parameters: parametersFor(operation, direction) };
    gesture.current = held;
    setActiveKey(`${operation}:${direction}`);
    const pulse = async () => {
      if (held.released) return;
      const current = latest.current.control;
      if (!current.canOperate(operation)) { finish(true); return; }
      held.steps += 1;
      try {
        await current.execute(operation, held.parameters);
      } catch {
        if (!held.released) finish(true);
        return;
      }
      // The next animation frame lets React publish the cleared busy guard.
      if (!held.released) held.frame = requestAnimationFrame(pulse);
    };
    void pulse();
  };

  useEffect(() => {
    const abort = () => finish(true);
    const hidden = () => { if (document.hidden) abort(); };
    window.addEventListener('blur', abort);
    document.addEventListener('visibilitychange', hidden);
    return () => {
      window.removeEventListener('blur', abort);
      document.removeEventListener('visibilitychange', hidden);
      abort();
    };
  }, [finish]);

  useEffect(() => {
    const held = gesture.current;
    if (held && (!control.enabled || !control.status.connected
      || control.status.available === false || control.status.following_active === true
      || !control.canOperate('stop') || !control.status.capabilities?.includes(held.operation))) finish(true);
  }, [control, finish]);

  const handlers = (operation, direction) => ({
    onPointerDown: event => {
      if (event.isPrimary === false || event.button !== 0) return;
      event.preventDefault();
      suppressedClick.current = true;
      const element = event.currentTarget;
      element.setPointerCapture?.(event.pointerId);
      start(operation, direction, { element, pointerId: event.pointerId });
    },
    onPointerUp: event => {
      if (gesture.current?.pointerId === event.pointerId) finish();
    },
    onPointerCancel: event => {
      if (gesture.current?.pointerId === event.pointerId) finish(true);
    },
    onLostPointerCapture: event => {
      if (gesture.current?.pointerId === event.pointerId) finish(true);
    },
    onContextMenu: event => event.preventDefault(),
    onKeyDown: event => {
      if (![' ', 'Enter'].includes(event.key)) return;
      event.preventDefault();
      if (!event.repeat) start(operation, direction, { key: event.key });
    },
    onKeyUp: event => {
      if (gesture.current?.key === event.key) { event.preventDefault(); finish(); }
    },
    onBlur: () => finish(true),
    onClick: event => {
      if (event.detail > 0 && suppressedClick.current) {
        suppressedClick.current = false;
        return;
      }
      // Keyboard/assistive clicks without a preceding held key remain one step.
      void latest.current.control.execute(operation, parametersFor(operation, direction)).catch(() => {});
    },
  });
  return { activeKey, handlers, abort: (requestStop = true) => finish(true, requestStop) };
}
