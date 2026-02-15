// dashboard/src/pages/ModelsPage.js
/**
 * Detection Models management page.
 *
 * Features:
 * - Active model summary with backend/device info
 * - Model inventory table with activate/delete actions
 * - Upload new model files with optional NCNN auto-export
 * - Download models by name with popular model shortcuts
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
  Tabs,
  Tab,
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
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import MemoryIcon from '@mui/icons-material/Memory';
import StorageIcon from '@mui/icons-material/Storage';
import LabelIcon from '@mui/icons-material/Label';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import SyncIcon from '@mui/icons-material/Sync';

import {
  useModels,
  useModelLabels,
  useSwitchModel,
  useUploadModel,
  useDownloadModel,
  useDeleteModel,
} from '../hooks/useModels';

/** Format file size in bytes to a human-readable string. */
const formatSize = (bytes) => {
  if (!bytes || bytes <= 0) return '--';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const POPULAR_MODELS = ['yolo11n.pt', 'yolo11s.pt', 'yolov8n.pt'];

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
    activeModelSummary,
    loading,
    error,
    refetch,
    rescan,
  } = useModels(10000);

  const { switchModel, switching } = useSwitchModel();
  const { deleteModel, deleting } = useDeleteModel();
  const { uploadModel, uploading, uploadProgress, resetUpload } = useUploadModel();
  const { downloadModel, downloading } = useDownloadModel();
  const { fetchLabels } = useModelLabels();

  // Local UI state
  const [deleteDialog, setDeleteDialog] = useState({ open: false, modelId: null, modelName: '' });
  const [labelsDialog, setLabelsDialog] = useState({ open: false, labels: [], modelName: '' });
  const [addTab, setAddTab] = useState(0);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadAutoNcnn, setUploadAutoNcnn] = useState(true);
  const [downloadName, setDownloadName] = useState('');
  const [downloadAutoNcnn, setDownloadAutoNcnn] = useState(true);
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

  const handleActivate = async (modelPath) => {
    const result = await switchModel(modelPath);
    if (result.success) {
      showSnackbar(`Model activated: ${result.modelInfo?.name || modelPath}`);
      refetch();
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
    const result = await uploadModel(uploadFile, uploadAutoNcnn);
    if (result.success) {
      showSnackbar(`Uploaded: ${result.filename || uploadFile.name}`);
      setUploadFile(null);
      resetUpload();
      refetch();
    } else {
      showSnackbar(result.error || 'Upload failed', 'error');
    }
  };

  const handleDownload = async (name) => {
    const modelName = name || downloadName.trim();
    if (!modelName) return;
    const result = await downloadModel(modelName, null, downloadAutoNcnn);
    if (result.success) {
      showSnackbar(`Downloaded: ${result.modelName || modelName}`);
      setDownloadName('');
      refetch();
    } else {
      showSnackbar(result.error || 'Download failed', 'error');
    }
  };

  // Active model derived info — runtime is populated once SmartTracker loads a model,
  // activeModelSummary comes from /api/models/active and is always available
  const activeBackend = runtime?.backend || activeModelSummary?.backend || 'ultralytics';
  const activeDevice = runtime?.effective_device || activeModelSummary?.device || '--';
  const activeTask = activeModelSummary?.task || '--';
  const activeName = activeModelSummary?.model_name || currentModel || '--';
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
        <Tooltip title="Rescan disk (rebuilds model registry from files on disk)">
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
                <Typography variant="subtitle2" fontWeight={600}>Active Model</Typography>
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
                  No models found. Upload or download a model below.
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
                      const isActive = m.id === activeModelId || m.name === activeName;
                      return (
                        <TableRow
                          key={m.id}
                          hover
                          sx={isActive ? { bgcolor: 'action.selected' } : undefined}
                        >
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12 }}>
                                {m.name || m.id}
                              </Typography>
                              {isActive && (
                                <Chip label="active" size="small" color="success" sx={{ fontSize: 10, height: 18 }} />
                              )}
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={detectModelType(m.name || m.id)}
                              size="small"
                              variant="outlined"
                              color={detectModelType(m.name || m.id) === 'Custom' ? 'secondary' : 'info'}
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
                              <Tooltip title={isActive ? 'Already active' : 'Activate'}>
                                <span>
                                  <IconButton
                                    size="small"
                                    color="primary"
                                    disabled={isActive || switching}
                                    onClick={() => handleActivate(m.path || m.id)}
                                  >
                                    <CheckCircleIcon sx={{ fontSize: 18 }} />
                                  </IconButton>
                                </span>
                              </Tooltip>
                              <Tooltip title="Delete">
                                <span>
                                  <IconButton
                                    size="small"
                                    color="error"
                                    disabled={isActive || deleting}
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
              <Tabs value={addTab} onChange={(_, v) => setAddTab(v)} sx={{ mb: 2 }}>
                <Tab label="Upload File" icon={<CloudUploadIcon sx={{ fontSize: 18 }} />} iconPosition="start" />
                <Tab label="Download by Name" icon={<CloudDownloadIcon sx={{ fontSize: 18 }} />} iconPosition="start" />
              </Tabs>

              {addTab === 0 && (
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
                      accept=".pt,.onnx,.engine,.mlmodel,.tflite"
                      onChange={(e) => {
                        setUploadFile(e.target.files?.[0] || null);
                        resetUpload();
                      }}
                    />
                  </Button>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={uploadAutoNcnn}
                        onChange={(e) => setUploadAutoNcnn(e.target.checked)}
                        size="small"
                      />
                    }
                    label={<Typography variant="body2">Auto-export NCNN after upload</Typography>}
                  />
                  {uploading && (
                    <LinearProgress variant="determinate" value={uploadProgress} sx={{ height: 6, borderRadius: 1 }} />
                  )}
                  <Button
                    variant="contained"
                    onClick={handleUpload}
                    disabled={!uploadFile || uploading}
                    startIcon={<CloudUploadIcon />}
                  >
                    {uploading ? `Uploading... ${uploadProgress}%` : 'Upload'}
                  </Button>
                </Box>
              )}

              {addTab === 1 && (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, maxWidth: 500 }}>
                  <TextField
                    label="Model Name"
                    placeholder="e.g. yolo11n.pt"
                    size="small"
                    value={downloadName}
                    onChange={(e) => setDownloadName(e.target.value)}
                    fullWidth
                  />
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {POPULAR_MODELS.map((name) => (
                      <Chip
                        key={name}
                        label={name}
                        size="small"
                        variant="outlined"
                        clickable
                        onClick={() => setDownloadName(name)}
                      />
                    ))}
                  </Box>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={downloadAutoNcnn}
                        onChange={(e) => setDownloadAutoNcnn(e.target.checked)}
                        size="small"
                      />
                    }
                    label={<Typography variant="body2">Auto-export NCNN after download</Typography>}
                  />
                  <Button
                    variant="contained"
                    onClick={() => handleDownload()}
                    disabled={!downloadName.trim() || downloading}
                    startIcon={<CloudDownloadIcon />}
                  >
                    {downloading ? 'Downloading...' : 'Download'}
                  </Button>
                </Box>
              )}
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
