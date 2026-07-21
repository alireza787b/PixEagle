// dashboard/src/pages/ModelsPage.js
/**
 * Detection Models management page.
 *
 * Features:
 * - Active model summary with backend/device info
 * - Model inventory table with activate/delete actions
 * - Explicitly trust and register local model files
 * - Label viewer dialog
 *
 * Project: PixEagle
 */

import React, { useState, useMemo } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Tooltip,
  Button,
  Chip,
  Grid,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  LinearProgress,
  Snackbar,
  Alert,
  Skeleton,
  Checkbox,
  FormControlLabel,
} from '@mui/material';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import RefreshIcon from '@mui/icons-material/Refresh';
import DeleteIcon from '@mui/icons-material/Delete';
import RadioButtonCheckedIcon from '@mui/icons-material/RadioButtonChecked';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import LabelIcon from '@mui/icons-material/Label';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import SyncIcon from '@mui/icons-material/Sync';
import DownloadIcon from '@mui/icons-material/Download';

import {
  useModels,
  useModelLabels,
  useSwitchModel,
  useUploadModel,
  useDeleteModel,
} from '../hooks/useModels';
import { endpoints } from '../services/apiEndpoints';
import { downloadApiBlob } from '../services/apiClient';

/** Format file size in bytes to a human-readable string. */
const formatSize = (bytes) => {
  if (!bytes || bytes <= 0) return '--';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

/** Detect model architecture from filename/id. */
const detectModelType = (name) => {
  const n = (name || '').toLowerCase();
  if (/yolo\s*v?\s*12/.test(n)) return 'YOLOv12';
  if (/yolo\s*2[6-9]|yolo\s*v?26/.test(n)) return 'YOLO26';
  if (/yolo\s*11|yolo\s*v?11/.test(n)) return 'YOLO11';
  if (/yolov?10/.test(n)) return 'YOLOv10';
  if (/yolov?9/.test(n)) return 'YOLOv9';
  if (/yolov?8/.test(n)) return 'YOLOv8';
  if (/yolov?5/.test(n)) return 'YOLOv5';
  if (/yolo/i.test(n)) return 'YOLO';
  return 'Custom';
};

const ModelsPage = () => {
  const {
    models,
    currentModel,
    configuredGpuModel,
    configuredCpuModel,
    runtime,
    activeModelId,
    activeModelSource,
    activeModelSummary,
    loading,
    error,
    refetch,
    rescan,
  } = useModels(10000);

  const { switchModel, switching } = useSwitchModel();
  const { deleteModel, deleting } = useDeleteModel();
  const { uploadModel, uploading, uploadProgress, resetUpload } = useUploadModel();
  const { fetchLabels } = useModelLabels();

  // Local UI state
  const [deleteDialog, setDeleteDialog] = useState({ open: false, modelId: null, modelName: '' });
  const [labelsDialog, setLabelsDialog] = useState({ open: false, labels: [], modelName: '' });
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadAutoNcnn, setUploadAutoNcnn] = useState(false);
  const [uploadExpectedSha256, setUploadExpectedSha256] = useState('');
  const [uploadTrustModel, setUploadTrustModel] = useState(false);
  const [uploadDisplayName, setUploadDisplayName] = useState('');
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });

  const showSnackbar = (message, severity = 'success') => {
    setSnackbar({ open: true, message, severity });
  };

  // Derive model list from the models map
  const modelList = useMemo(() => {
    if (!models || typeof models !== 'object') return [];
    return Object.entries(models).map(([id, info]) => ({ id, ...info }));
  }, [models]);

  const totalModels = modelList.length;
  const ncnnCount = modelList.filter((m) => m.has_ncnn || m.ncnn_available).length;

  // -- Handlers --

  const handleActivate = async (model) => {
    const modelPath = model.path || model.id;
    const modelName = model.name || model.id;
    const result = await switchModel(modelPath);
    if (result.success) {
      showSnackbar(
        result.action === 'model_configured'
          ? `Selected for Smart Mode: ${modelName}`
          : `Model activated: ${modelName}`
      );
      await refetch();
    } else {
      showSnackbar(result.error || 'Failed to activate model', 'error');
    }
  };

  const handleDeleteConfirm = async () => {
    const { modelId } = deleteDialog;
    setDeleteDialog({ open: false, modelId: null, modelName: '' });
    const result = await deleteModel(modelId);
    if (result.success) {
      showSnackbar('Model deleted successfully');
      refetch();
    } else {
      showSnackbar(result.error || 'Failed to delete model', 'error');
    }
  };

  const handleViewLabels = async (modelId, modelName) => {
    const result = await fetchLabels(modelId);
    if (result.success) {
      setLabelsDialog({ open: true, labels: result.labels, modelName });
    } else {
      showSnackbar(result.error || 'Failed to fetch labels', 'error');
    }
  };

  const handleUpload = async () => {
    if (!uploadFile) return;
    const result = await uploadModel(uploadFile, {
      autoExportNcnn: uploadAutoNcnn,
      expectedSha256: uploadExpectedSha256,
      trustModel: uploadTrustModel,
      displayName: uploadDisplayName,
    });
    if (result.success) {
      showSnackbar(`Registered: ${result.filename || uploadFile.name}`);
      setUploadFile(null);
      setUploadExpectedSha256('');
      setUploadTrustModel(false);
      setUploadDisplayName('');
      resetUpload();
      refetch();
    } else {
      showSnackbar(result.error || 'Upload failed', 'error');
    }
  };

  const handleModelFileDownload = async (model) => {
    const modelName = model.name || model.filename || `${model.id}.pt`;
    try {
      await downloadApiBlob(endpoints.modelFile(model.id), modelName);
      showSnackbar(`Downloaded: ${modelName}`);
    } catch (err) {
      showSnackbar(err.message || 'Failed to download model file', 'error');
    }
  };

  // Active model derived info — runtime is populated once SmartTracker loads a model,
  // activeModelSummary comes from /api/models/active and is always available
  const activeBackend = runtime?.backend || activeModelSummary?.backend || 'ultralytics';
  const activeDevice = runtime?.effective_device || activeModelSummary?.device || '--';
  const activeTask = activeModelSummary?.task || '--';
  const activeName = activeModelSummary?.model_name || currentModel || '--';
  const activeHeading = activeModelSource === 'runtime'
    ? 'Active Model'
    : activeModelSource === 'configured' ? 'Selected Model' : 'Detection Model';
  const activeLabelCount = activeModelSummary?.num_labels ?? '--';
  const fallbackOccurred = runtime?.fallback_occurred === true || activeModelSummary?.fallback_occurred === true;
  const fallbackEnabled = runtime?.gpu_to_cpu_fallback !== undefined ? runtime.gpu_to_cpu_fallback : '--';
  const isCuda = typeof activeDevice === 'string' && activeDevice.toLowerCase().includes('cuda');

  return (
    <Box sx={{ p: 3 }}>
      {/* Page Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
        <SmartToyIcon color="primary" />
        <Typography variant="h5" fontWeight={600}>
          Detection Models
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Tooltip title="Revalidate trusted models and rebuild metadata">
          <IconButton onClick={() => { rescan(); showSnackbar('Rescanning model files...', 'info'); }} size="small">
            <SyncIcon />
          </IconButton>
        </Tooltip>
        <Tooltip title="Refresh">
          <IconButton onClick={refetch} size="small">
            <RefreshIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {error && (
        <Alert severity="warning" sx={{ mb: 2 }} onClose={() => {}}>
          Could not reach model API: {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Active Model Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <SmartToyIcon color="primary" sx={{ fontSize: 20 }} />
                <Typography variant="subtitle2" fontWeight={600}>{activeHeading}</Typography>
              </Box>
              {loading ? (
                <Skeleton variant="rectangular" height={90} />
              ) : (
                <>
                  <Typography variant="body1" fontWeight={600} sx={{ mb: 1, fontFamily: 'monospace' }}>
                    {activeName}
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
                    <Chip label={activeBackend} size="small" variant="outlined" />
                    <Chip
                      label={activeDevice}
                      size="small"
                      color={isCuda ? 'success' : 'default'}
                      variant="outlined"
                    />
                    <Chip label={activeTask} size="small" variant="outlined" />
                  </Box>
                  {fallbackOccurred && (
                    <Alert severity="warning" icon={<WarningAmberIcon fontSize="small" />} sx={{ py: 0, mb: 1 }}>
                      GPU-to-CPU fallback occurred
                    </Alert>
                  )}
                  <Typography variant="caption" color="text.secondary">
                    Classes: {activeLabelCount}
                  </Typography>
                </>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Backend Info Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <MemoryIcon color="primary" sx={{ fontSize: 20 }} />
                <Typography variant="subtitle2" fontWeight={600}>Backend Info</Typography>
              </Box>
              {loading ? (
                <Skeleton variant="rectangular" height={90} />
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  <Row label="Backend" value={activeBackend} />
                  <Row label="Runtime Device" value={activeDevice} />
                  <Row
                    label="GPU-to-CPU Fallback"
                    value={fallbackEnabled === true ? 'Enabled' : fallbackEnabled === false ? 'Disabled' : '--'}
                  />
                  <Row label="GPU Model" value={configuredGpuModel || '--'} mono />
                  <Row label="CPU Model" value={configuredCpuModel || '--'} mono />
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Model Storage Card */}
        <Grid item xs={12} md={4}>
          <Card variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <StorageIcon color="primary" sx={{ fontSize: 20 }} />
                <Typography variant="subtitle2" fontWeight={600}>Model Storage</Typography>
              </Box>
              {loading ? (
                <Skeleton variant="rectangular" height={90} />
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  <Row label="Total Models" value={totalModels} />
                  <Row label="With NCNN Export" value={ncnnCount} />
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Model Inventory Table */}
        <Grid item xs={12}>
          <Card variant="outlined">
            <CardContent sx={{ pb: 1 }}>
              <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>
                Model Inventory
              </Typography>
            </CardContent>
            {loading ? (
              <Box sx={{ p: 3 }}>
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} variant="text" height={40} sx={{ mb: 0.5 }} />
                ))}
              </Box>
            ) : modelList.length === 0 ? (
              <Box sx={{ p: 4, textAlign: 'center' }}>
                <SmartToyIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                <Typography color="text.secondary">
                  No models found. Upload a model below.
                </Typography>
              </Box>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Name</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Type</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }} align="right">Size</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }} align="right">Classes</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>Task</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }}>NCNN</TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 12 }} align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {modelList.map((m) => {
                      const isSelected = m.id === activeModelId;
                      const isRunning = isSelected && activeModelSource === 'runtime';
                      return (
                        <TableRow
                          key={m.id}
                          hover
                          sx={isSelected ? { bgcolor: 'action.selected' } : undefined}
                        >
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                                {m.name || m.id}
                              </Typography>
                              {isSelected && (
                                <Chip
                                  label={isRunning ? 'active' : 'selected'}
                                  size="small"
                                  color={isRunning ? 'success' : 'primary'}
                                  variant={isRunning ? 'filled' : 'outlined'}
                                  sx={{ fontSize: 10, height: 18 }}
                                />
                              )}
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={detectModelType(m.id || m.path || m.name)}
                              size="small"
                              variant="outlined"
                              color={detectModelType(m.id || m.path || m.name) === 'Custom' ? 'secondary' : 'info'}
                              sx={{ fontSize: 10, height: 20 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                              {m.size_bytes ? formatSize(m.size_bytes) : m.size_mb ? `${m.size_mb.toFixed(1)} MB` : '--'}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" sx={{ fontSize: 12 }}>
                              {m.num_classes ?? '--'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ fontSize: 12 }}>
                              {m.task || '--'}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={m.has_ncnn || m.ncnn_available ? 'Yes' : 'No'}
                              size="small"
                              color={m.has_ncnn || m.ncnn_available ? 'success' : 'default'}
                              variant="outlined"
                              sx={{ fontSize: 10, height: 20 }}
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5 }}>
                              <Tooltip title="View Labels">
                                <IconButton
                                  size="small"
                                  onClick={() => handleViewLabels(m.id, m.name || m.id)}
                                >
                                  <LabelIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Download .pt file">
                                <IconButton
                                  size="small"
                                  onClick={() => handleModelFileDownload(m)}
                                >
                                  <DownloadIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title={isSelected ? 'Already selected' : 'Select for Smart Mode'}>
                                <span>
                                  <IconButton
                                    size="small"
                                    color={isSelected ? 'success' : 'primary'}
                                    aria-pressed={isSelected}
                                    aria-label={isSelected
                                      ? `${m.name || m.id} is selected for Smart Mode`
                                      : `Select ${m.name || m.id} for Smart Mode`}
                                    disabled={switching}
                                    onClick={() => {
                                      if (!isSelected) handleActivate(m);
                                    }}
                                  >
                                    {isSelected
                                      ? <RadioButtonCheckedIcon sx={{ fontSize: 18 }} />
                                      : <RadioButtonUncheckedIcon sx={{ fontSize: 18 }} />}
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Delete">
                                <span>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    disabled={isSelected || deleting}
                                    onClick={() => setDeleteDialog({ open: true, modelId: m.id, modelName: m.name || m.id })}
                                  >
                                    <DeleteIcon sx={{ fontSize: 18 }} />
                                  </IconButton>
                                </span>
                              </Tooltip>
                            </Box>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Card>
        </Grid>

        {/* Add Model Panel */}
        <Grid item xs={12}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>
                Add Model
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 500 }}>
                <Button
                  variant="outlined"
                  component="label"
                  startIcon={<CloudUploadIcon />}
                >
                  {uploadFile ? uploadFile.name : 'Choose Model File'}
                  <input
                    type="file"
                    hidden
                    accept=".pt"
                    onChange={(e) => {
                      const nextFile = e.target.files?.[0] || null;
                      setUploadFile(nextFile);
                      setUploadDisplayName(nextFile ? nextFile.name.replace(/\.pt$/i, '') : '');
                      resetUpload();
                    }}
                  />
                </Button>
                <TextField
                  label="Display name (optional)"
                  size="small"
                  value={uploadDisplayName}
                  onChange={(e) => setUploadDisplayName(e.target.value)}
                  inputProps={{ maxLength: 80 }}
                  fullWidth
                />
                <TextField
                  label="Expected SHA-256 (recommended)"
                  placeholder="64 hexadecimal characters"
                  size="small"
                  value={uploadExpectedSha256}
                  onChange={(e) => setUploadExpectedSha256(e.target.value)}
                  inputProps={{ maxLength: 64, spellCheck: false }}
                  fullWidth
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={uploadTrustModel}
                      onChange={(e) => setUploadTrustModel(e.target.checked)}
                      size="small"
                    />
                  }
                  label={<Typography variant="body2">I trust this checkpoint source and approve model loading</Typography>}
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={uploadAutoNcnn}
                      onChange={(e) => setUploadAutoNcnn(e.target.checked)}
                      size="small"
                    />
                  }
                  label={<Typography variant="body2">Export NCNN after registration</Typography>}
                />
                {uploading && (
                  <LinearProgress variant="determinate" value={uploadProgress} sx={{ height: 6, borderRadius: 1 }} />
                )}
                <Button
                  variant="contained"
                  onClick={handleUpload}
                  disabled={!uploadFile || !uploadTrustModel || uploading}
                  startIcon={<CloudUploadIcon />}
                >
                  {uploading ? `Uploading... ${uploadProgress}%` : 'Upload'}
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialog.open}
        onClose={() => setDeleteDialog({ open: false, modelId: null, modelName: '' })}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Delete Model</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{deleteDialog.modelName}</strong>?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialog({ open: false, modelId: null, modelName: '' })}>
            Cancel
          </Button>
          <Button onClick={handleDeleteConfirm} color="error" variant="contained">
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Labels Viewer Dialog */}
      <Dialog
        open={labelsDialog.open}
        onClose={() => setLabelsDialog({ open: false, labels: [], modelName: '' })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Labels: {labelsDialog.modelName}</DialogTitle>
        <DialogContent dividers>
          {labelsDialog.labels.length === 0 ? (
            <Typography color="text.secondary">No labels available.</Typography>
          ) : (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {labelsDialog.labels.map((item, idx) => (
                <Chip
                  key={idx}
                  label={typeof item === 'object' ? `${item.class_id}: ${item.label}` : `${idx}: ${item}`}
                  size="small"
                  variant="outlined"
                />
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLabelsDialog({ open: false, labels: [], modelName: '' })}>
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbar((s) => ({ ...s, open: false }))}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          <Typography variant="body2">{snackbar.message}</Typography>
        </Alert>
      </Snackbar>
    </Box>
  );
};

/** Small helper for label-value rows in info cards. */
const Row = ({ label, value, mono }) => (
  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography
      variant="caption"
      fontWeight={600}
      sx={mono ? { fontFamily: 'monospace', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis' } : undefined}
    >
      {value}
    </Typography>
  </Box>
);

export default ModelsPage;
