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
  const { schema, loading: schemaLoading, error: schemaError } = useTrackerSchema();
  const { currentStatus, loading: statusLoading, error: statusError } = useCurrentTrackerStatus();
  const { availableTrackers, currentConfig, loading: configLoading, isChanging, changeTrackerType } = useTrackerSelection();

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
    const value = fieldData?.value;
    if (value === null || value === undefined) return null;

    if (Array.isArray(value)) {
      if (fieldName.includes('position') && value.length === 2) {
        return `(${value[0].toFixed(2)}, ${value[1].toFixed(2)})`;
      }
      if (fieldName === 'angular' && value.length === 3) {
        // Format gimbal angles: yaw, pitch, roll
        return `Y:${value[0].toFixed(1)}° P:${value[1].toFixed(1)}° R:${value[2].toFixed(1)}°`;
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

  // Prioritize gimbal-specific fields for GIMBAL_ANGLES data type
  const keyFields = dataType === 'GIMBAL_ANGLES'
    ? ['angular', 'confidence', 'position_2d'].filter(field => fields[field])
    : ['position_2d', 'confidence', 'bbox'].filter(field => fields[field]);

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
              {keyFields.slice(0, 2).map(fieldName => {
                const fieldData = fields[fieldName];
                const value = getKeyFieldValue(fieldName, fieldData);
                const icon = fieldName.includes('position') ? <GpsFixed fontSize="small" /> :
                           fieldName.includes('confidence') ? <Visibility fontSize="small" /> :
                           fieldName === 'angular' ? <TrackChanges fontSize="small" /> :
                           <Speed fontSize="small" />;

                return value ? (
                  <Box key={fieldName} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                    {icon}
                    <Typography variant="caption" sx={{ minWidth: 60 }}>
                      {fieldName === 'angular' && dataType === 'GIMBAL_ANGLES' ? 'angles' : fieldName.replace('_', ' ')}:
                    </Typography>
                    <Tooltip title={`Type: ${fieldData?.type}`}>
                      <Typography variant="caption" fontFamily="monospace" color="primary">
                        {value}
                      </Typography>
                    </Tooltip>
                  </Box>
                ) : null;
              })}
            </Box>
          )}

          {/* Gimbal-specific Status - Only for GIMBAL_ANGLES data type */}
          {isActive && dataType === 'GIMBAL_ANGLES' && currentStatus?.raw_data && (
            <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
              <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
                Gimbal Status:
              </Typography>

              {/* Connection Health Indicator */}
              {(currentStatus.raw_data.data_is_stale || currentStatus.raw_data.connection_health) && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <Warning fontSize="small" color={
                    currentStatus.raw_data.data_is_stale ? 'warning' : 'success'
                  } />
                  <Typography variant="caption" sx={{ minWidth: 60 }}>
                    health:
                  </Typography>
                  <Chip
                    size="small"
                    label={currentStatus.raw_data.data_is_stale ?
                      `STALE (${currentStatus.raw_data.data_age_seconds?.toFixed(1)}s)` :
                      (currentStatus.raw_data.connection_health?.toUpperCase() || 'GOOD')
                    }
                    color={currentStatus.raw_data.data_is_stale ? 'warning' :
                           currentStatus.raw_data.connection_health === 'poor' ? 'error' :
                           currentStatus.raw_data.connection_health === 'degraded' ? 'warning' : 'success'}
                    sx={{ height: 16, fontSize: '0.6rem' }}
                  />
                </Box>
              )}

              {/* Gimbal Tracking State */}
              {currentStatus.raw_data.tracking_status && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <TrackChanges fontSize="small" color={
                    currentStatus.raw_data.gimbal_tracking_active ? 'success' : 'warning'
                  } />
                  <Typography variant="caption" sx={{ minWidth: 60 }}>
                    mode:
                  </Typography>
                  <Chip
                    size="small"
                    label={currentStatus.raw_data.tracking_status}
                    color={currentStatus.raw_data.gimbal_tracking_active ? 'success' : 'warning'}
                    sx={{ height: 16, fontSize: '0.6rem' }}
                  />
                </Box>
              )}

              {/* Connection Status */}
              {currentStatus.raw_data.connection_status && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <CheckCircle fontSize="small" color={
                    currentStatus.raw_data.connection_status === 'RECEIVING' ? 'success' : 'warning'
                  } />
                  <Typography variant="caption" sx={{ minWidth: 60 }}>
                    UDP:
                  </Typography>
                  <Typography variant="caption" fontFamily="monospace" color={
                    currentStatus.raw_data.connection_status === 'RECEIVING' ? 'success.main' : 'warning.main'
                  }>
                    {currentStatus.raw_data.connection_status}
                  </Typography>
                </Box>
              )}

              {/* Coordinate System */}
              {currentStatus.raw_data.coordinate_system && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <GpsFixed fontSize="small" color="info" />
                  <Typography variant="caption" sx={{ minWidth: 60 }}>
                    coords:
                  </Typography>
                  <Typography variant="caption" fontFamily="monospace" color="info.main">
                    {currentStatus.raw_data.coordinate_system}
                  </Typography>
                </Box>
              )}

              {/* Failure Counter (when there are consecutive failures) */}
              {currentStatus.raw_data.consecutive_failures > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                  <Warning fontSize="small" color="warning" />
                  <Typography variant="caption" sx={{ fontSize: '0.65rem' }} color="warning.main">
                    {currentStatus.raw_data.consecutive_failures} consecutive failures
                  </Typography>
                </Box>
              )}
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