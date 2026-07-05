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
import { apiFetch } from '../services/apiClient';

const DEFAULT_PRESETS = ['minimal', 'professional', 'military', 'full_telemetry', 'debug'];
const DEFAULT_COLOR_MODES = ['day', 'night', 'amber'];
const STATUS_POLL_INTERVAL_MS = 2000;
const NO_STORE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};

export const cleanOsdChoice = (value) => {
  const cleaned = String(value ?? '').trim();
  return cleaned || null;
};

const normalizeChoiceList = (values, fallbackValues) => {
  if (!Array.isArray(values)) {
    return fallbackValues;
  }

  const seen = new Set();
  const cleanedValues = [];
  values.forEach((value) => {
    const cleaned = cleanOsdChoice(value);
    if (!cleaned || seen.has(cleaned)) {
      return;
    }
    seen.add(cleaned);
    cleanedValues.push(cleaned);
  });

  return cleanedValues.length > 0 ? cleanedValues : fallbackValues;
};

export const normalizePresets = (presets) => normalizeChoiceList(presets, DEFAULT_PRESETS);

export const normalizeColorModes = (modes) => normalizeChoiceList(modes, DEFAULT_COLOR_MODES);

export const formatOsdChoiceLabel = (value) => {
  const cleaned = cleanOsdChoice(value);
  if (!cleaned) {
    return 'Unknown';
  }
  return cleaned
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const extractPresetFromStatus = (statusPayload) => (
  statusPayload?.configuration?.current_preset
  || statusPayload?.current_preset
  || statusPayload?.preset
  || null
);

const fetchJsonNoStore = async (url, options = {}) => {
  const { headers = {}, ...rest } = options;
  const response = await apiFetch(url, {
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
  const [missingPreset, setMissingPreset] = useState(null);
  const [currentColorMode, setCurrentColorMode] = useState('day');
  const [availableColorModes, setAvailableColorModes] = useState(DEFAULT_COLOR_MODES);
  const [missingColorMode, setMissingColorMode] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [toggleLoading, setToggleLoading] = useState(false);
  const [presetLoading, setPresetLoading] = useState(false);
  const [colorModeLoading, setColorModeLoading] = useState(false);
  const [error, setError] = useState(null);

  const currentPresetRef = useRef('professional');
  const availablePresetsRef = useRef(DEFAULT_PRESETS);
  const currentColorModeRef = useRef('day');
  const availableColorModesRef = useRef(DEFAULT_COLOR_MODES);
  const statusRequestRef = useRef(0);
  const presetsRequestRef = useRef(0);

  useEffect(() => {
    currentPresetRef.current = currentPreset;
  }, [currentPreset]);

  useEffect(() => {
    availablePresetsRef.current = availablePresets;
  }, [availablePresets]);

  useEffect(() => {
    currentColorModeRef.current = currentColorMode;
  }, [currentColorMode]);

  useEffect(() => {
    availableColorModesRef.current = availableColorModes;
  }, [availableColorModes]);

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
      const [statusData, presetsData, colorModesData] = await Promise.all([
        fetchJsonNoStore(endpoints.osdStatus),
        includePresets ? fetchJsonNoStore(endpoints.osdPresets) : Promise.resolve(null),
        includePresets
          ? fetchJsonNoStore(endpoints.osdColorModes).catch(() => null)
          : Promise.resolve(null),
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

      const statusPreset = cleanOsdChoice(extractPresetFromStatus(statusData));
      const presetFromPresetsApi = cleanOsdChoice(presetsData?.current);
      const fallbackPreset = resolvedPresets[0] || 'professional';
      const resolvedPreset = statusPreset
        || presetFromPresetsApi
        || cleanOsdChoice(currentPresetRef.current)
        || fallbackPreset;

      setMissingPreset(
        resolvedPreset && !resolvedPresets.includes(resolvedPreset)
          ? resolvedPreset
          : null
      );

      setCurrentPreset(resolvedPreset);
      currentPresetRef.current = resolvedPreset;
      setOsdEnabled(Boolean(statusData?.enabled));

      let resolvedColorModes = availableColorModesRef.current;
      if (includePresets) {
        resolvedColorModes = normalizeColorModes(colorModesData?.available_modes);
        setAvailableColorModes(resolvedColorModes);
        availableColorModesRef.current = resolvedColorModes;
      }

      const statusColorMode = cleanOsdChoice(
        statusData?.configuration?.color_mode || statusData?.color_mode
      );
      const colorModeFromApi = cleanOsdChoice(colorModesData?.current);
      const fallbackColorMode = resolvedColorModes[0] || 'day';
      const resolvedColorMode = statusColorMode
        || colorModeFromApi
        || cleanOsdChoice(currentColorModeRef.current)
        || fallbackColorMode;

      setMissingColorMode(
        resolvedColorMode && !resolvedColorModes.includes(resolvedColorMode)
          ? resolvedColorMode
          : null
      );
      setCurrentColorMode(resolvedColorMode);
      currentColorModeRef.current = resolvedColorMode;

      setError(null);

      return {
        enabled: Boolean(statusData?.enabled),
        preset: resolvedPreset,
        colorMode: resolvedColorMode,
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
          {missingPreset && (
            <MenuItem key={`missing-${missingPreset}`} value={missingPreset} disabled>
              <Tooltip title="The backend reports this preset, but it is not in the current preset catalog." placement="right" arrow>
                <Box sx={{ width: '100%' }}>
                  Missing preset: {formatOsdChoiceLabel(missingPreset)}
                </Box>
              </Tooltip>
            </MenuItem>
          )}
          {availablePresets.map((preset) => {
            const presetName = String(preset);
            const displayName = formatOsdChoiceLabel(presetName);

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
          {missingColorMode && (
            <MenuItem key={`missing-${missingColorMode}`} value={missingColorMode} disabled>
              <Tooltip title="The backend reports this color mode, but it is not in the current mode catalog." placement="right" arrow>
                <Box sx={{ width: '100%' }}>
                  Missing color: {formatOsdChoiceLabel(missingColorMode)}
                </Box>
              </Tooltip>
            </MenuItem>
          )}
          {availableColorModes.map((mode) => {
            const displayName = formatOsdChoiceLabel(mode);

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
          {missingPreset ? 'Preset missing' : 'Preset'}: {formatOsdChoiceLabel(currentPreset)}
          {' | '}
          {missingColorMode ? 'Color missing' : 'Color'}: {formatOsdChoiceLabel(currentColorMode)}
        </Typography>
      )}
    </Box>
  );
};

export default OSDToggle;
