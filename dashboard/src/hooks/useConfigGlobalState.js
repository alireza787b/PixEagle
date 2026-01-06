// dashboard/src/hooks/useConfigGlobalState.js
/**
 * Global configuration state hook for tracking save status across all sections.
 * Provides aggregate state for ConfigStatusBanner and other status indicators.
 *
 * @version 5.4.0
 */

import { useState, useCallback, useEffect, useRef, createContext, useContext } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

// Default context value
const defaultState = {
  totalUnsaved: 0,
  allSaved: true,
  lastSaveTimestamp: null,
  sectionsWithChanges: [],
  unsavedParams: [],
  modifiedFromDefaults: 0,
  saveStatus: 'idle', // 'idle' | 'saving' | 'saved' | 'error'
  lastError: null,
};

// Create context for global config state
const ConfigGlobalStateContext = createContext(defaultState);

/**
 * Context provider component for global config state.
 * Wrap your app or SettingsPage with this provider.
 */
export const ConfigGlobalStateProvider = ({ children }) => {
  const [state, setState] = useState(defaultState);
  const saveTimerRef = useRef(null);

  // Fetch diff from defaults to count modifications
  const fetchModifiedCount = useCallback(async () => {
    try {
      const response = await axios.get(endpoints.configDiff);
      if (response.data.success) {
        return response.data.differences?.length || 0;
      }
    } catch (err) {
      console.warn('Failed to fetch config diff:', err.message);
    }
    return 0;
  }, []);

  // Initialize modified count on mount
  useEffect(() => {
    const init = async () => {
      const count = await fetchModifiedCount();
      setState(prev => ({
        ...prev,
        modifiedFromDefaults: count,
      }));
    };
    init();
  }, [fetchModifiedCount]);

  // Register an unsaved change
  const registerUnsavedChange = useCallback((section, param, oldValue, newValue) => {
    setState(prev => {
      // Check if this param is already tracked
      const existingIdx = prev.unsavedParams.findIndex(
        p => p.section === section && p.param === param
      );

      let updatedParams;
      if (existingIdx >= 0) {
        // Update existing entry
        updatedParams = [...prev.unsavedParams];
        updatedParams[existingIdx] = { section, param, oldValue, newValue };
      } else {
        // Add new entry
        updatedParams = [...prev.unsavedParams, { section, param, oldValue, newValue }];
      }

      // Calculate unique sections with changes
      const sectionsWithChanges = [...new Set(updatedParams.map(p => p.section))];

      return {
        ...prev,
        unsavedParams: updatedParams,
        totalUnsaved: updatedParams.length,
        sectionsWithChanges,
        allSaved: updatedParams.length === 0,
        saveStatus: 'idle',
      };
    });
  }, []);

  // Mark a parameter as saved
  const markParamSaved = useCallback((section, param) => {
    setState(prev => {
      const updatedParams = prev.unsavedParams.filter(
        p => !(p.section === section && p.param === param)
      );
      const sectionsWithChanges = [...new Set(updatedParams.map(p => p.section))];

      return {
        ...prev,
        unsavedParams: updatedParams,
        totalUnsaved: updatedParams.length,
        sectionsWithChanges,
        allSaved: updatedParams.length === 0,
        lastSaveTimestamp: new Date(),
        saveStatus: 'saved',
      };
    });

    // Reset status to idle after 3 seconds
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      setState(prev => ({
        ...prev,
        saveStatus: prev.allSaved ? 'idle' : prev.saveStatus,
      }));
    }, 3000);
  }, []);

  // Mark section as saving
  const markSectionSaving = useCallback((section) => {
    setState(prev => ({
      ...prev,
      saveStatus: 'saving',
    }));
  }, []);

  // Mark save error
  const markSaveError = useCallback((section, param, error) => {
    setState(prev => ({
      ...prev,
      saveStatus: 'error',
      lastError: { section, param, error, timestamp: new Date() },
    }));
  }, []);

  // Clear all unsaved for a section (e.g., after revert)
  const clearSectionChanges = useCallback((section) => {
    setState(prev => {
      const updatedParams = prev.unsavedParams.filter(p => p.section !== section);
      const sectionsWithChanges = [...new Set(updatedParams.map(p => p.section))];

      return {
        ...prev,
        unsavedParams: updatedParams,
        totalUnsaved: updatedParams.length,
        sectionsWithChanges,
        allSaved: updatedParams.length === 0,
      };
    });
  }, []);

  // Refresh modified count (after import, restore, etc.)
  const refreshModifiedCount = useCallback(async () => {
    const count = await fetchModifiedCount();
    setState(prev => ({
      ...prev,
      modifiedFromDefaults: count,
    }));
    return count;
  }, [fetchModifiedCount]);

  // Reset all state (e.g., on page unmount)
  const reset = useCallback(() => {
    setState(defaultState);
  }, []);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const value = {
    ...state,
    registerUnsavedChange,
    markParamSaved,
    markSectionSaving,
    markSaveError,
    clearSectionChanges,
    refreshModifiedCount,
    reset,
  };

  return (
    <ConfigGlobalStateContext.Provider value={value}>
      {children}
    </ConfigGlobalStateContext.Provider>
  );
};

/**
 * Hook to access global config state.
 *
 * @returns {Object} Global config state and actions
 * @returns {number} return.totalUnsaved - Count of unsaved parameter changes
 * @returns {boolean} return.allSaved - True if all changes are saved
 * @returns {Date|null} return.lastSaveTimestamp - Timestamp of last successful save
 * @returns {string[]} return.sectionsWithChanges - Array of section names with unsaved changes
 * @returns {Array} return.unsavedParams - Array of {section, param, oldValue, newValue}
 * @returns {number} return.modifiedFromDefaults - Count of params differing from defaults
 * @returns {string} return.saveStatus - 'idle' | 'saving' | 'saved' | 'error'
 * @returns {Object|null} return.lastError - Last save error details
 * @returns {Function} return.registerUnsavedChange - Register a local unsaved change
 * @returns {Function} return.markParamSaved - Mark a parameter as successfully saved
 * @returns {Function} return.markSectionSaving - Mark section as currently saving
 * @returns {Function} return.markSaveError - Register a save error
 * @returns {Function} return.clearSectionChanges - Clear all unsaved changes for a section
 * @returns {Function} return.refreshModifiedCount - Refresh count of params modified from defaults
 * @returns {Function} return.reset - Reset all state to defaults
 *
 * @example
 * const { totalUnsaved, allSaved, lastSaveTimestamp } = useConfigGlobalState();
 */
export const useConfigGlobalState = () => {
  const context = useContext(ConfigGlobalStateContext);
  if (!context) {
    // Return a minimal working state if used outside provider
    console.warn('useConfigGlobalState used outside of ConfigGlobalStateProvider');
    return {
      ...defaultState,
      registerUnsavedChange: () => {},
      markParamSaved: () => {},
      markSectionSaving: () => {},
      markSaveError: () => {},
      clearSectionChanges: () => {},
      refreshModifiedCount: async () => 0,
      reset: () => {},
    };
  }
  return context;
};

/**
 * Format last save timestamp as relative time string.
 *
 * @param {Date|null} timestamp - The timestamp to format
 * @returns {string} Formatted relative time (e.g., "2 min ago", "Just now")
 */
export const formatRelativeTime = (timestamp) => {
  if (!timestamp) return 'Never';

  const now = new Date();
  const diff = Math.floor((now - timestamp) / 1000);

  if (diff < 5) return 'Just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return timestamp.toLocaleDateString();
};

export default useConfigGlobalState;
