// dashboard/src/components/config/ExportDialog.js
import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, FormControl, FormLabel, RadioGroup, FormControlLabel,
  Radio, Box, Typography, CircularProgress, Alert, Chip,
  List, ListItem, ListItemText, Divider
} from '@mui/material';
import {
  FileDownload, Description, CompareArrows, AllInclusive
} from '@mui/icons-material';
import axios from 'axios';
import yaml from 'js-yaml';

import { endpoints } from '../../services/apiEndpoints';
import { useConfigDiff } from '../../hooks/useConfig';

/**
 * ExportDialog - Dialog for exporting configuration
 *
 * Features:
 * - Export full config or changes-only
 * - Preview what will be exported
 * - Download as YAML file
 */
const ExportDialog = ({ open, onClose, changesCount = 0 }) => {
  const [exportMode, setExportMode] = useState('full');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);

  const { diff, loading: diffLoading } = useConfigDiff();

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setExportMode('full');
      setError(null);
      setPreview(null);
    }
  }, [open]);

  // Generate preview when mode changes
  useEffect(() => {
    if (exportMode === 'changes' && diff) {
      // Group changes by section
      const grouped = diff.reduce((acc, d) => {
        if (!acc[d.section]) {
          acc[d.section] = [];
        }
        acc[d.section].push(d);
        return acc;
      }, {});
      setPreview(grouped);
    } else {
      setPreview(null);
    }
  }, [exportMode, diff]);

  const handleExport = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (exportMode === 'changes') {
        params.append('changes_only', 'true');
      }

      const response = await axios.get(
        `${endpoints.configExport}?${params.toString()}`
      );

      if (!response.data.success) {
        throw new Error(response.data.error || 'Export failed');
      }

      // Convert JSON config to YAML with header comment
      const header = `# PixEagle Configuration Export\n# Exported: ${new Date().toISOString()}\n# Mode: ${exportMode === 'changes' ? 'Changes only' : 'Full configuration'}\n\n`;
      const yamlContent = header + yaml.dump(response.data.config, {
        indent: 2,
        lineWidth: 120,
        noRefs: true,
        sortKeys: true
      });

      // Create download link
      const blob = new Blob([yamlContent], { type: 'application/x-yaml' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      // Generate filename with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const suffix = exportMode === 'changes' ? '_changes' : '';
      link.download = `pixeagle_config${suffix}_${timestamp}.yaml`;

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      onClose(true);
    } catch (err) {
      setError(err.message || 'Failed to export configuration');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    if (!loading) {
      onClose(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <FileDownload />
        Export Configuration
      </DialogTitle>

      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <FormControl component="fieldset" sx={{ mb: 3 }}>
          <FormLabel component="legend">Export Mode</FormLabel>
          <RadioGroup
            value={exportMode}
            onChange={(e) => setExportMode(e.target.value)}
          >
            <FormControlLabel
              value="full"
              control={<Radio />}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <AllInclusive fontSize="small" />
                  <Box>
                    <Typography variant="body1">Full Configuration</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Export all parameters including defaults
                    </Typography>
                  </Box>
                </Box>
              }
            />
            <FormControlLabel
              value="changes"
              control={<Radio />}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CompareArrows fontSize="small" />
                  <Box>
                    <Typography variant="body1">
                      Changes Only
                      {changesCount > 0 && (
                        <Chip
                          label={changesCount}
                          size="small"
                          color="warning"
                          sx={{ ml: 1 }}
                        />
                      )}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Export only parameters that differ from defaults
                    </Typography>
                  </Box>
                </Box>
              }
              disabled={changesCount === 0}
            />
          </RadioGroup>
        </FormControl>

        {/* Preview for changes-only mode */}
        {exportMode === 'changes' && preview && (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Changes to Export:
            </Typography>
            <Box
              sx={{
                maxHeight: 200,
                overflow: 'auto',
                border: 1,
                borderColor: 'divider',
                borderRadius: 1,
                bgcolor: 'background.default'
              }}
            >
              {diffLoading ? (
                <Box sx={{ p: 2, textAlign: 'center' }}>
                  <CircularProgress size={24} />
                </Box>
              ) : (
                <List dense disablePadding>
                  {Object.entries(preview).map(([section, changes], idx) => (
                    <React.Fragment key={section}>
                      {idx > 0 && <Divider />}
                      <ListItem sx={{ bgcolor: 'action.hover' }}>
                        <ListItemText
                          primary={section}
                          primaryTypographyProps={{
                            variant: 'subtitle2',
                            fontWeight: 'bold'
                          }}
                          secondary={`${changes.length} change(s)`}
                        />
                      </ListItem>
                      {changes.map((change) => (
                        <ListItem key={`${section}.${change.parameter}`} sx={{ pl: 4 }}>
                          <ListItemText
                            primary={change.parameter}
                            primaryTypographyProps={{
                              variant: 'body2',
                              fontFamily: 'monospace'
                            }}
                            secondary={
                              <Typography
                                component="span"
                                variant="caption"
                                sx={{ fontFamily: 'monospace' }}
                              >
                                {String(change.old_value).slice(0, 20)} → {String(change.new_value).slice(0, 20)}
                              </Typography>
                            }
                          />
                        </ListItem>
                      ))}
                    </React.Fragment>
                  ))}
                </List>
              )}
            </Box>
          </Box>
        )}

        {exportMode === 'changes' && changesCount === 0 && (
          <Alert severity="info">
            No changes to export. All parameters match their default values.
          </Alert>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleExport}
          disabled={loading || (exportMode === 'changes' && changesCount === 0)}
          startIcon={loading ? <CircularProgress size={16} /> : <FileDownload />}
        >
          {loading ? 'Exporting...' : 'Export'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ExportDialog;
