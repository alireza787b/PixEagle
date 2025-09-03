// dashboard/src/components/EnhancedTrackerStatus.js

import React, { useState, useEffect } from 'react';
import { Card, CardContent, Typography, Chip, Box, Grid, LinearProgress } from '@mui/material';

const EnhancedTrackerStatus = ({ trackerData }) => {
  const [enhancedData, setEnhancedData] = useState(null);

  // Extract enhanced tracker data
  useEffect(() => {
    if (trackerData && trackerData.length > 0) {
      const latest = trackerData[trackerData.length - 1];
      
      // Support both legacy and enhanced formats
      if (latest.tracker_data) {
        setEnhancedData(latest.tracker_data);
      } else {
        // Convert legacy format to enhanced-like structure
        setEnhancedData({
          data_type: 'position_2d',
          tracker_id: 'legacy_tracker',
          tracking_active: latest.tracker_started || false,
          confidence: latest.confidence || null,
          legacy_mode: true,
          position_2d: latest.center,
          normalized_bbox: latest.bounding_box
        });
      }
    }
  }, [trackerData]);

  if (!enhancedData) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Tracker Status
          </Typography>
          <Typography color="textSecondary">
            No tracker data available
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const getDataTypeInfo = (dataType) => {
    const typeInfo = {
      'position_2d': { label: '2D Position', color: 'primary', icon: '📍' },
      'position_3d': { label: '3D Position', color: 'secondary', icon: '🎯' },
      'angular': { label: 'Angular', color: 'warning', icon: '🧭' },
      'bbox_confidence': { label: 'Bbox + Confidence', color: 'info', icon: '🔲' },
      'velocity_aware': { label: 'With Velocity', color: 'success', icon: '⚡' },
      'multi_target': { label: 'Multi-Target', color: 'error', icon: '🎪' },
      'external': { label: 'External Source', color: 'default', icon: '📡' }
    };
    
    return typeInfo[dataType] || { label: dataType, color: 'default', icon: '❓' };
  };

  const typeInfo = getDataTypeInfo(enhancedData.data_type);

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Enhanced Tracker Status
        </Typography>
        
        <Grid container spacing={2}>
          {/* Tracker Type and Status */}
          <Grid item xs={12} sm={6}>
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              <span style={{ fontSize: '18px' }}>{typeInfo.icon}</span>
              <Chip 
                label={typeInfo.label} 
                color={typeInfo.color}
                variant="outlined"
                size="small"
              />
            </Box>
            
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              <Chip 
                label={enhancedData.tracking_active ? 'Active' : 'Inactive'}
                color={enhancedData.tracking_active ? 'success' : 'error'}
                size="small"
              />
              {enhancedData.legacy_mode && (
                <Chip 
                  label="Legacy Mode" 
                  color="warning"
                  variant="outlined"
                  size="small"
                />
              )}
            </Box>
          </Grid>

          {/* Tracker ID */}
          <Grid item xs={12} sm={6}>
            <Typography variant="body2" color="textSecondary" gutterBottom>
              Tracker ID
            </Typography>
            <Typography variant="body2" style={{ fontFamily: 'monospace' }}>
              {enhancedData.tracker_id}
            </Typography>
          </Grid>

          {/* Confidence */}
          {enhancedData.confidence !== null && (
            <Grid item xs={12}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Confidence: {(enhancedData.confidence * 100).toFixed(1)}%
              </Typography>
              <LinearProgress 
                variant="determinate" 
                value={enhancedData.confidence * 100}
                color={enhancedData.confidence > 0.7 ? 'success' : enhancedData.confidence > 0.4 ? 'warning' : 'error'}
              />
            </Grid>
          )}

          {/* Position Data */}
          {enhancedData.position_2d && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                2D Position
              </Typography>
              <Typography variant="body2" style={{ fontFamily: 'monospace' }}>
                ({enhancedData.position_2d[0].toFixed(3)}, {enhancedData.position_2d[1].toFixed(3)})
              </Typography>
            </Grid>
          )}

          {enhancedData.position_3d && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                3D Position
              </Typography>
              <Typography variant="body2" style={{ fontFamily: 'monospace' }}>
                ({enhancedData.position_3d[0].toFixed(3)}, {enhancedData.position_3d[1].toFixed(3)}, {enhancedData.position_3d[2].toFixed(3)})
              </Typography>
            </Grid>
          )}

          {/* Angular Data */}
          {enhancedData.angular && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Angular (Bearing, Elevation)
              </Typography>
              <Typography variant="body2" style={{ fontFamily: 'monospace' }}>
                {enhancedData.angular[0].toFixed(1)}°, {enhancedData.angular[1].toFixed(1)}°
              </Typography>
            </Grid>
          )}

          {/* Velocity Data */}
          {enhancedData.velocity && (
            <Grid item xs={12} sm={6}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Velocity
              </Typography>
              <Typography variant="body2" style={{ fontFamily: 'monospace' }}>
                vx: {enhancedData.velocity.vx?.toFixed(3)}, vy: {enhancedData.velocity.vy?.toFixed(3)}
              </Typography>
              {enhancedData.velocity.magnitude && (
                <Typography variant="body2" color="textSecondary">
                  |v| = {enhancedData.velocity.magnitude.toFixed(3)}
                </Typography>
              )}
            </Grid>
          )}

          {/* Multi-target Info */}
          {enhancedData.targets && enhancedData.target_count > 0 && (
            <Grid item xs={12}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Multi-Target Tracking
              </Typography>
              <Box display="flex" alignItems="center" gap={1}>
                <Chip 
                  label={`${enhancedData.target_count} targets`}
                  color="info"
                  size="small"
                />
                {enhancedData.selected_target_id && (
                  <Chip 
                    label={`Selected: ${enhancedData.selected_target_id}`}
                    color="primary"
                    variant="outlined"
                    size="small"
                  />
                )}
              </Box>
            </Grid>
          )}

          {/* Capabilities */}
          {enhancedData.capabilities && (
            <Grid item xs={12}>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Tracker Capabilities
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={0.5}>
                {enhancedData.capabilities.supports_confidence && (
                  <Chip label="Confidence" size="small" variant="outlined" />
                )}
                {enhancedData.capabilities.supports_velocity && (
                  <Chip label="Velocity" size="small" variant="outlined" />
                )}
                {enhancedData.capabilities.supports_bbox && (
                  <Chip label="BBox" size="small" variant="outlined" />
                )}
                {enhancedData.capabilities.multi_target && (
                  <Chip label="Multi-Target" size="small" variant="outlined" />
                )}
                {enhancedData.capabilities.real_time && (
                  <Chip label="Real-Time" size="small" variant="outlined" />
                )}
              </Box>
            </Grid>
          )}

          {/* Timestamp */}
          {enhancedData.timestamp && (
            <Grid item xs={12}>
              <Typography variant="caption" color="textSecondary">
                Last Updated: {new Date(enhancedData.timestamp * 1000).toLocaleTimeString()}
              </Typography>
            </Grid>
          )}
        </Grid>
      </CardContent>
    </Card>
  );
};

export default EnhancedTrackerStatus;