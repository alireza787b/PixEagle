// dashboard/src/components/TrackerDataDisplay.js
import React from 'react';
import { 
  Paper, 
  Typography, 
  Grid, 
  Box, 
  Chip, 
  Alert,
  Skeleton,
  Divider,
  Tooltip
} from '@mui/material';
import {
  Timeline as TimelineIcon,
  Visibility as VisibilityIcon,
  GpsFixed as GpsIcon,
  Speed as SpeedIcon,
  RadioButtonChecked as RadioIcon,
  RotateRight as RotateIcon,
  CameraAlt as CameraIcon,
  Straighten as RulerIcon,
  Wifi as WifiIcon,
  SignalWifiOff as SignalWifiOffIcon
} from '@mui/icons-material';
import { getTrackerRuntimeState } from '../utils/trackerRuntimeState';
import { formatLabel, formatOperatorValue } from '../utils/operatorFormat';

/**
 * Schema-driven tracker data display component
 * Automatically renders available tracker fields based on current data type
 */
const TrackerDataDisplay = ({ 
  currentStatus, 
  trackerData, 
  schema,
  loading = false,
  error = null,
  showSchema = true,
  compact = false
}) => {
  // Enhanced field type to icon mapping with gimbal support
  const getFieldIcon = (fieldName, fieldType) => {
    const iconMap = {
      // Position and tracking icons
      position_2d: <GpsIcon fontSize="small" />,
      position_3d: <GpsIcon fontSize="small" />,
      bbox: <CameraIcon fontSize="small" />,
      normalized_bbox: <CameraIcon fontSize="small" />,
      confidence: <VisibilityIcon fontSize="small" />,
      velocity: <SpeedIcon fontSize="small" />,
      timestamp: <TimelineIcon fontSize="small" />,

      // Gimbal-specific icons
      angular: <RotateIcon fontSize="small" />,
      angular_3d: <RotateIcon fontSize="small" />,
      gimbal_angles: <RotateIcon fontSize="small" />,
      tracking: <VisibilityIcon fontSize="small" />,
      tracking_status: <VisibilityIcon fontSize="small" />,
      system: <GpsIcon fontSize="small" />,
      coordinate_system: <GpsIcon fontSize="small" />,

      // Generic type-based mapping
      tuple_2d: <RulerIcon fontSize="small" />,
      tuple_3d: <RotateIcon fontSize="small" />,
      percentage: <VisibilityIcon fontSize="small" />
    };

    return iconMap[fieldName] || iconMap[fieldType] || <RadioIcon fontSize="small" />;
  };

  const formatFieldValue = (value, fieldType, fieldName, fieldData = {}) => (
    formatOperatorValue(value, {
      fieldName,
      fieldType,
      unit: fieldData.units || fieldData.unit,
      precision: fieldType === 'float' ? 3 : 2,
    })
  );

  // Get field display color based on importance and status
  const getFieldColor = (fieldName, fieldData, required = false) => {
    if (required) return 'primary';
    if (fieldName.includes('confidence')) return 'success';
    if (fieldName.includes('position')) return 'info';
    if (fieldName.includes('velocity')) return 'warning';

    // Special color coding for tracking status
    if (fieldName === 'tracking' || fieldName === 'tracking_status') {
      const value = fieldData?.value || '';
      if (value.includes('ACTIVE')) return 'success';
      if (value.includes('SELECTION')) return 'warning';
      if (value.includes('LOST')) return 'error';
      if (value.includes('DISABLED')) return 'default';
      return 'warning'; // For UNKNOWN or other states
    }

    return 'default';
  };

  if (loading) {
    return (
      <Paper elevation={2} sx={{ p: 2 }}>
        <Skeleton variant="text" width="60%" height={32} />
        <Box sx={{ mt: 2 }}>
          {[1, 2, 3, 4].map(i => (
            <Box key={i} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Skeleton variant="circular" width={24} height={24} sx={{ mr: 1 }} />
              <Skeleton variant="text" width="40%" height={24} sx={{ mr: 2 }} />
              <Skeleton variant="text" width="30%" height={24} />
            </Box>
          ))}
        </Box>
      </Paper>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Error loading tracker data: {error}
      </Alert>
    );
  }

  const runtimeState = getTrackerRuntimeState(currentStatus);

  if (!currentStatus || !runtimeState.hasOutput) {
    return (
      <Paper elevation={2} sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary" gutterBottom>
          No Tracker Output
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Start tracking or connect an external tracker to see real-time data fields.
        </Typography>
      </Paper>
    );
  }

  const fields = currentStatus.fields || {};
  const fieldEntries = Object.entries(fields);

  return (
      <Paper elevation={2} sx={{ p: compact ? 2 : 3, overflow: 'hidden' }}>
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Box
          sx={{
            display: 'flex',
            alignItems: { xs: 'flex-start', sm: 'center' },
            justifyContent: 'space-between',
            flexDirection: { xs: 'column', sm: 'row' },
            gap: 1,
            mb: 1,
          }}
        >
          <Typography variant={compact ? "subtitle1" : "h6"} component="h2">
            Tracker Telemetry
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Chip
              label={runtimeState.label}
              size="small"
              color={runtimeState.color}
              variant="filled"
            />
            <Chip
              label={runtimeState.followLabel}
              size="small"
              color={runtimeState.followColor}
              variant="outlined"
            />
            <Chip 
              label={currentStatus.tracker_type || 'Unknown'} 
              size="small" 
              color="primary"
              variant="outlined"
            />
            {currentStatus.smart_mode && (
              <Chip
                label="Smart Mode"
                size="small"
                color="secondary"
                variant="filled"
              />
            )}
            {/* Connection Status for External Trackers */}
            {currentStatus.raw_data?.connection_status && (
              <Chip
                icon={
                  currentStatus.raw_data.connection_status === 'receiving'
                    ? <WifiIcon fontSize="small" />
                    : <SignalWifiOffIcon fontSize="small" />
                }
                label={currentStatus.raw_data.connection_status.toUpperCase()}
                size="small"
                color={
                  currentStatus.raw_data.connection_status === 'receiving'
                    ? 'success'
                    : 'warning'
                }
                variant="filled"
              />
            )}
          </Box>
        </Box>
        
        {showSchema && currentStatus.data_type && (
          <Typography variant="caption" color="text.secondary">
            Data Type: <strong>{currentStatus.data_type.toUpperCase()}</strong>
          </Typography>
        )}
      </Box>

      {runtimeState.severity !== 'success' && (
        <Alert severity={runtimeState.severity} sx={{ mb: 2 }}>
          {runtimeState.message}
        </Alert>
      )}

      <Divider sx={{ mb: 2 }} />

      {/* Field List */}
      {fieldEntries.length === 0 ? (
        <Typography variant="body2" color="text.secondary" textAlign="center">
          No data fields available
        </Typography>
      ) : (
        <Grid
          container
          rowSpacing={compact ? 1 : 2}
          columnSpacing={{ xs: 0, sm: compact ? 1 : 2 }}
        >
          {fieldEntries.map(([fieldName, fieldData]) => {
            const isRequired = fieldData.schema?.required || false;
            const fieldType = fieldData.type || 'unknown';
            const displayName = fieldData.display_name || formatLabel(fieldName);
            const formattedValue = formatFieldValue(fieldData.value, fieldType, fieldName, fieldData);
            
            return (
              <Grid item xs={12} sm={compact ? 12 : 6} key={fieldName}>
                <Box 
                  sx={{ 
                    display: 'flex',
                    alignItems: 'flex-start',
                    p: compact ? 1 : 1.5,
                    bgcolor: 'background.default',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider'
                  }}
                >
                  <Box sx={{ mr: 1.5, color: 'text.secondary' }}>
                    {getFieldIcon(fieldName, fieldType)}
                  </Box>
                  
                  <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                      <Typography 
                        variant={compact ? "caption" : "body2"} 
                        fontWeight="medium"
                      >
                        {displayName}
                      </Typography>
                      {isRequired && (
                        <Chip
                          label="Required"
                          size="small"
                          color={getFieldColor(fieldName, fieldData, isRequired)}
                          variant="outlined"
                          sx={{ height: 16, fontSize: '0.7rem' }}
                        />
                      )}
                      {(fieldName === 'tracking' || fieldName === 'tracking_status') && (
                        <Chip
                          label={formattedValue}
                          size="small"
                          color={getFieldColor(fieldName, fieldData, false)}
                          variant="filled"
                          sx={{ height: 16, fontSize: '0.7rem', ml: 0.5 }}
                        />
                      )}
                    </Box>
                    
                    <Tooltip title={`Type: ${fieldType}`} placement="bottom-start">
                      <Typography 
                        variant={compact ? "caption" : "body2"} 
                        color="text.primary"
                        fontFamily="monospace"
                        sx={{ 
                          overflowWrap: 'anywhere',
                          fontSize: compact ? '0.7rem' : '0.875rem'
                        }}
                      >
                        {formattedValue}
                      </Typography>
                    </Tooltip>
                  </Box>
                </Box>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* Schema Information */}
      {showSchema && schema && currentStatus.data_type && (
        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">
            Schema-driven display • {fieldEntries.length} fields • Real-time updates
          </Typography>
        </Box>
      )}
    </Paper>
  );
};

export default TrackerDataDisplay;
