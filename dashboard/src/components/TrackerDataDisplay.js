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
  RadioButtonChecked as RadioIcon
} from '@mui/icons-material';

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
  // Field type to icon mapping
  const getFieldIcon = (fieldName, fieldType) => {
    const iconMap = {
      position_2d: <GpsIcon fontSize="small" />,
      position_3d: <GpsIcon fontSize="small" />,
      bbox: <RadioIcon fontSize="small" />,
      normalized_bbox: <RadioIcon fontSize="small" />,
      confidence: <VisibilityIcon fontSize="small" />,
      velocity: <SpeedIcon fontSize="small" />,
      timestamp: <TimelineIcon fontSize="small" />
    };
    
    return iconMap[fieldName] || iconMap[fieldType] || <RadioIcon fontSize="small" />;
  };

  // Field value formatter
  const formatFieldValue = (value, fieldType, fieldName) => {
    if (value === null || value === undefined) return 'N/A';
    
    switch (fieldType) {
      case 'tuple':
      case 'list':
        if (Array.isArray(value)) {
          if (fieldName.includes('position') && value.length === 2) {
            return `(${value[0].toFixed(3)}, ${value[1].toFixed(3)})`;
          }
          if (fieldName === 'bbox' && value.length === 4) {
            return `[${value[0]}, ${value[1]}, ${value[2]}, ${value[3]}]`;
          }
          return `[${value.map(v => typeof v === 'number' ? v.toFixed(3) : v).join(', ')}]`;
        }
        break;
      case 'float':
        return typeof value === 'number' ? value.toFixed(4) : value;
      case 'int':
        return value.toString();
      case 'str':
      case 'string':
        return value;
      default:
        if (typeof value === 'object') {
          return JSON.stringify(value, null, 2);
        }
        return value.toString();
    }
    return value;
  };

  // Get field display color based on importance
  const getFieldColor = (fieldName, required = false) => {
    if (required) return 'primary';
    if (fieldName.includes('confidence')) return 'success';
    if (fieldName.includes('position')) return 'info';
    if (fieldName.includes('velocity')) return 'warning';
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

  if (!currentStatus || !currentStatus.active) {
    return (
      <Paper elevation={2} sx={{ p: 3, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary" gutterBottom>
          No Active Tracker
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Start tracking to see real-time data fields
        </Typography>
      </Paper>
    );
  }

  const fields = currentStatus.fields || {};
  const fieldEntries = Object.entries(fields);

  return (
    <Paper elevation={2} sx={{ p: compact ? 2 : 3 }}>
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant={compact ? "subtitle1" : "h6"} component="h2">
            Tracker Data Fields
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
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
          </Box>
        </Box>
        
        {showSchema && currentStatus.data_type && (
          <Typography variant="caption" color="text.secondary">
            Data Type: <strong>{currentStatus.data_type.toUpperCase()}</strong>
          </Typography>
        )}
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Field List */}
      {fieldEntries.length === 0 ? (
        <Typography variant="body2" color="text.secondary" textAlign="center">
          No data fields available
        </Typography>
      ) : (
        <Grid container spacing={compact ? 1 : 2}>
          {fieldEntries.map(([fieldName, fieldData]) => {
            const isRequired = fieldData.schema?.required || false;
            const fieldType = fieldData.type || 'unknown';
            const displayName = fieldData.display_name || fieldName.replace('_', ' ');
            const formattedValue = formatFieldValue(fieldData.value, fieldType, fieldName);
            
            return (
              <Grid item xs={12} sm={compact ? 12 : 6} key={fieldName}>
                <Box 
                  sx={{ 
                    display: 'flex', 
                    alignItems: 'center', 
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
                  
                  <Box sx={{ flexGrow: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
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
                          color={getFieldColor(fieldName, isRequired)}
                          variant="outlined"
                          sx={{ height: 16, fontSize: '0.7rem' }}
                        />
                      )}
                    </Box>
                    
                    <Tooltip title={`Type: ${fieldType}`} placement="bottom-start">
                      <Typography 
                        variant={compact ? "caption" : "body2"} 
                        color="text.primary"
                        fontFamily="monospace"
                        sx={{ 
                          wordBreak: 'break-all',
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