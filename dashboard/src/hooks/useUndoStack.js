// dashboard/src/hooks/useUndoStack.js
import { useState, useCallback, useMemo } from 'react';

/**
 * useUndoStack - Hook for managing undo/redo history
 *
 * Provides local undo/redo capability for value editing before save.
 * Useful for complex value editors where users might make mistakes.
 *
 * @param {any} initialValue - Starting value
 * @param {number} maxHistory - Maximum history entries (default 20)
 */
export function useUndoStack(initialValue, maxHistory = 20) {
  // History is an array of value snapshots
  const [history, setHistory] = useState([initialValue]);
  // Current position in history (0 = most recent state pushed)
  const [index, setIndex] = useState(0);

  // Current value is derived from history and index
  const value = useMemo(() => history[index], [history, index]);

  // Push a new value to history
  const push = useCallback((newValue) => {
    setHistory(prev => {
      // Remove any "future" entries if we're not at the end
      const newHistory = prev.slice(index);
      // Add new value at the beginning
      newHistory.unshift(newValue);
      // Trim to max history
      if (newHistory.length > maxHistory) {
        newHistory.pop();
      }
      return newHistory;
    });
    setIndex(0); // Reset to newest entry
  }, [index, maxHistory]);

  // Undo - go back in history
  const undo = useCallback(() => {
    setIndex(prev => Math.min(prev + 1, history.length - 1));
  }, [history.length]);

  // Redo - go forward in history
  const redo = useCallback(() => {
    setIndex(prev => Math.max(prev - 1, 0));
  }, []);

  // Reset to a specific value (clears history)
  const reset = useCallback((newValue) => {
    setHistory([newValue]);
    setIndex(0);
  }, []);

  // Reset to initial value
  const resetToInitial = useCallback(() => {
    reset(initialValue);
  }, [initialValue, reset]);

  // Check capabilities
  const canUndo = index < history.length - 1;
  const canRedo = index > 0;
  const hasChanges = history.length > 1 || index > 0;

  // Get history info for debugging/display
  const historyInfo = useMemo(() => ({
    length: history.length,
    position: index + 1,
    total: history.length
  }), [history.length, index]);

  return {
    value,
    push,
    undo,
    redo,
    reset,
    resetToInitial,
    canUndo,
    canRedo,
    hasChanges,
    historyInfo
  };
}

export default useUndoStack;
