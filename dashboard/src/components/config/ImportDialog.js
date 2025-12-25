// dashboard/src/components/config/ImportDialog.js
import React, { useState, useRef, useCallback } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Box, Typography, CircularProgress, Alert, Stepper,
  Step, StepLabel, Paper, FormControl, FormLabel, RadioGroup,
  FormControlLabel, Radio, Chip
} from '@mui/material';
import {
  FileUpload, CloudUpload, Preview, CheckCircle,
  Warning, MergeType, SwapHoriz
} from '@mui/icons-material';
import axios from 'axios';
import yaml from 'js-yaml';

import { endpoints } from '../../services/apiEndpoints';
import DiffViewer from './DiffViewer';

/**
 * ImportDialog - Dialog for importing configuration with diff preview
 *
 * Steps:
 * 1. Upload YAML file
 * 2. Preview differences
 * 3. Select changes (optional)
 * 4. Confirm import
 */
const ImportDialog = ({ open, onClose }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [file, setFile] = useState(null);
  const [parsedConfig, setParsedConfig] = useState(null);
  const [differences, setDifferences] = useState([]);
  const [selectedChanges, setSelectedChanges] = useState([]);
  const [mergeMode, setMergeMode] = useState('merge');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [importResult, setImportResult] = useState(null);

  const fileInputRef = useRef(null);

  const steps = ['Upload File', 'Preview Changes', 'Confirm Import'];

  // Reset state when dialog opens
  const handleOpen = useCallback(() => {
    setActiveStep(0);
    setFile(null);
    setParsedConfig(null);
    setDifferences([]);
    setSelectedChanges([]);
    setMergeMode('merge');
    setError(null);
    setImportResult(null);
  }, []);

  React.useEffect(() => {
    if (open) {
      handleOpen();
    }
  }, [open, handleOpen]);

  const handleFileSelect = async (event) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    setError(null);
    setLoading(true);

    try {
      // Read and parse file
      const text = await selectedFile.text();
      let parsed;

      try {
        parsed = yaml.load(text);
      } catch (parseError) {
        throw new Error(`Invalid YAML: ${parseError.message}`);
      }

      if (!parsed || typeof parsed !== 'object') {
        throw new Error('Invalid configuration format');
      }

      setFile(selectedFile);
      setParsedConfig(parsed);

      // Get diff from backend
      const response = await axios.post(endpoints.configDiff, {
        compare_config: parsed
      });

      if (response.data.success) {
        const diffs = response.data.differences || [];
        setDifferences(diffs);
        setSelectedChanges([...diffs]); // Select all by default
        setActiveStep(1);
      } else {
        throw new Error(response.data.error || 'Failed to compare configurations');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();

    const droppedFile = event.dataTransfer?.files?.[0];
    if (droppedFile) {
      // Simulate file input change
      const dataTransfer = new DataTransfer();
      dataTransfer.items.add(droppedFile);
      if (fileInputRef.current) {
        fileInputRef.current.files = dataTransfer.files;
        handleFileSelect({ target: { files: dataTransfer.files } });
      }
    }
  }, []);

  const handleDragOver = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const handleImport = async () => {
    setLoading(true);
    setError(null);

    try {
      // Build import config based on selection
      let importConfig = parsedConfig;

      // If not all selected, filter to selected changes only
      if (selectedChanges.length < differences.length) {
        importConfig = {};
        selectedChanges.forEach(change => {
          if (!importConfig[change.section]) {
            importConfig[change.section] = {};
          }
          importConfig[change.section][change.parameter] = change.new_value;
        });
      }

      const response = await axios.post(endpoints.configImport, {
        data: importConfig,
        merge_mode: mergeMode
      });

      if (response.data.success) {
        setImportResult({
          success: true,
          changes: response.data.changes_applied || selectedChanges.length
        });
        setActiveStep(2);
      } else {
        throw new Error(response.data.error || 'Import failed');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      onClose(importResult?.success || false);
    }
  };

  const handleBack = () => {
    setActiveStep(prev => Math.max(0, prev - 1));
    setError(null);
  };

  const renderUploadStep = () => (
    <Box>
      {/* Merge mode selection */}
      <FormControl component="fieldset" sx={{ mb: 3 }}>
        <FormLabel component="legend">Import Mode</FormLabel>
        <RadioGroup
          value={mergeMode}
          onChange={(e) => setMergeMode(e.target.value)}
        >
          <FormControlLabel
            value="merge"
            control={<Radio />}
            label={
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <MergeType fontSize="small" />
                  <Typography>Merge (Recommended)</Typography>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Only update specified parameters, keep existing values for others
                </Typography>
              </Box>
            }
          />
          <FormControlLabel
            value="replace"
            control={<Radio />}
            label={
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <SwapHoriz fontSize="small" />
                  <Typography>Replace</Typography>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  Replace entire sections with imported values
                </Typography>
              </Box>
            }
          />
        </RadioGroup>
      </FormControl>

      {/* Drop zone */}
      <Paper
        variant="outlined"
        sx={{
          p: 4,
          textAlign: 'center',
          border: '2px dashed',
          borderColor: 'divider',
          bgcolor: 'action.hover',
          cursor: 'pointer',
          transition: 'all 0.2s',
          '&:hover': {
            borderColor: 'primary.main',
            bgcolor: 'action.selected'
          }
        }}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".yaml,.yml"
          style={{ display: 'none' }}
          onChange={handleFileSelect}
        />

        {loading ? (
          <CircularProgress />
        ) : (
          <>
            <CloudUpload sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              Drop YAML file here
            </Typography>
            <Typography variant="body2" color="text.secondary">
              or click to browse
            </Typography>
            <Typography variant="caption" color="text.disabled" sx={{ mt: 1, display: 'block' }}>
              Supported: .yaml, .yml
            </Typography>
          </>
        )}
      </Paper>

      {file && (
        <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Chip
            label={file.name}
            onDelete={() => {
              setFile(null);
              setParsedConfig(null);
            }}
            size="small"
          />
          <Typography variant="caption" color="text.secondary">
            {(file.size / 1024).toFixed(1)} KB
          </Typography>
        </Box>
      )}
    </Box>
  );

  const renderPreviewStep = () => (
    <Box>
      {differences.length === 0 ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          No differences found. The imported configuration matches current settings.
        </Alert>
      ) : (
        <>
          <Alert severity="info" sx={{ mb: 2 }}>
            Review the changes below. You can deselect specific changes you don't want to apply.
          </Alert>

          <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
            <DiffViewer
              differences={differences}
              selectable={true}
              selectedChanges={selectedChanges}
              onSelectionChange={setSelectedChanges}
            />
          </Box>
        </>
      )}
    </Box>
  );

  const renderConfirmStep = () => (
    <Box sx={{ textAlign: 'center', py: 3 }}>
      {importResult?.success ? (
        <>
          <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
          <Typography variant="h5" gutterBottom>
            Import Successful
          </Typography>
          <Typography color="text.secondary">
            {importResult.changes} parameter(s) have been updated.
          </Typography>
          <Alert severity="info" sx={{ mt: 3, textAlign: 'left' }}>
            <Typography variant="body2">
              A backup was created before import. You can restore it from the History dialog if needed.
            </Typography>
          </Alert>
        </>
      ) : (
        <>
          <Warning sx={{ fontSize: 64, color: 'error.main', mb: 2 }} />
          <Typography variant="h5" gutterBottom>
            Import Failed
          </Typography>
          <Typography color="error">
            {error || 'An unknown error occurred'}
          </Typography>
        </>
      )}
    </Box>
  );

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FileUpload />
        Import Configuration
      </DialogTitle>

      <DialogContent>
        {/* Stepper */}
        <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {/* Error display */}
        {error && activeStep < 2 && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Step content */}
        {activeStep === 0 && renderUploadStep()}
        {activeStep === 1 && renderPreviewStep()}
        {activeStep === 2 && renderConfirmStep()}
      </DialogContent>

      <DialogActions>
        {activeStep === 0 && (
          <Button onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
        )}

        {activeStep === 1 && (
          <>
            <Button onClick={handleBack} disabled={loading}>
              Back
            </Button>
            <Button onClick={handleClose} disabled={loading}>
              Cancel
            </Button>
            <Button
              variant="contained"
              onClick={handleImport}
              disabled={loading || selectedChanges.length === 0}
              startIcon={loading ? <CircularProgress size={16} /> : <FileUpload />}
            >
              {loading ? 'Importing...' : `Import ${selectedChanges.length} Changes`}
            </Button>
          </>
        )}

        {activeStep === 2 && (
          <Button
            variant="contained"
            onClick={handleClose}
          >
            {importResult?.success ? 'Done' : 'Close'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default ImportDialog;
