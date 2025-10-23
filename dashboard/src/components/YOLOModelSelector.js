// dashboard/src/components/YOLOModelSelector.js

/**
 * YOLOModelSelector Component
 *
 * A UI component for dynamically managing YOLO models in SmartTracker.
 * Mirrors the TrackerSelector/FollowerSelector UI pattern for consistency.
 *
 * Features:
 * - Model discovery and listing
 * - Real-time current model display
 * - Model switching without restart
 * - File upload support (.pt files)
 * - Model deletion
 * - Custom model detection
 * - NCNN export status
 * - Device selection (GPU/CPU/Auto)
 *
 * Project: PixEagle
 * Author: Alireza Ghaderi
 * Repository: https://github.com/alireza787b/PixEagle
 */

import React, { useState, useMemo, useCallback, memo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Alert,
  CircularProgress,
  IconButton,
  Tooltip,
  Skeleton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  LinearProgress,
  FormControlLabel,
  Radio,
  RadioGroup
} from '@mui/material';
import {
  Memory,
  SwapHoriz,
  CheckCircle,
  Warning,
  Info,
  CloudUpload,
  Delete,
  Speed,
  Autorenew,
  Star,
  CloudDownload
} from '@mui/icons-material';
import {
  useYOLOModels,
  useSwitchYOLOModel,
  useUploadYOLOModel,
  useDeleteYOLOModel
} from '../hooks/useYOLOModels';

// Loading skeleton component
const LoadingSkeleton = () => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Skeleton variant="text" width={150} height={32} />
        <Skeleton variant="circular" width={40} height={40} />
      </Box>
      <Skeleton variant="rectangular" height={56} sx={{ borderRadius: 1, mb: 2 }} />
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        <Skeleton variant="rectangular" width={80} height={24} sx={{ borderRadius: 1 }} />
        <Skeleton variant="rectangular" width={90} height={24} sx={{ borderRadius: 1 }} />
      </Box>
    </CardContent>
  </Card>
);

const YOLOModelSelector = memo(() => {
  // Custom hooks for YOLO model management
  const { models, currentModel, loading: loadingModels, error: modelsError, refetch } = useYOLOModels();
  const { switchModel, switching, switchError } = useSwitchYOLOModel();
  const { uploadModel, uploading, uploadError, uploadProgress, resetUpload } = useUploadYOLOModel();
  const { deleteModel, deleting, deleteError } = useDeleteYOLOModel();

  // Local state
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('auto');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [modelToDelete, setModelToDelete] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [autoExportNcnn, setAutoExportNcnn] = useState(true);

  // Update selected model when current model changes
  React.useEffect(() => {
    if (currentModel && !selectedModel && models) {
      // Find the model_id that matches the current model filename
      const currentModelEntry = Object.entries(models).find(
        ([, modelData]) => modelData.path?.endsWith(currentModel)
      );
      if (currentModelEntry) {
        setSelectedModel(currentModelEntry[0]);
      }
    }
  }, [currentModel, selectedModel, models]);

  // Memoized model list for dropdown
  const modelOptions = useMemo(() => {
    if (!models) return [];

    return Object.entries(models).map(([modelId, modelData]) => ({
      value: modelId,
      label: modelData.name || modelId,
      isCustom: modelData.is_custom || false,
      hasNcnn: modelData.has_ncnn || false,
      numClasses: modelData.num_classes || 80,
      type: modelData.type || 'unknown',
      path: modelData.path || ''
    }));
  }, [models]);

  // Handle model selection change
  const handleModelChange = useCallback((event) => {
    setSelectedModel(event.target.value);
  }, []);

  // Handle device selection change
  const handleDeviceChange = useCallback((event) => {
    setSelectedDevice(event.target.value);
  }, []);

  // Handle switch button click
  const handleSwitch = useCallback(async () => {
    if (!selectedModel || !models || !models[selectedModel]) {
      return;
    }

    const modelPath = models[selectedModel].path;
    const result = await switchModel(modelPath, selectedDevice);

    if (result.success) {
      // Refresh model list to update current model
      setTimeout(() => refetch(), 500);
    }
  }, [selectedModel, selectedDevice, models, switchModel, refetch]);

  // Handle file selection for upload
  const handleFileSelect = useCallback((event) => {
    const file = event.target.files[0];
    if (file && file.name.endsWith('.pt')) {
      setSelectedFile(file);
    } else {
      alert('Please select a .pt file');
      event.target.value = null;
    }
  }, []);

  // Handle upload
  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;

    const result = await uploadModel(selectedFile, autoExportNcnn);

    if (result.success) {
      setUploadDialogOpen(false);
      setSelectedFile(null);
      resetUpload();
      // Refresh model list
      setTimeout(() => refetch(), 500);
    }
  }, [selectedFile, autoExportNcnn, uploadModel, resetUpload, refetch]);

  // Handle delete confirmation
  const handleDeleteClick = useCallback((modelId) => {
    setModelToDelete(modelId);
    setDeleteDialogOpen(true);
  }, []);

  // Handle delete execution
  const handleDeleteConfirm = useCallback(async () => {
    if (!modelToDelete) return;

    const result = await deleteModel(modelToDelete);

    if (result.success) {
      setDeleteDialogOpen(false);
      setModelToDelete(null);
      // Clear selection if deleted model was selected
      if (selectedModel === modelToDelete) {
        setSelectedModel('');
      }
      // Refresh model list
      setTimeout(() => refetch(), 500);
    }
  }, [modelToDelete, deleteModel, selectedModel, refetch]);

  // Check if switch button should be disabled
  const isSwitchDisabled = useMemo(() => {
    if (!selectedModel || !models || !models[selectedModel]) return true;

    const selectedModelPath = models[selectedModel].path;
    const currentModelPath = currentModel;

    return (
      !selectedModel ||
      selectedModelPath?.endsWith(currentModelPath) ||
      switching ||
      loadingModels
    );
  }, [selectedModel, currentModel, models, switching, loadingModels]);

  // Get model icon based on type
  const getModelIcon = (isCustom, hasNcnn) => {
    if (isCustom) return '🎨';
    if (hasNcnn) return '⚡';
    return '🤖';
  };

  // Show loading skeleton
  if (loadingModels && !models) {
    return <LoadingSkeleton />;
  }

  // Show error state
  if (modelsError && !models) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            YOLO Model Selector
          </Typography>
          <Alert severity="error" size="small">
            {modelsError || 'Failed to load YOLO models'}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card sx={{ height: '100%', opacity: switching ? 0.7 : 1, transition: 'opacity 0.3s' }}>
        <CardContent>
          {/* Header */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">
              YOLO Model Selector
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Tooltip title="Upload new model">
                <IconButton size="small" onClick={() => setUploadDialogOpen(true)}>
                  <CloudUpload />
                </IconButton>
              </Tooltip>
              <Tooltip title="Manage YOLO models">
                <IconButton size="small">
                  <Memory />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {/* Current Model Status */}
          {currentModel && (
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              <Chip
                label="Active"
                color="success"
                size="small"
                icon={<CheckCircle />}
              />
              <Chip
                label={currentModel}
                color="primary"
                size="small"
                icon={<Star />}
              />
              {models && Object.values(models).find(m => m.path?.endsWith(currentModel))?.is_custom && (
                <Chip
                  label="Custom Model"
                  size="small"
                  sx={{ bgcolor: '#9C27B0', color: 'white' }}
                  icon={<Star fontSize="small" />}
                />
              )}
            </Box>
          )}

          {/* Model Selection Dropdown */}
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel id="model-select-label">Select Model</InputLabel>
            <Select
              labelId="model-select-label"
              value={selectedModel}
              onChange={handleModelChange}
              label="Select Model"
              disabled={switching || loadingModels}
            >
              {modelOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                    <span>{getModelIcon(option.isCustom, option.hasNcnn)}</span>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2">
                        {option.label}
                        {option.isCustom && ' (Custom)'}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        {option.numClasses} classes
                        {option.hasNcnn && ' • NCNN ready'}
                      </Typography>
                    </Box>
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteClick(option.value);
                      }}
                      disabled={deleting}
                    >
                      <Delete fontSize="small" />
                    </IconButton>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* Device Selection */}
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel id="device-select-label">Device</InputLabel>
            <Select
              labelId="device-select-label"
              value={selectedDevice}
              onChange={handleDeviceChange}
              label="Device"
              disabled={switching || loadingModels}
            >
              <MenuItem value="auto">
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Autorenew fontSize="small" />
                  Auto (GPU if available)
                </Box>
              </MenuItem>
              <MenuItem value="gpu">
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Speed fontSize="small" />
                  GPU (Faster)
                </Box>
              </MenuItem>
              <MenuItem value="cpu">
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Memory fontSize="small" />
                  CPU (Slower)
                </Box>
              </MenuItem>
            </Select>
          </FormControl>

          {/* Switch Button */}
          <Button
            fullWidth
            variant="contained"
            color="primary"
            startIcon={switching ? <CircularProgress size={16} color="inherit" /> : <SwapHoriz />}
            onClick={handleSwitch}
            disabled={isSwitchDisabled}
            sx={{ mb: 2 }}
          >
            {switching ? 'Switching...' : 'Switch Model'}
          </Button>

          {/* Switch Error/Info Alert */}
          {switchError && (
            <Alert
              severity={switchError.includes('switched successfully') ? 'success' : 'error'}
              size="small"
              sx={{ mb: 2 }}
            >
              <Typography variant="caption">
                {switchError}
              </Typography>
            </Alert>
          )}

          {/* Switching Progress */}
          {switching && (
            <Box sx={{ mb: 2 }}>
              <CircularProgress size={20} />
              <Typography variant="caption" color="textSecondary" sx={{ ml: 1 }}>
                Switching model...
              </Typography>
            </Box>
          )}

          {/* Info Message */}
          <Alert severity="info" size="small">
            <Typography variant="caption">
              Models are loaded from yolo/ folder. Upload .pt files or use add_yolo_model.py CLI.
            </Typography>
          </Alert>
        </CardContent>
      </Card>

      {/* Upload Dialog */}
      <Dialog open={uploadDialogOpen} onClose={() => setUploadDialogOpen(false)}>
        <DialogTitle>Upload YOLO Model</DialogTitle>
        <DialogContent>
          <Box sx={{ minWidth: 400, pt: 2 }}>
            <input
              accept=".pt"
              style={{ display: 'none' }}
              id="model-file-input"
              type="file"
              onChange={handleFileSelect}
            />
            <label htmlFor="model-file-input">
              <Button
                variant="outlined"
                component="span"
                fullWidth
                startIcon={<CloudDownload />}
                sx={{ mb: 2 }}
              >
                Select .pt File
              </Button>
            </label>

            {selectedFile && (
              <Alert severity="info" size="small" sx={{ mb: 2 }}>
                <Typography variant="caption">
                  Selected: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                </Typography>
              </Alert>
            )}

            <FormControlLabel
              control={
                <input
                  type="checkbox"
                  checked={autoExportNcnn}
                  onChange={(e) => setAutoExportNcnn(e.target.checked)}
                />
              }
              label={
                <Typography variant="caption">
                  Auto-export to NCNN format (recommended for CPU)
                </Typography>
              }
            />

            {uploading && (
              <Box sx={{ mt: 2 }}>
                <LinearProgress variant="determinate" value={uploadProgress} />
                <Typography variant="caption" color="textSecondary" sx={{ mt: 1 }}>
                  Uploading... {uploadProgress}%
                </Typography>
              </Box>
            )}

            {uploadError && (
              <Alert severity="error" size="small" sx={{ mt: 2 }}>
                {uploadError}
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadDialogOpen(false)} disabled={uploading}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            variant="contained"
            disabled={!selectedFile || uploading}
            startIcon={uploading ? <CircularProgress size={16} /> : <CloudUpload />}
          >
            Upload
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Model?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to delete this model? This will remove the .pt file and NCNN exports.
          </Typography>
          {deleteError && (
            <Alert severity="error" size="small" sx={{ mt: 2 }}>
              {deleteError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)} disabled={deleting}>
            Cancel
          </Button>
          <Button
            onClick={handleDeleteConfirm}
            color="error"
            variant="contained"
            disabled={deleting}
            startIcon={deleting ? <CircularProgress size={16} /> : <Delete />}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
});

export default YOLOModelSelector;
