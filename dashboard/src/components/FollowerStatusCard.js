// dashboard/src/components/FollowerStatusCard.js
import React, { memo, useMemo } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  LinearProgress,
  IconButton,
  Tooltip,
  Alert,
  Skeleton
} from '@mui/material';
import {
  FlightTakeoff,
  Speed,
  Rotate90DegreesCcw,
  Warning,
  Settings,
  PowerSettingsNew,
  PowerOff,
  Security,
  LocationOn,
  Info,
  CheckCircle,
  Error,
  Pause,
  PlayArrow
} from '@mui/icons-material';
import { useCurrentFollowerProfile } from '../hooks/useFollowerSchema';


const LoadingSkeleton = () => (
  <Card>
    <CardContent>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Skeleton variant="text" width={120} height={32} />
        <Skeleton variant="circular" width={32} height={32} />
      </Box>
      <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
        <Skeleton variant="rectangular" width={60} height={24} sx={{ borderRadius: 1 }} />
        <Skeleton variant="rectangular" width={80} height={24} sx={{ borderRadius: 1 }} />
        <Skeleton variant="rectangular" width={70} height={24} sx={{ borderRadius: 1 }} />
      </Box>
    </CardContent>
  </Card>
);

const FollowerStatusCard = memo(({ followerData = {} }) => {
  const { currentProfile, loading, error, isTransitioning } = useCurrentFollowerProfile();

  const memoizedData = useMemo(() => {
    if (!currentProfile) return null;
    
    const status = currentProfile.status; // 'engaged', 'configured', 'unknown'
    const isEngaged = status === 'engaged';
    const isConfigured = status === 'configured' || status === 'engaged';
    const fields = followerData.fields || currentProfile.current_field_values || {};
    const controlType = currentProfile.control_type;
    const isValid = currentProfile.validation_status;

    return {
      status,
      isEngaged,
      isConfigured,
      fields,
      controlType,
      isValid,
      displayName: currentProfile.display_name,
      description: currentProfile.description,
      message: currentProfile.message,
      availableFields: currentProfile.available_fields || [],
      mode: currentProfile.mode
    };
  }, [currentProfile, followerData]);

  // Memoize expensive target loss state calculations
  const targetLossInfo = useMemo(() => {
    if (!followerData.target_loss_handler) return null;

    const state = followerData.target_loss_handler.state;
    const getStateInfo = (state) => {
      switch (state) {
        case 'ACTIVE':
          return { icon: <CheckCircle fontSize="small" />, color: 'success.main', label: 'Active' };
        case 'LOST':
          return { icon: <Warning fontSize="small" />, color: 'warning.main', label: 'Target Lost' };
        case 'TIMEOUT':
          return { icon: <Error fontSize="small" />, color: 'error.main', label: 'Timeout' };
        case 'RECOVERING':
          return { icon: <PlayArrow fontSize="small" />, color: 'info.main', label: 'Recovering' };
        default:
          return { icon: <Info fontSize="small" />, color: 'textSecondary', label: state || 'Unknown' };
      }
    };

    return getStateInfo(state);
  }, [followerData.target_loss_handler]);

  // Get key fields to display based on control type
  const keyFields = useMemo(() => {
    if (!memoizedData) return [];
    
    const { controlType, availableFields } = memoizedData;
    
    let fieldDefinitions = [];
    if (controlType === 'velocity_body') {
      fieldDefinitions = [
        { name: 'vel_x', icon: <Speed fontSize="small" />, color: '#2196F3', unit: 'm/s' },
        { name: 'vel_y', icon: <Speed fontSize="small" />, color: '#4CAF50', unit: 'm/s' },
        { name: 'vel_z', icon: <FlightTakeoff fontSize="small" />, color: '#FF9800', unit: 'm/s' },
        { name: 'yaw_rate', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#9C27B0', unit: 'rad/s' }
      ];
    } else if (controlType === 'velocity_body_offboard') {
      fieldDefinitions = [
        { name: 'vel_body_fwd', icon: <Speed fontSize="small" />, color: '#2196F3', unit: 'm/s' },
        { name: 'vel_body_right', icon: <Speed fontSize="small" />, color: '#4CAF50', unit: 'm/s' },
        { name: 'vel_body_down', icon: <FlightTakeoff fontSize="small" />, color: '#FF9800', unit: 'm/s' },
        { name: 'yawspeed_deg_s', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#9C27B0', unit: '°/s' },
        { name: 'yaw_angle_deg', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#9C27B0', unit: '°' }
      ];
    } else if (controlType === 'attitude_rate') {
      fieldDefinitions = [
        { name: 'roll_rate', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#F44336', unit: 'rad/s' },
        { name: 'pitch_rate', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#2196F3', unit: 'rad/s' },
        { name: 'yaw_rate', icon: <Rotate90DegreesCcw fontSize="small" />, color: '#9C27B0', unit: 'rad/s' },
        { name: 'thrust', icon: <FlightTakeoff fontSize="small" />, color: '#FF5722', unit: '' }
      ];
    }
    
    return fieldDefinitions.filter(field => availableFields.includes(field.name));
  }, [memoizedData]);

  if (loading && !currentProfile) {
    return <LoadingSkeleton />;
  }

  if (error && !currentProfile) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Follower Status
          </Typography>
          <Alert severity="warning" size="small">
            {`Error: ${error}`}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (!memoizedData) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Follower Status
          </Typography>
          <Alert severity="info" size="small">
            No follower data available
          </Alert>
        </CardContent>
      </Card>
    );
  }

  const { isEngaged, isConfigured, fields, controlType, isValid, displayName, description, message } = memoizedData;

  // Status icon and color
  const getStatusIcon = () => {
    if (isEngaged) return <PowerSettingsNew />;
    if (isConfigured) return <PowerOff />;
    return <Warning />;
  };

  const getStatusColor = () => {
    if (isEngaged) return 'success';
    if (isConfigured) return 'warning';
    return 'error';
  };

  const getStatusLabel = () => {
    if (isEngaged) return 'Engaged';
    if (isConfigured) return 'Configured';
    return 'Unknown';
  };

  return (
    <Card sx={{ height: '100%', opacity: isTransitioning ? 0.7 : 1, transition: 'opacity 0.3s' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Follower Status
          </Typography>
          <Tooltip title="Go to Follower Page">
            <IconButton size="small" onClick={() => window.location.href = '/follower'}>
              <Settings />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Status Indicators */}
        <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
          <Chip
            label={getStatusLabel()}
            color={getStatusColor()}
            size="small"
            icon={getStatusIcon()}
          />
          <Chip
            label={displayName || 'Unknown'}
            color="primary"
            size="small"
          />
          <Chip
            label={controlType}
            variant="outlined"
            size="small"
          />
          <Chip
            label={isValid ? 'Valid' : 'Invalid'}
            color={isValid ? 'success' : 'error'}
            size="small"
          />
        </Box>

        {/* Status Message for Configured but not Engaged */}
        {!isEngaged && isConfigured && message && (
          <Alert severity="info" size="small" sx={{ mb: 2 }}>
            <Typography variant="caption">
              {message}
            </Typography>
          </Alert>
        )}

        {/* Show transition indicator */}
        {isTransitioning && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress size="small" />
            <Typography variant="caption" color="textSecondary">
              Switching profile...
            </Typography>
          </Box>
        )}

        {/* Key Setpoint Values - Similar to Tracker Key Fields */}
        {keyFields.length > 0 && (
          <Box sx={{ mt: 1, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
              {isEngaged ? 'Live Setpoints:' : 'Expected Fields:'}
            </Typography>
            {keyFields.map((field) => {
              const currentValue = isEngaged ? fields[field.name] : null;
              const displayValue = currentValue !== null && currentValue !== undefined 
                ? (typeof currentValue === 'number' ? currentValue.toFixed(3) : currentValue.toString())
                : (isEngaged ? '0.000' : 'Ready');
                
              return (
                <Box key={field.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                  <Box sx={{ color: field.color }}>
                    {field.icon}
                  </Box>
                  <Typography variant="caption" sx={{ minWidth: 60 }}>
                    {field.name.replace('_', ' ')}:
                  </Typography>
                  <Typography 
                    variant="caption" 
                    fontFamily="monospace" 
                    color={isEngaged ? 'primary' : 'textSecondary'}
                    fontWeight={isEngaged ? 'bold' : 'normal'}
                  >
                    {displayValue} {field.unit}
                  </Typography>
                </Box>
              );
            })}
            
            {/* Show control type info when configured but not engaged */}
            {!isEngaged && isConfigured && (
              <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: 'block' }}>
                Control: {controlType?.replace('_', ' ').toUpperCase()}
              </Typography>
            )}
          </Box>
        )}

        {/* Target Loss and Safety Status - Enhanced for gimbal followers */}
        {isEngaged && followerData.target_loss_handler && (
          <Box sx={{ mt: 2, pt: 1, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: 'block' }}>
              Target Loss & Safety:
            </Typography>

            {/* Target Loss State */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
              {(() => {
                const state = followerData.target_loss_handler.state;
                const getStateInfo = (state) => {
                  switch (state) {
                    case 'ACTIVE':
                      return { icon: <CheckCircle fontSize="small" />, color: 'success.main', label: 'Active' };
                    case 'LOST':
                      return { icon: <Warning fontSize="small" />, color: 'warning.main', label: 'Target Lost' };
                    case 'TIMEOUT':
                      return { icon: <Error fontSize="small" />, color: 'error.main', label: 'Timeout' };
                    case 'RECOVERING':
                      return { icon: <PlayArrow fontSize="small" />, color: 'info.main', label: 'Recovering' };
                    default:
                      return { icon: <Info fontSize="small" />, color: 'textSecondary', label: state || 'Unknown' };
                  }
                };
                const { icon, color, label } = getStateInfo(state);
                return (
                  <>
                    <Box sx={{ color }}>{icon}</Box>
                    <Typography variant="caption" sx={{ minWidth: 60 }}>
                      Target:
                    </Typography>
                    <Typography variant="caption" fontFamily="monospace" color={color} fontWeight="bold">
                      {label}
                    </Typography>
                  </>
                );
              })()}
            </Box>

            {/* Velocity Continuation */}
            {followerData.target_loss_handler.velocity_continuation_active && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Pause fontSize="small" color="warning" />
                <Typography variant="caption" sx={{ minWidth: 60 }}>
                  Continue:
                </Typography>
                <Typography variant="caption" fontFamily="monospace" color="warning.main">
                  {followerData.target_loss_handler.timeout_remaining?.toFixed(1) || '0.0'}s
                </Typography>
              </Box>
            )}

            {/* Safety Systems Status */}
            {followerData.safety_systems && (
              <>
                {(followerData.safety_systems.emergency_stop_active ||
                  followerData.safety_systems.rtl_triggered ||
                  followerData.safety_systems.altitude_safety_active ||
                  followerData.safety_systems.safety_violations_count > 0) && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                    <Security fontSize="small" color="warning" />
                    <Typography variant="caption" sx={{ minWidth: 60 }}>
                      Safety:
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                      {followerData.safety_systems.emergency_stop_active && (
                        <Chip size="small" label="E-STOP" color="error" sx={{ height: 16, fontSize: '0.6rem' }} />
                      )}
                      {followerData.safety_systems.rtl_triggered && (
                        <Chip size="small" label="RTL" color="warning" sx={{ height: 16, fontSize: '0.6rem' }} />
                      )}
                      {followerData.safety_systems.altitude_safety_active && (
                        <Chip size="small" label="ALT" color="info" sx={{ height: 16, fontSize: '0.6rem' }} />
                      )}
                      {followerData.safety_systems.safety_violations_count > 0 && (
                        <Chip
                          size="small"
                          label={`${followerData.safety_systems.safety_violations_count} violations`}
                          color="warning"
                          sx={{ height: 16, fontSize: '0.6rem' }}
                        />
                      )}
                    </Box>
                  </Box>
                )}
              </>
            )}

            {/* Circuit Breaker Status */}
            {followerData.circuit_breaker_active && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Security fontSize="small" color="warning" />
                <Typography variant="caption" sx={{ minWidth: 60 }}>
                  Mode:
                </Typography>
                <Chip
                  size="small"
                  label="TESTING"
                  color="warning"
                  sx={{ height: 16, fontSize: '0.6rem', fontWeight: 'bold' }}
                />
              </Box>
            )}

            {/* Performance Info */}
            {followerData.performance && (
              <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: 'block' }}>
                Success: {followerData.performance.success_rate_percent?.toFixed(1) || '0.0'}%
                ({followerData.performance.successful_transformations || 0}/{followerData.performance.total_follow_calls || 0})
              </Typography>
            )}
          </Box>
        )}

        {/* Description - Only show if not engaged and no setpoints */}
        {description && !isEngaged && keyFields.length === 0 && (
          <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
            {description}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
});

export default FollowerStatusCard;