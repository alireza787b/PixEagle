// dashboard/src/components/OSDToggle.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Switch,
  FormControlLabel,
  Typography,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Alert,
  Tooltip,
  IconButton,
} from '@mui/material';
import InfoIcon from '@mui/icons-material/Info';
import { endpoints } from '../services/apiEndpoints';

const DEFAULT_PRESETS = ['minimal', 'professional', 'military', 'full_telemetry', 'debug'];
const DEFAULT_COLOR_MODES = ['day', 'night', 'amber'];
const STATUS_POLL_INTERVAL_MS = 2000;
const NO_STORE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

const normalizePresets = (presets) => {
  if (!Array.isArray(presets)) {
    return DEFAULT_PRESETS;
  }

  const cleanedPresets = presets
    .map((preset) => String(preset).trim())
    .filter(Boolean);

  return cleanedPresets.length > 0 ? cleanedPresets : DEFAULT_PRESETS;
};

const extractPresetFromStatus = (statusPayload) => (
  statusPayload?.configuration?.current_preset
  || statusPayload?.current_preset
  || statusPayload?.preset
  || null
);

const fetchJsonNoStore = async (url, options = {}) => {
  const { headers = {}, ...rest } = options;
  const response = await fetch(url, {
    cache: 'no-store',
    ...rest,
    headers: {
      ...NO_STORE_HEADERS,
      ...headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`);
  }

  return response.json();
};

/**
 * OSDToggle Component
 *
 * Server-synced OSD control with resilient state reconciliation.
 * Backend state is the source of truth for both enable/disable and preset selection.
 */
const OSDToggle = () => {
  const [osdEnabled, setOsdEnabled] = useState(false);
  const [currentPreset, setCurrentPreset] = useState('professional');
  const [availablePresets, setAvailablePresets] = useState(DEFAULT_PRESETS);
  const [currentColorMode, setCurrentColorMode] = useState('day');
  const [initialLoading, setInitialLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [toggleLoading, setToggleLoading] = useState(false);
  const [presetLoading, setPresetLoading] = useState(false);
  const [colorModeLoading, setColorModeLoading] = useState(false);
  const [error, setError] = useState(null);

  const currentPresetRef = useRef('professional');
  const availablePresetsRef = useRef(DEFAULT_PRESETS);
  const statusRequestRef = useRef(0);
  const presetsRequestRef = useRef(0);

  useEffect(() => {
    currentPresetRef.current = currentPreset;
  }, [currentPreset]);

  useEffect(() => {
    availablePresetsRef.current = availablePresets;
  }, [availablePresets]);

  // Preset descriptions for tooltips
  const presetDescriptions = {
    minimal: 'Racing/FPV - Minimal distraction with only essential data',
    professional: 'Default - Balanced aviation-grade layout',
    military: 'Tactical - MIL-STD inspired defense HUD',
    full_telemetry: 'Analysis - Maximum telemetry data density',
    debug: 'Engineering - All fields + debug info',
  };

  // Color mode descriptions
  const colorModeDescriptions = {
    day: 'Green phosphor - Standard daylight operations',
    night: 'NVIS compatible - Night vision safe (dim green)',
    amber: 'Amber HUD - A-10/Apache style warm tones',
  };

  const syncState = useCallback(async ({ includePresets = false, silent = false, suppressError = false } = {}) => {
    const statusRequestId = ++statusRequestRef.current;
    const presetsRequestId = includePresets ? ++presetsRequestRef.current : null;

    if (!silent) {
      setSyncing(true);
    }

    try {
      const [statusData, presetsData] = await Promise.all([
        fetchJsonNoStore(endpoints.osdStatus),
        includePresets ? fetchJsonNoStore(endpoints.osdPresets) : Promise.resolve(null),
      ]);

      if (statusRequestId !== statusRequestRef.current) {
        return null;
      }
      if (includePresets && presetsRequestId !== presetsRequestRef.current) {
        return null;
      }

      let resolvedPresets = availablePresetsRef.current;
      if (includePresets) {
        resolvedPresets = normalizePresets(presetsData?.presets);
        setAvailablePresets(resolvedPresets);
        availablePresetsRef.current = resolvedPresets;
      }

      const statusPreset = extractPresetFromStatus(statusData);
      const presetFromPresetsApi = presetsData?.current ? String(presetsData.current) : null;
      const fallbackPreset = resolvedPresets[0] || 'professional';
      const resolvedPreset = statusPreset || presetFromPresetsApi || currentPresetRef.current || fallbackPreset;

      if (resolvedPreset && !resolvedPresets.includes(resolvedPreset)) {
        resolvedPresets = [...resolvedPresets, resolvedPreset];
        setAvailablePresets(resolvedPresets);
        availablePresetsRef.current = resolvedPresets;
      }

      setCurrentPreset(resolvedPreset);
      currentPresetRef.current = resolvedPreset;
      setOsdEnabled(Boolean(statusData?.enabled));

      // Sync color mode from status
      const colorMode = statusData?.configuration?.color_mode || 'day';
      setCurrentColorMode(colorMode);

      setError(null);

      return {
        enabled: Boolean(statusData?.enabled),
        preset: resolvedPreset,
        colorMode,
      };
    } catch (syncError) {
      if (!suppressError) {
        console.error('Failed to sync OSD state:', syncError);
        setError('Failed to sync OSD status');
      }
      return null;
    } finally {
      if (!silent) {
        setSyncing(false);
      }
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const initialize = async () => {
      await syncState({ includePresets: true });
      if (mounted) {
        setInitialLoading(false);
      }
    };

    initialize();

    const pollStatus = () => {
      syncState({ silent: true, suppressError: true });
    };

    const intervalId = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) {
        return;
      }
      pollStatus();
    }, STATUS_POLL_INTERVAL_MS);

    const handleVisibilityChange = () => {
      if (typeof document !== 'undefined' && !document.hidden) {
        pollStatus();
      }
    };

    const handleWindowFocus = () => {
      pollStatus();
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', handleWindowFocus);
    }

    return () => {
      mounted = false;
      clearInterval(intervalId);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
      if (typeof window !== 'undefined') {
        window.removeEventListener('focus', handleWindowFocus);
      }
    };
  }, [syncState]);

  /**
   * Toggle OSD enable/disable and reconcile with backend status.
   */
  const handleToggle = async () => {
    if (toggleLoading || presetLoading) {
      return;
    }

    setToggleLoading(true);
    setError(null);

    try {
      await fetchJsonNoStore(endpoints.toggleOsd, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      await syncState({ silent: true, suppressError: true });
    } catch (toggleError) {
      console.error('Failed to toggle OSD:', toggleError);
      setError('Failed to toggle OSD. Please try again.');
      await syncState({ silent: true, suppressError: true });
    } finally {
      setToggleLoading(false);
    }
  };

  /**
   * Change OSD preset and reconcile with backend status.
   */
  const handlePresetChange = async (event) => {
    const newPreset = String(event.target.value);
    setPresetLoading(true);
    setError(null);

    try {
      await fetchJsonNoStore(endpoints.loadOsdPreset(newPreset), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      await syncState({ includePresets: true, silent: true, suppressError: true });
    } catch (presetError) {
      console.error('Failed to change OSD preset:', presetError);
      setError('Failed to load preset. Please try again.');
      await syncState({ silent: true, suppressError: true });
    } finally {
      setPresetLoading(false);
    }
  };

  /**
   * Change OSD color mode and reconcile with backend status.
   */
  const handleColorModeChange = async (event) => {
    const newMode = String(event.target.value);
    setColorModeLoading(true);
    setError(null);

    try {
      await fetchJsonNoStore(endpoints.setOsdColorMode(newMode), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      await syncState({ silent: true, suppressError: true });
    } catch (colorError) {
      console.error('Failed to change color mode:', colorError);
      setError('Failed to switch color mode. Please try again.');
      await syncState({ silent: true, suppressError: true });
    } finally {
      setColorModeLoading(false);
    }
  };

  const switchBusy = initialLoading || toggleLoading || syncing;

  return (
    <Box sx={{ mt: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        <Typography variant="h6" gutterBottom sx={{ mb: 0 }}>
          OSD (On-Screen Display)
        </Typography>
        <Tooltip
          title="Professional OSD system with high-quality text rendering and multiple presets. See docs/OSD_GUIDE.md for details."
          arrow
        >
          <IconButton size="small" sx={{ ml: 1 }}>
            <InfoIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* OSD Enable/Disable Toggle */}
      <FormControlLabel
        control={
          <Switch
            checked={osdEnabled}
            onChange={handleToggle}
            disabled={switchBusy || presetLoading}
            color="primary"
          />
        }
        label={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {switchBusy && <CircularProgress size={16} sx={{ mr: 1 }} />}
            {osdEnabled ? 'OSD Enabled' : 'OSD Disabled'}
          </Box>
        }
      />

      {/* Preset Selector */}
      <FormControl fullWidth sx={{ mt: 2 }} disabled={!osdEnabled || presetLoading || initialLoading}>
        <InputLabel id="osd-preset-label">OSD Preset</InputLabel>
        <Select
          labelId="osd-preset-label"
          id="osd-preset-select"
          value={currentPreset}
          label="OSD Preset"
          onChange={handlePresetChange}
        >
          {availablePresets.map((preset) => {
            const presetName = String(preset);
            const displayName = presetName.charAt(0).toUpperCase() + presetName.slice(1).replace('_', ' ');

            return (
              <MenuItem key={presetName} value={presetName}>
                <Tooltip title={presetDescriptions[presetName] || ''} placement="right" arrow>
                  <Box sx={{ width: '100%' }}>
                    {displayName}
                    {presetName === 'professional' && ' ⭐'}
                  </Box>
                </Tooltip>
              </MenuItem>
            );
          })}
        </Select>
      </FormControl>

      {/* Preset loading indicator */}
      {presetLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
          <CircularProgress size={16} sx={{ mr: 1 }} />
          <Typography variant="caption" color="text.secondary">
            Loading preset...
          </Typography>
        </Box>
      )}

      {/* Color Mode Selector */}
      <FormControl fullWidth sx={{ mt: 2 }} disabled={!osdEnabled || colorModeLoading || initialLoading}>
        <InputLabel id="osd-color-mode-label">Color Mode</InputLabel>
        <Select
          labelId="osd-color-mode-label"
          id="osd-color-mode-select"
          value={currentColorMode}
          label="Color Mode"
          onChange={handleColorModeChange}
        >
          {DEFAULT_COLOR_MODES.map((mode) => {
            const displayName = mode.charAt(0).toUpperCase() + mode.slice(1);

            return (
              <MenuItem key={mode} value={mode}>
                <Tooltip title={colorModeDescriptions[mode] || ''} placement="right" arrow>
                  <Box sx={{ width: '100%' }}>
                    {displayName}
                    {mode === 'day' && ' (Default)'}
                  </Box>
                </Tooltip>
              </MenuItem>
            );
          })}
        </Select>
      </FormControl>

      {/* Color mode loading indicator */}
      {colorModeLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
          <CircularProgress size={16} sx={{ mr: 1 }} />
          <Typography variant="caption" color="text.secondary">
            Switching color mode...
          </Typography>
        </Box>
      )}

      {/* Current status display */}
      {currentPreset && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Preset: {currentPreset.charAt(0).toUpperCase() + currentPreset.slice(1).replace('_', ' ')}
          {' | '}Color: {currentColorMode.charAt(0).toUpperCase() + currentColorMode.slice(1)}
        </Typography>
      )}
    </Box>
  );
};

export default OSDToggle;
