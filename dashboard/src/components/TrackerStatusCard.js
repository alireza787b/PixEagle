// dashboard/src/components/TrackerStatusCard.js
import React from 'react';
import { 
  Card, 
  CardContent, 
  Typography, 
  Box, 
  Chip, 
  Skeleton,
  Tooltip
} from '@mui/material';
import { 
  TrackChanges,
  Visibility,
  Speed,
  GpsFixed,
  CheckCircle,
  Warning
} from '@mui/icons-material';
import { useTrackerSchema, useCurrentTrackerStatus, useTrackerSelection } from '../hooks/useTrackerSchema';

const TrackerStatusCard = () => {
  const { loading: schemaLoading, error: schemaError } = useTrackerSchema();
  const { currentStatus, loading: statusLoading, error: statusError } = useCurrentTrackerStatus();
  const { availableTrackers, currentConfig, loading: configLoading } = useTrackerSelection();

  const loading = schemaLoading || statusLoading || configLoading;
  const error = schemaError || statusError;

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <TrackChanges color="action" />
            <Typography variant="h6">Tracker Status</Typography>
          </Box>
          <Skeleton variant="text" width="80%" height={24} />
          <Skeleton variant="text" width="60%" height={20} sx={{ mt: 1 }} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Warning color="error" />
            <Typography variant="h6">Tracker Status</Typography>
          </Box>
          <Typography variant="body2" color="error">
            Error: {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // Determine if tracker is currently active
  const isActive = currentStatus && currentStatus.active;
  
  // Use active tracker info if available, otherwise use configured info
  const trackerType = isActive 
    ? (currentStatus?.tracker_type || 'Unknown')
    : (currentConfig?.configured_tracker || 'CSRT');
    
  const dataType = isActive 
    ? (currentStatus?.data_type?.toUpperCase() || 'N/A')
    : (currentConfig?.expected_data_type || 'POSITION_2D');
    
  const smartMode = isActive 
    ? (currentStatus?.smart_mode || false)
    : (currentConfig?.smart_mode_active || false);
    
  const fields = currentStatus?.fields || {};
  const fieldCount = Object.keys(fields).length;
  
  // Get tracker info from available trackers for configured mode
  const configuredTrackerInfo = availableTrackers?.available_trackers?.[trackerType] || {};

  // Get key field values for compact display
  const getKeyFieldValue = (fieldName, fieldData) => {
    // Handle special fields from raw_data (dynamic, schema-based)
    if (fieldName === 'system' && currentStatus?.raw_data?.system) {
      return currentStatus.raw_data.system;
    }

    if (fieldName === 'tracking' && currentStatus?.raw_data?.tracking) {
      return currentStatus.raw_data.tracking;
    }

    if (fieldName === 'coordinate_system' && currentStatus?.raw_data?.coordinate_system) {
      return currentStatus.raw_data.coordinate_system.toUpperCase();
    }

    if (fieldName === 'tracking_status' && currentStatus?.raw_data?.tracking_status) {
      return currentStatus.raw_data.tracking_status;
    }

    const value = fieldData?.value;
    if (value === null || value === undefined) return null;

    if (Array.isArray(value)) {
      if (fieldName.includes('position') && value.length === 2) {
        return `(${value[0].toFixed(2)}, ${value[1].toFixed(2)})`;
      }
      if (fieldName === 'angular' && value.length === 3) {
        // Format gimbal angles: yaw, pitch, roll with clear labels
        return `🎯 Y:${value[0].toFixed(1)}° P:${value[1].toFixed(1)}° R:${value[2].toFixed(1)}°`;
      }
      if (fieldName === 'angular' && value.length === 2) {
        // Format angular bearing/elevation
        return `B:${value[0].toFixed(1)}° E:${value[1].toFixed(1)}°`;
      }
      return value.join(', ');
    }

    if (typeof value === 'number') {
      return value.toFixed(3);
    }

    return value.toString();
  };

  // Schema-based field selection - dynamic based on data type and available raw_data
  const getAvailableFields = () => {
    if (dataType === 'GIMBAL_ANGLES') {
      // For gimbal trackers, prioritize gimbal-specific fields
      const gimbalFields = ['angular', 'tracking', 'system', 'confidence'];
      return gimbalFields.filter(field => {
        // Check if field exists in fields object or raw_data
        return fields[field] ||
               (currentStatus?.raw_data &&
                (currentStatus.raw_data[field] !== undefined &&
                 currentStatus.raw_data[field] !== null));
      });
    } else {
      // For standard trackers, use position-based fields
      return ['position_2d', 'confidence', 'bbox'].filter(field => fields[field]);
    }
  };

  const keyFields = getAvailableFields();

  return (
    <Card>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <TrackChanges color={isActive ? 'primary' : 'action'} />
          <Typography variant="h6">Tracker Status</Typography>
          <Chip 
            label={isActive ? 'Active' : 'Inactive'}
            color={isActive ? 'success' : 'default'}
            size="small"
            icon={isActive ? <CheckCircle /> : <Warning />}
          />
        </Box>

        {/* Status Info */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2" color="textSecondary">
              Type:
            </Typography>
            <Chip 
              label={configuredTrackerInfo.display_name || trackerType}
              color={smartMode ? 'secondary' : 'primary'}
              size="small"
              variant={isActive ? "filled" : "outlined"}
            />
          </Box>

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2" color="textSecondary">
              Schema:
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body2" fontWeight="medium">
                {dataType} {isActive ? `(${fieldCount} fields)` : '(Expected)'}
              </Typography>
              {isActive && currentStatus?.data_type === 'VELOCITY_AWARE' && (
                <Tooltip title="Schema enhanced by Kalman estimator providing velocity data">
                  <Chip
                    size="small"
                    label="EST"
                    color="info"
                    sx={{ height: 16, fontSize: '0.6rem', fontWeight: 'bold' }}
                  />
                </Tooltip>
              )}
            </Box>
          </Box>
          
          {/* Show configured info when inactive */}
          {!isActive && configuredTrackerInfo.description && (
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
                Ready to Start:
              </Typography>
              <Typography variant="caption" color="text.primary">
                {configuredTrackerInfo.description}
              </Typography>
              {configuredTrackerInfo.suitable_for && (
                <Box sx={{ mt: 0.5 }}>
                  <Typography variant="caption" color="textSecondary">
                    Best for: {configuredTrackerInfo.suitable_for.slice(0, 2).join(', ')}
                  </Typography>
                </Box>
              )}
            </Box>
          )}

          {/* Key Field Values - Only when active */}
          {isActive && keyFields.length > 0 && (
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
                Live Data:
              </Typography>
              {keyFields.slice(0, 4).map(fieldName => {
                const fieldData = fields[fieldName];
                const value = getKeyFieldValue(fieldName, fieldData);

                // Skip if no value available
                if (!value) return null;

                // Get appropriate icon and label - schema-aware
                const getFieldInfo = (field) => {
                  switch (field) {
                    case 'angular':
                      return { icon: <TrackChanges fontSize="small" />, label: 'angles' };
                    case 'tracking':
                      return { icon: <CheckCircle fontSize="small" />, label: 'status' };
                    case 'system':
                      return { icon: <GpsFixed fontSize="small" />, label: 'system' };
                    case 'coordinate_system':
                      return { icon: <GpsFixed fontSize="small" />, label: 'coords' };
                    case 'tracking_status':
                      return { icon: <TrackChanges fontSize="small" />, label: 'mode' };
                    case 'confidence':
                      return { icon: <Visibility fontSize="small" />, label: 'confidence' };
                    case 'position_2d':
                      return { icon: <GpsFixed fontSize="small" />, label: 'position' };
                    case 'bbox':
                      return { icon: <Speed fontSize="small" />, label: 'bbox' };
                    default:
                      return { icon: <Speed fontSize="small" />, label: field.replace('_', ' ') };
                  }
                };

                const { icon, label } = getFieldInfo(fieldName);

                return (
                  <Box key={fieldName} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                    {icon}
                    <Typography variant="caption" sx={{ minWidth: 60 }}>
                      {label}:
                    </Typography>
                    <Typography variant="caption" fontFamily="monospace" color="primary">
                      {value}
                    </Typography>
                  </Box>
                );
              })}
            </Box>
          )}

          {/* Connection Health - Only show when degraded/stale */}
          {isActive && dataType === 'GIMBAL_ANGLES' && currentStatus?.raw_data &&
           (currentStatus.raw_data.data_is_stale || currentStatus.raw_data.connection_health === 'degraded' || currentStatus.raw_data.connection_health === 'poor') && (
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Warning fontSize="small" color="warning" />
                <Typography variant="caption" color="warning.main">
                  {currentStatus.raw_data.data_is_stale
                    ? `Data stale (${currentStatus.raw_data.data_age_seconds?.toFixed(1)}s)`
                    : `Connection ${currentStatus.raw_data.connection_health}`}
                </Typography>
              </Box>
            </Box>
          )}

          {/* Estimator Status Enhancement */}
          {currentStatus && currentStatus.raw_data && (
            <Box sx={{ mt: 1.5, pt: 1, borderTop: 1, borderColor: 'divider' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Speed fontSize="small" color={currentStatus.raw_data.estimator_providing_velocity ? 'success' : 'disabled'} />
                <Typography variant="caption" color="text.secondary">
                  Estimator:
                </Typography>
                <Chip
                  size="small"
                  label={currentStatus.raw_data.estimator_enabled ? 
                    (currentStatus.raw_data.estimator_providing_velocity ? 'ACTIVE' : 'STANDBY') : 'OFF'
                  }
                  color={currentStatus.raw_data.estimator_providing_velocity ? 'success' : 
                         currentStatus.raw_data.estimator_enabled ? 'warning' : 'default'}
                  sx={{ height: 18, fontSize: '0.7rem' }}
                />
                {currentStatus.raw_data.estimator_providing_velocity && (
                  <Typography variant="caption" fontFamily="monospace" color="success.main">
                    v={currentStatus.raw_data.velocity_magnitude}
                  </Typography>
                )}
              </Box>
              {currentStatus.data_type === 'VELOCITY_AWARE' && (
                <Typography variant="caption" color="info.main" sx={{ fontSize: '0.65rem', fontStyle: 'italic' }}>
                  Schema enhanced by Kalman estimator
                </Typography>
              )}
            </Box>
          )}
        </Box>
      </CardContent>
    </Card>
  );
};

export default TrackerStatusCard;