// dashboard/src/components/ModelQuickControl.js
import React, { useState } from 'react';
import {
  Box, Chip, Select, MenuItem, FormControl, InputLabel, IconButton,
  Typography, Tooltip, CircularProgress,
} from '@mui/material';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { Link } from 'react-router-dom';
import { useActiveModel } from '../hooks/useModels';
import { useModels, useSwitchModel } from '../hooks/useModels';

const ModelQuickControl = () => {
  const { activeModel, runtime, loading: activeLoading } = useActiveModel(5000);
  const { models, loading: modelsLoading } = useModels(15000);
  const { switchModel, switching } = useSwitchModel();
  const [selectedModelPath, setSelectedModelPath] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('auto');

  const modelName = runtime?.model_name || activeModel || 'None';
  const device = runtime?.effective_device || 'unknown';
  const fallback = runtime?.fallback_occurred || false;
  const backend = runtime?.backend || '';

  const modelList = models ? Object.entries(models) : [];

  const handleSwitch = async () => {
    if (!selectedModelPath) return;
    await switchModel(selectedModelPath, selectedDevice);
    setSelectedModelPath('');
  };

  if (activeLoading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1 }}>
        <CircularProgress size={16} />
        <Typography variant="body2" color="text.secondary">Loading model status...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      {/* Status Row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <SmartToyIcon fontSize="small" color="primary" />
        <Chip label={modelName} size="small" color="primary" variant="outlined" />
        <Chip
          label={device.toUpperCase()}
          size="small"
          color={device.startsWith('cuda') ? 'success' : 'default'}
          variant="filled"
        />
        {backend && (
          <Chip label={backend} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
        )}
        {fallback && (
          <Tooltip title="GPU failed, running on CPU fallback">
            <WarningAmberIcon fontSize="small" color="warning" />
          </Tooltip>
        )}
      </Box>

      {/* Quick Switch Row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FormControl size="small" sx={{ minWidth: 140, flex: 1 }}>
          <InputLabel>Model</InputLabel>
          <Select
            value={selectedModelPath}
            label="Model"
            onChange={(e) => setSelectedModelPath(e.target.value)}
            disabled={modelsLoading || switching}
          >
            {modelList.map(([id, info]) => (
              <MenuItem key={id} value={info.path}>
                {info.name || id}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 80 }}>
          <InputLabel>Device</InputLabel>
          <Select
            value={selectedDevice}
            label="Device"
            onChange={(e) => setSelectedDevice(e.target.value)}
            disabled={switching}
          >
            <MenuItem value="auto">Auto</MenuItem>
            <MenuItem value="gpu">GPU</MenuItem>
            <MenuItem value="cpu">CPU</MenuItem>
          </Select>
        </FormControl>

        <Tooltip title="Switch model">
          <span>
            <IconButton
              size="small"
              color="primary"
              onClick={handleSwitch}
              disabled={!selectedModelPath || switching}
            >
              {switching ? <CircularProgress size={18} /> : <SwapHorizIcon />}
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      {/* Link to Models page */}
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Tooltip title="Open full model management">
          <Typography
            component={Link}
            to="/models"
            variant="caption"
            color="primary"
            sx={{ display: 'flex', alignItems: 'center', gap: 0.5, textDecoration: 'none' }}
          >
            Manage Models <OpenInNewIcon sx={{ fontSize: 12 }} />
          </Typography>
        </Tooltip>
      </Box>
    </Box>
  );
};

export default ModelQuickControl;
