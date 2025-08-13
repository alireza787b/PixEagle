// dashboard/src/components/DynamicFieldDisplay.js
import React from 'react';
import { 
  Box, 
  Typography, 
  Grid, 
  Card, 
  CardContent, 
  Chip,
  LinearProgress,
  Tooltip
} from '@mui/material';

const FieldValueDisplay = ({ fieldName, value, fieldDefinition, groupColor }) => {
  const formatValue = (val) => {
    if (typeof val === 'number') {
      return val.toFixed(3);
    }
    return val;
  };

  const getValueProgress = () => {
    if (!fieldDefinition?.limits || typeof value !== 'number') return null;
    
    const { min, max } = fieldDefinition.limits;
    const progress = ((value - min) / (max - min)) * 100;
    
    return Math.max(0, Math.min(100, progress));
  };

  const progress = getValueProgress();

  return (
    <Tooltip title={fieldDefinition?.description || fieldName}>
      <Card 
        sx={{ 
          minHeight: 120,
          borderLeft: `4px solid ${groupColor}`,
          '&:hover': { transform: 'translateY(-2px)' },
          transition: 'transform 0.2s'
        }}
      >
        <CardContent>
          <Typography variant="subtitle2" color="textSecondary" gutterBottom>
            {fieldName.replace('_', ' ').toUpperCase()}
          </Typography>
          
          <Typography variant="h6" component="div">
            {formatValue(value)}
          </Typography>
          
          {fieldDefinition?.unit && (
            <Typography variant="caption" color="textSecondary">
              {fieldDefinition.unit}
            </Typography>
          )}
          
          {progress !== null && (
            <Box sx={{ mt: 1 }}>
              <LinearProgress 
                variant="determinate" 
                value={progress}
                sx={{ 
                  backgroundColor: 'rgba(0,0,0,0.1)',
                  '& .MuiLinearProgress-bar': {
                    backgroundColor: groupColor
                  }
                }}
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5 }}>
                <Typography variant="caption">
                  {fieldDefinition.limits.min}
                </Typography>
                <Typography variant="caption">
                  {fieldDefinition.limits.max}
                </Typography>
              </Box>
            </Box>
          )}
        </CardContent>
      </Card>
    </Tooltip>
  );
};

const FieldGroupDisplay = ({ groupName, groupConfig, fieldValues, fieldDefinitions }) => {
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Box 
          sx={{ 
            width: 4, 
            height: 24, 
            backgroundColor: groupConfig.color,
            mr: 2 
          }} 
        />
        <Typography variant="h6">{groupConfig.name}</Typography>
        <Chip 
          label={`${groupConfig.fields.length} fields`}
          size="small"
          sx={{ ml: 2 }}
        />
      </Box>
      
      <Grid container spacing={2}>
        {groupConfig.fields.map((fieldName) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={fieldName}>
            <FieldValueDisplay
              fieldName={fieldName}
              value={fieldValues[fieldName] || 0}
              fieldDefinition={fieldDefinitions[fieldName]}
              groupColor={groupConfig.color}
            />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

const DynamicFieldDisplay = ({ schema, currentProfile, fieldValues }) => {
  if (!schema || !currentProfile || !currentProfile.active) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography variant="h6" color="textSecondary">
          No active follower profile
        </Typography>
      </Box>
    );
  }

  const fieldDefinitions = schema.command_fields || {};
  const uiConfig = schema.ui_config || {};
  const fieldGroups = uiConfig.field_groups || {};
  
  // Group available fields
  const availableFields = currentProfile.available_fields || [];
  const groups = {};
  
  Object.entries(fieldGroups).forEach(([groupKey, groupConfig]) => {
    const groupFields = groupConfig.fields.filter(field => 
      availableFields.includes(field)
    );
    
    if (groupFields.length > 0) {
      groups[groupKey] = {
        ...groupConfig,
        fields: groupFields
      };
    }
  });

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h5" gutterBottom>
          {currentProfile.display_name}
        </Typography>
        <Typography variant="body2" color="textSecondary" paragraph>
          {currentProfile.description}
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Chip 
            label={currentProfile.control_type}
            color="primary"
            size="small"
          />
          <Chip 
            label={currentProfile.validation_status ? 'Valid' : 'Invalid'}
            color={currentProfile.validation_status ? 'success' : 'error'}
            size="small"
          />
        </Box>
      </Box>

      {Object.entries(groups).map(([groupKey, groupConfig]) => (
        <FieldGroupDisplay
          key={groupKey}
          groupName={groupKey}
          groupConfig={groupConfig}
          fieldValues={fieldValues || {}}
          fieldDefinitions={fieldDefinitions}
        />
      ))}
    </Box>
  );
};

export default DynamicFieldDisplay;