import { useCallback, useEffect, useRef, useState } from 'react';

// Held intent is renewed only while this gesture owns the pointer/key. Older
// providers retain their completed, server-bounded step behavior.
export default function useGimbalHold(control, parametersFor) {
  const latest = useRef({ control, parametersFor });
  latest.current = { control, parametersFor };
  const gesture = useRef(null);
  const suppressedClick = useRef(false);
  const [activeKey, setActiveKey] = useState(null);

  const stop = useCallback((held) => {
    const current = latest.current.control;
    const parameters = {
      ...(held.parameters.camera_context ? { camera_context: held.parameters.camera_context } : {}),
      ...(held.manual ? { gesture_id: held.id, sequence: ++held.sequence } : {}),
    };
    if (current.canOperate('stop')) {
      const request = held.manual
        ? current.execute('stop', parameters, { preserveError: true })
        : current.execute('stop', parameters);
      return request.catch(() => false);
    }
  }, []);

  const finish = useCallback((abort = false, requestStop = true) => {
    const held = gesture.current;
    if (!held) return;
    gesture.current = null;
    held.released = true;
    cancelAnimationFrame(held.frame);
    clearInterval(held.timer);
    setActiveKey(null);
    if (held.element?.hasPointerCapture?.(held.pointerId)) {
      held.element.releasePointerCapture(held.pointerId);
    }
    // Lease gestures always release immediately. Legacy quick taps finish their
    // bounded step; repetitions and interruptions request Stop.
    if (requestStop && (held.manual || abort || held.steps > 1)) return stop(held);
  }, [stop]);

  const start = (operation, direction, input = {}) => {
    if (gesture.current || !control.canOperate(operation)) return;
    const held = { operation, direction, ...input, steps: 0, released: false,
      parameters: parametersFor(operation, direction),
      manual: control.status.capabilities?.includes('manual_begin')
        && control.status.capabilities?.includes('manual_update'),
      id: window.crypto?.randomUUID?.() || `gesture-${Date.now()}-${Math.random()}`,
      sequence: 0, pending: false };
    gesture.current = held;
    setActiveKey(`${operation}:${direction}`);
    const isCurrent = () => gesture.current === held && !held.released;
    const renew = async (begin = false) => {
      if (!isCurrent() || held.pending) return;
      const current = latest.current.control;
      const action = begin ? 'manual_begin' : 'manual_update';
      if (!current.canOperate(action)) { finish(true); return; }
      held.pending = true;
      const maximumSpeed = current.status.motion_settings?.max_speed_deg_s;
      const speed = held.parameters.speed_deg_s;
      const magnitude = operation !== 'zoom' && maximumSpeed && speed
        ? Math.min(1, speed / maximumSpeed) : 1;
      try {
        const result = await current.execute(action, {
          camera_context: held.parameters.camera_context,
          gesture_id: held.id, sequence: begin ? 0 : ++held.sequence,
          intent: { axis: operation, value: direction * magnitude },
        }, { isCurrent });
        if (!isCurrent()) return;
        if (['stopped', 'expired', 'failed'].includes(result?.result?.manual?.state)) {
          finish(true);
          return;
        }
      } catch {
        if (isCurrent()) finish(true);
      } finally {
        held.pending = false;
      }
      if (begin && isCurrent()) {
        // Begin establishes ownership only; renewed intent authorizes motion.
        held.timer = setInterval(() => { void renew(); }, 100);
        void renew();
      }
    };
    if (held.manual) { void renew(true); return; }
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
      || !control.canOperate('stop') || !control.status.capabilities?.includes(held.operation)
      || (held.parameters.camera_context && (held.parameters.camera_context.guard.camera_id !== control.status.guard?.camera_id
        || held.parameters.camera_context.guard.source_epoch !== control.status.guard?.source_epoch
        || held.parameters.camera_context.guard.camera_generation !== control.status.guard?.camera_generation)))) finish(true);
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
