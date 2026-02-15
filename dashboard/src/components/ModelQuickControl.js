// dashboard/src/components/ModelQuickControl.js
/**
 * Compact detection model control for the dashboard status cards row.
 *
 * Features:
 * - Active model name + status chip
 * - Device + backend indicators
 * - Quick model switch dropdown
 * - Link to full Models management page
 *
 * Design: Matches RecordingQuickControl / OSDToggle pattern.
 */

import React, { useState } from 'react';
import {
  Box, Chip, Select, MenuItem, FormControl, InputLabel, IconButton,
  Typography, Tooltip, CircularProgress, Button,
} from '@mui/material';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import MemoryIcon from '@mui/icons-material/Memory';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import { Link } from 'react-router-dom';
import { useActiveModel, useModels, useSwitchModel } from '../hooks/useModels';

const ModelQuickControl = () => {
  const { activeModel, runtime, loading: activeLoading } = useActiveModel(5000);
  const { models, loading: modelsLoading } = useModels(15000);
  const { switchModel, switching } = useSwitchModel();
  const [selectedModelPath, setSelectedModelPath] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('auto');

  // activeModel is the full active_model_summary object from /api/models/active
  const modelName = runtime?.model_name || activeModel?.model_name || 'None';
  const device = runtime?.effective_device || activeModel?.device || null;
  const fallback = runtime?.fallback_occurred || activeModel?.fallback_occurred || false;
  const backend = runtime?.backend || activeModel?.backend || null;
  const task = activeModel?.task || '--';
  const numLabels = activeModel?.num_labels ?? '--';
  const isRunning = runtime != null;
  const hasModel = activeModel != null;

  const modelList = models ? Object.entries(models) : [];

  const handleSwitch = async () => {
    if (!selectedModelPath) return;
    await switchModel(selectedModelPath, selectedDevice);
    setSelectedModelPath('');
  };

  if (activeLoading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', py: 1 }}>
        <CircularProgress size={16} />
      </Box>
    );
  }

  return (
    <Box>
      {/* Status Row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 1, flexWrap: 'wrap' }}>
        <SmartToyIcon sx={{ fontSize: 14, color: hasModel ? 'primary.main' : 'text.disabled' }} />

        <Chip
          label={modelName}
          size="small"
          color={isRunning ? 'primary' : hasModel ? 'default' : 'default'}
          variant={isRunning ? 'filled' : 'outlined'}
          sx={{ fontSize: 10, height: 20, fontWeight: 700, maxWidth: 140 }}
        />

        {device ? (
          <Chip
            label={device.toUpperCase()}
            size="small"
            color={device.startsWith('cuda') ? 'success' : 'default'}
            variant="outlined"
            sx={{ fontSize: 10, height: 20 }}
          />
        ) : (
          <Chip
            label={isRunning ? 'Loading...' : 'Standby'}
            size="small"
            variant="outlined"
            sx={{ fontSize: 10, height: 20, color: 'text.secondary' }}
          />
        )}

        {fallback && (
          <Tooltip title="GPU failed, running on CPU fallback">
            <WarningAmberIcon sx={{ fontSize: 14, color: 'warning.main' }} />
          </Tooltip>
        )}
      </Box>

      {/* Info Row — task, backend, labels */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 1.5, flexWrap: 'wrap' }}>
        {backend && (
          <Chip
            icon={<MemoryIcon sx={{ fontSize: '12px !important' }} />}
            label={backend}
            size="small"
            variant="outlined"
            sx={{ fontSize: 9, height: 18 }}
          />
        )}
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
          Task: <b>{task}</b>
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
          Classes: <b>{numLabels}</b>
        </Typography>
      </Box>

      {/* Quick Switch Row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <FormControl size="small" sx={{ flex: 1, minWidth: 0 }}>
          <InputLabel sx={{ fontSize: 12 }}>Model</InputLabel>
          <Select
            value={selectedModelPath}
            label="Model"
            onChange={(e) => setSelectedModelPath(e.target.value)}
            disabled={modelsLoading || switching}
            sx={{ fontSize: 12, '& .MuiSelect-select': { py: 0.75 } }}
          >
            {modelList.map(([id, info]) => (
              <MenuItem key={id} value={info.path} sx={{ fontSize: 12 }}>
                {info.name || id}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 65 }}>
          <InputLabel sx={{ fontSize: 12 }}>Device</InputLabel>
          <Select
            value={selectedDevice}
            label="Device"
            onChange={(e) => setSelectedDevice(e.target.value)}
            disabled={switching}
            sx={{ fontSize: 12, '& .MuiSelect-select': { py: 0.75 } }}
          >
            <MenuItem value="auto" sx={{ fontSize: 12 }}>Auto</MenuItem>
            <MenuItem value="gpu" sx={{ fontSize: 12 }}>GPU</MenuItem>
            <MenuItem value="cpu" sx={{ fontSize: 12 }}>CPU</MenuItem>
          </Select>
        </FormControl>

        <Tooltip title="Switch model">
          <span>
            <IconButton
              size="small"
              color="primary"
              onClick={handleSwitch}
              disabled={!selectedModelPath || switching}
              sx={{ border: 1, borderColor: 'divider', borderRadius: 1, width: 28, height: 28 }}
            >
              {switching ? <CircularProgress size={14} /> : <SwapHorizIcon sx={{ fontSize: 16 }} />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* Footer: keyboard hint + manage link */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 0.75 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <KeyboardIcon sx={{ fontSize: 12, color: 'text.disabled' }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: 10 }}>
            Press <b>M</b> for smart mode
          </Typography>
        </Box>
        <Tooltip title="Full model management">
          <Typography
            component={Link}
            to="/models"
            variant="caption"
            color="primary"
            sx={{ display: 'flex', alignItems: 'center', gap: 0.3, textDecoration: 'none', fontSize: 10, fontWeight: 600 }}
          >
            Manage <OpenInNewIcon sx={{ fontSize: 10 }} />
          </Typography>
        </Tooltip>
      </Box>
    </Box>
  );
};

export default ModelQuickControl;
