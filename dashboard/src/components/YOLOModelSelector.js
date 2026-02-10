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

import React, { useState, useMemo, useCallback, useEffect, memo } from 'react';
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
  TextField,
} from '@mui/material';
import {
  SwapHoriz,
  CheckCircle,
  CloudUpload,
  Delete,
  Speed,
  Memory,
  Autorenew,
  Star,
  CloudDownload,
  Warning,
  Label
} from '@mui/icons-material';
import {
  useYOLOModels,
  useSwitchYOLOModel,
  useUploadYOLOModel,
  useDeleteYOLOModel,
  useYOLOModelLabels,
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
  const {
    models,
    currentModel,
    configuredModel,
    configuredGpuModel,
    configuredCpuModel,
    runtime,
    activeModelId,
    activeModelSource,
    activeModelSummary,
    loading: loadingModels,
    error: modelsError,
    refetch
  } = useYOLOModels();
  const { switchModel, switching, switchError } = useSwitchYOLOModel();
  const { uploadModel, uploading, uploadError, uploadProgress, resetUpload } = useUploadYOLOModel();
  const { deleteModel, deleting, deleteError } = useDeleteYOLOModel();
  const { fetchLabels, loading: labelsLoading, error: labelsError } = useYOLOModelLabels();

  // Local state
  const [selectedModel, setSelectedModel] = useState('');
  const [selectedDevice, setSelectedDevice] = useState('auto');
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [modelToDelete, setModelToDelete] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [autoExportNcnn, setAutoExportNcnn] = useState(true);
  const [actionFeedback, setActionFeedback] = useState(null);
  const [labelsDialogOpen, setLabelsDialogOpen] = useState(false);
  const [labelsQuery, setLabelsQuery] = useState('');
  const [labelRows, setLabelRows] = useState([]);
  const [labelFilteredCount, setLabelFilteredCount] = useState(0);
  const [labelTotalCount, setLabelTotalCount] = useState(0);
  const [labelHasMore, setLabelHasMore] = useState(false);
  const hasPendingSelection = React.useRef(false);
  const labelsRequestId = React.useRef(0);

  const activeModelSelectionId = useMemo(() => {
    if (!models) return '';
    const modelToMatch = currentModel || configuredModel;
    if (!modelToMatch) return '';
    const entry = Object.entries(models).find(
      ([, modelData]) => modelData.path?.endsWith(modelToMatch)
    );
    return entry?.[0] || '';
  }, [models, currentModel, configuredModel]);

  // Update selected model when current/configured model changes
  // Priority: currentModel (if SmartTracker active) > configuredModel (from config.yaml) > empty
  React.useEffect(() => {
    if (!models) return;
    if (hasPendingSelection.current) return;

    // Use currentModel if SmartTracker is active, otherwise use configuredModel
    const modelToSelect = currentModel || configuredModel;

    if (modelToSelect) {
      // Find the model_id that matches the model filename
      const modelEntry = Object.entries(models).find(
        ([, modelData]) => modelData.path?.endsWith(modelToSelect)
      );
      if (modelEntry) {
        // Only update if different to avoid unnecessary re-renders
        const modelId = modelEntry[0];
        setSelectedModel((prev) => (prev === modelId ? prev : modelId));
      }
    } else if (!modelToSelect) {
      // Clear selection if no model is configured
      setSelectedModel((prev) => (prev ? '' : prev));
    }
  }, [currentModel, configuredModel, models]);

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

  const resolvedActiveModelSummary = useMemo(() => {
    if (activeModelSummary?.model_id) {
      return activeModelSummary;
    }

    if (!models) {
      return null;
    }

    const modelIdentifier = currentModel || configuredModel;
    if (!modelIdentifier) {
      return null;
    }

    const matchedEntry = Object.entries(models).find(
      ([, modelData]) => modelData.path?.endsWith(modelIdentifier)
    );
    if (!matchedEntry) {
      return null;
    }

    const [fallbackModelId, modelData] = matchedEntry;
    const labels = modelData.class_names || [];
    return {
      model_id: activeModelId || fallbackModelId,
      model_name: modelData.name || fallbackModelId,
      task: modelData.task || runtime?.model_task || 'unknown',
      geometry_mode: runtime?.geometry_mode || modelData.output_geometry || 'aabb',
      backend: runtime?.backend || null,
      device: runtime?.effective_device || null,
      fallback_occurred: Boolean(runtime?.fallback_occurred),
      num_labels: modelData.num_classes || labels.length || 0,
      label_preview: labels.slice(0, 8),
      has_more_labels: labels.length > 8,
      is_custom: Boolean(modelData.is_custom),
      has_ncnn: Boolean(modelData.has_ncnn),
      source: activeModelSource || (currentModel ? 'runtime' : 'configured'),
    };
  }, [activeModelSummary, activeModelId, activeModelSource, currentModel, configuredModel, models, runtime]);

  const handleOpenLabelsDialog = useCallback(() => {
    if (!resolvedActiveModelSummary?.model_id) {
      return;
    }
    setLabelsQuery('');
    setLabelsDialogOpen(true);
  }, [resolvedActiveModelSummary]);

  const handleCloseLabelsDialog = useCallback(() => {
    setLabelsDialogOpen(false);
  }, []);

  useEffect(() => {
    if (!labelsDialogOpen || !resolvedActiveModelSummary?.model_id) {
      return undefined;
    }

    const requestId = ++labelsRequestId.current;
    const timer = setTimeout(async () => {
      const response = await fetchLabels(resolvedActiveModelSummary.model_id, {
        offset: 0,
        limit: 500,
        search: labelsQuery,
      });

      if (requestId !== labelsRequestId.current) {
        return;
      }

      if (response.success) {
        setLabelRows(response.labels || []);
        setLabelFilteredCount(response.filteredCount ?? 0);
        setLabelTotalCount(response.totalLabels ?? 0);
        setLabelHasMore(Boolean(response.hasMore));
      } else {
        setLabelRows([]);
        setLabelFilteredCount(0);
        setLabelTotalCount(0);
        setLabelHasMore(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [labelsDialogOpen, resolvedActiveModelSummary, labelsQuery, fetchLabels]);

  // Handle model selection change
  const handleModelChange = useCallback((event) => {
    const newValue = event.target.value;
    setSelectedModel(newValue);
    hasPendingSelection.current = Boolean(newValue && newValue !== activeModelSelectionId);
  }, [activeModelSelectionId]);

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
    hasPendingSelection.current = false;

    if (result.success) {
      const runtimeInfo = result.runtime || {};
      const fallbackText = runtimeInfo?.fallback_occurred
        ? ` Fallback: ${runtimeInfo.fallback_reason || 'GPU load failed'}`
        : '';
      setActionFeedback({
        type: 'success',
        message: `Switched to ${runtimeInfo.model_name || modelPath} (${runtimeInfo.backend || 'unknown'}).${fallbackText}`
      });
      // Refresh model list to update current model
      refetch();
      setTimeout(() => refetch(), 500);
    } else {
      setActionFeedback({
        type: 'error',
        message: result.error || 'Failed to switch model'
      });
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
      const exportInfo = result.ncnnExport;
      const exportSummary = result.ncnnExported
        ? ` NCNN ready${exportInfo?.ncnn_path ? `: ${exportInfo.ncnn_path}` : ''}.`
        : ' Uploaded without NCNN export.';
      setActionFeedback({
        type: 'success',
        message: `${result.filename} uploaded.${exportSummary}`
      });
      setUploadDialogOpen(false);
      setSelectedFile(null);
      resetUpload();
      // Refresh model list
      setTimeout(() => refetch(), 500);
    } else {
      setActionFeedback({
        type: 'error',
        message: result.error || 'Upload failed'
      });
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
      setActionFeedback({
        type: 'success',
        message: `Deleted model ${modelToDelete}`
      });
      setDeleteDialogOpen(false);
      setModelToDelete(null);
      // Clear selection if deleted model was selected
      if (selectedModel === modelToDelete) {
        setSelectedModel('');
      }
      hasPendingSelection.current = false;
      // Refresh model list
      setTimeout(() => refetch(), 500);
    } else {
      setActionFeedback({
        type: 'error',
        message: result.error || 'Delete failed'
      });
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
            <Tooltip title="Upload new model">
              <IconButton size="small" onClick={() => setUploadDialogOpen(true)}>
                <CloudUpload />
              </IconButton>
            </Tooltip>
          </Box>

          {/* Model Status - Show Active or Configured */}
          {(currentModel || configuredModel) && (
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              <Chip
                label={currentModel ? "Active" : "Configured"}
                color={currentModel ? "success" : "default"}
                size="small"
                icon={<CheckCircle />}
              />
              <Chip
                label={currentModel || configuredModel}
                color="primary"
                size="small"
                icon={<Star />}
              />
              {models && Object.values(models).find(m => m.path?.endsWith(currentModel || configuredModel))?.is_custom && (
                <Chip
                  label="Custom Model"
                  size="small"
                  sx={{ bgcolor: '#9C27B0', color: 'white' }}
                  icon={<Star fontSize="small" />}
                />
              )}
              {runtime?.backend && (
                <Chip
                  label={`Backend: ${runtime.backend}`}
                  color={runtime.backend === 'cuda' ? 'success' : 'warning'}
                  size="small"
                  icon={runtime.backend === 'cuda' ? <Speed fontSize="small" /> : <Memory fontSize="small" />}
                />
              )}
              {runtime?.fallback_occurred && (
                <Chip
                  label="Fallback Applied"
                  color="warning"
                  size="small"
                  icon={<Warning fontSize="small" />}
                />
              )}
            </Box>
          )}

          {resolvedActiveModelSummary && (
            <Box
              sx={{
                mb: 2,
                p: 1.5,
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'action.hover'
              }}
            >
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                Active Model Capabilities
              </Typography>

              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                <Chip
                  size="small"
                  variant="outlined"
                  icon={<Label fontSize="small" />}
                  label={`${resolvedActiveModelSummary.num_labels || 0} labels`}
                  onClick={handleOpenLabelsDialog}
                  clickable
                  color="info"
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Task: ${resolvedActiveModelSummary.task || 'unknown'}`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Geometry: ${resolvedActiveModelSummary.geometry_mode || 'aabb'}`}
                />
                <Chip
                  size="small"
                  variant="outlined"
                  label={`Source: ${resolvedActiveModelSummary.source || 'unknown'}`}
                />
                {resolvedActiveModelSummary.has_ncnn && (
                  <Chip
                    size="small"
                    variant="outlined"
                    color="success"
                    label="NCNN Ready"
                  />
                )}
                {resolvedActiveModelSummary.is_custom && (
                  <Chip
                    size="small"
                    variant="outlined"
                    color="secondary"
                    label="Custom Labels"
                  />
                )}
              </Box>

              {(resolvedActiveModelSummary.label_preview || []).length > 0 && (
                <Typography variant="caption" color="textSecondary">
                  Labels preview: {resolvedActiveModelSummary.label_preview.join(', ')}
                  {resolvedActiveModelSummary.has_more_labels ? ' ...' : ''}
                </Typography>
              )}
            </Box>
          )}

          {(configuredGpuModel || configuredCpuModel) && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block' }}>
                Config defaults:
              </Typography>
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block' }}>
                GPU: {configuredGpuModel || 'n/a'} | CPU: {configuredCpuModel || 'n/a'}
              </Typography>
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
                  Auto (prefer CUDA, fallback CPU)
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
                  CPU (prefer NCNN)
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

          <Button
            fullWidth
            variant="outlined"
            color="error"
            startIcon={deleting ? <CircularProgress size={16} color="inherit" /> : <Delete />}
            onClick={() => handleDeleteClick(selectedModel)}
            disabled={!selectedModel || deleting || switching}
            sx={{ mb: 2 }}
          >
            Delete Selected Model
          </Button>

          {/* Switch Error/Info Alert */}
          {switchError && (
            <Alert severity="error" size="small" sx={{ mb: 2 }}>
              <Typography variant="caption">{switchError}</Typography>
            </Alert>
          )}

          {actionFeedback && (
            <Alert severity={actionFeedback.type} size="small" sx={{ mb: 2 }}>
              <Typography variant="caption">{actionFeedback.message}</Typography>
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
              {currentModel
                ? "SmartTracker is running with the active model. CPU mode prefers NCNN if available."
                : "Configured model is used when Smart Mode starts. Upload .pt and optional NCNN export is handled automatically."}
            </Typography>
          </Alert>
        </CardContent>
      </Card>

      <Dialog
        open={labelsDialogOpen}
        onClose={handleCloseLabelsDialog}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>
          Model Labels
          {resolvedActiveModelSummary?.model_name ? ` - ${resolvedActiveModelSummary.model_name}` : ''}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1 }}>
            <TextField
              fullWidth
              size="small"
              label="Search labels"
              value={labelsQuery}
              onChange={(event) => setLabelsQuery(event.target.value)}
              placeholder="Type to filter class names"
            />

            {(labelTotalCount > 0 || labelFilteredCount > 0) && (
              <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 1 }}>
                Showing {labelRows.length} of {labelFilteredCount} matching labels
                {labelFilteredCount !== labelTotalCount ? ` (${labelTotalCount} total)` : ''}
              </Typography>
            )}

            {labelsLoading && <LinearProgress sx={{ mt: 1.5 }} />}

            {labelsError && (
              <Alert severity="error" size="small" sx={{ mt: 2 }}>
                {labelsError}
              </Alert>
            )}

            {!labelsLoading && !labelsError && labelRows.length === 0 && (
              <Alert severity="info" size="small" sx={{ mt: 2 }}>
                No labels found for this query.
              </Alert>
            )}

            {!labelsLoading && labelRows.length > 0 && (
              <Box
                sx={{
                  mt: 2,
                  maxHeight: 320,
                  overflowY: 'auto',
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                }}
              >
                {labelRows.map((labelItem) => (
                  <Box
                    key={`${labelItem.class_id}-${labelItem.label}`}
                    sx={{
                      px: 1.5,
                      py: 1,
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                      '&:last-child': { borderBottom: 'none' },
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                    }}
                  >
                    <Chip
                      size="small"
                      label={`#${labelItem.class_id}`}
                      sx={{ minWidth: 56, fontFamily: 'monospace' }}
                    />
                    <Typography variant="body2">{labelItem.label}</Typography>
                  </Box>
                ))}
              </Box>
            )}

            {labelHasMore && (
              <Alert severity="warning" size="small" sx={{ mt: 1.5 }}>
                Showing first 500 labels. Narrow your search to see specific classes.
              </Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseLabelsDialog}>Close</Button>
        </DialogActions>
      </Dialog>

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
