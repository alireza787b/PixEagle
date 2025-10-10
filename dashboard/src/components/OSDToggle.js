// dashboard/src/components/OSDToggle.js
import React, { useState, useEffect } from 'react';
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

/**
 * OSDToggle Component
 *
 * Professional OSD control component with enable/disable toggle and preset selection.
 * Follows PixEagle dashboard design standards (similar to TrackerModeToggle).
 *
 * Features:
 * - Toggle OSD on/off
 * - Select from available presets (minimal, professional, full_telemetry)
 * - Real-time status updates
 * - Error handling with user feedback
 * - Tooltip with preset descriptions
 */
const OSDToggle = () => {
  const [osdEnabled, setOsdEnabled] = useState(false);
  const [currentPreset, setCurrentPreset] = useState('professional');
  const [availablePresets, setAvailablePresets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [presetLoading, setPresetLoading] = useState(false);

  // Preset descriptions for tooltips
  const presetDescriptions = {
    minimal: 'Racing/FPV - Minimal distraction with only essential data (6 elements)',
    professional: 'Default - Balanced layout for general operations (15-18 elements)',
    full_telemetry: 'Debugging - Maximum telemetry data for analysis (25+ elements)',
  };

  // Fetch OSD status on component mount
  useEffect(() => {
    fetchOSDStatus();
    fetchAvailablePresets();
  }, []);

  /**
   * Fetch current OSD status from backend
   */
  const fetchOSDStatus = async () => {
    try {
      const response = await fetch(endpoints.osdStatus);
      if (response.ok) {
        const data = await response.json();
        setOsdEnabled(data.enabled || false);
        setCurrentPreset(data.preset || 'professional');
      }
    } catch (err) {
      console.error('Failed to fetch OSD status:', err);
      setError('Failed to fetch OSD status');
    }
  };

  /**
   * Fetch available OSD presets from backend
   */
  const fetchAvailablePresets = async () => {
    try {
      const response = await fetch(endpoints.osdPresets);
      if (response.ok) {
        const data = await response.json();
        setAvailablePresets(data.presets || ['minimal', 'professional', 'full_telemetry']);
        setCurrentPreset(data.current || 'professional');
      }
    } catch (err) {
      console.error('Failed to fetch OSD presets:', err);
      // Use default presets if fetch fails
      setAvailablePresets(['minimal', 'professional', 'full_telemetry']);
    }
  };

  /**
   * Toggle OSD enable/disable
   */
  const handleToggle = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(endpoints.toggleOsd, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json();
        setOsdEnabled(data.enabled);
      } else {
        throw new Error('Failed to toggle OSD');
      }
    } catch (err) {
      console.error('Failed to toggle OSD:', err);
      setError('Failed to toggle OSD. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Change OSD preset
   */
  const handlePresetChange = async (event) => {
    const newPreset = event.target.value;
    setPresetLoading(true);
    setError(null);

    try {
      const response = await fetch(endpoints.loadOsdPreset(newPreset), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json();
        setCurrentPreset(newPreset);

        // If OSD was disabled, enable it when changing preset
        if (!osdEnabled && data.status === 'success') {
          setOsdEnabled(true);
        }
      } else {
        throw new Error('Failed to load preset');
      }
    } catch (err) {
      console.error('Failed to change OSD preset:', err);
      setError('Failed to load preset. Please try again.');
    } finally {
      setPresetLoading(false);
    }
  };

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
            disabled={loading}
            color="primary"
          />
        }
        label={
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            {loading && <CircularProgress size={16} sx={{ mr: 1 }} />}
            {osdEnabled ? 'OSD Enabled' : 'OSD Disabled'}
          </Box>
        }
      />

      {/* Preset Selector */}
      <FormControl fullWidth sx={{ mt: 2 }} disabled={!osdEnabled || presetLoading}>
        <InputLabel id="osd-preset-label">OSD Preset</InputLabel>
        <Select
          labelId="osd-preset-label"
          id="osd-preset-select"
          value={currentPreset}
          label="OSD Preset"
          onChange={handlePresetChange}
        >
          {availablePresets.map((preset) => {
            // Ensure preset is a string
            const presetName = typeof preset === 'string' ? preset : String(preset);
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

      {/* Current status display */}
      {osdEnabled && currentPreset && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Active: {String(currentPreset).charAt(0).toUpperCase() + String(currentPreset).slice(1).replace('_', ' ')}
        </Typography>
      )}
    </Box>
  );
};

export default OSDToggle;
