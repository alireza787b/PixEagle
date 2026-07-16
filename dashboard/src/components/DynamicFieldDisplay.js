// dashboard/src/components/DynamicFieldDisplay.js
import React from 'react';
import { 
  Box, 
  Typography, 
  Grid, 
  Paper,
  Chip,
  LinearProgress,
  Tooltip
} from '@mui/material';
import { EMPTY_VALUE, formatLabel, formatOperatorValue, isFiniteNumber } from '../utils/operatorFormat';

const FieldValueDisplay = ({ fieldName, value, fieldDefinition, groupColor }) => {
  const getValueProgress = () => {
    if (!fieldDefinition?.limits || !isFiniteNumber(value)) return null;
    
    const { min, max } = fieldDefinition.limits;
    if (!isFiniteNumber(min) || !isFiniteNumber(max) || max === min) return null;

    const progress = ((value - min) / (max - min)) * 100;
    
    return Math.max(0, Math.min(100, progress));
  };

  const progress = getValueProgress();
  const formattedValue = formatOperatorValue(value, {
    fieldName,
    fieldType: fieldDefinition?.type,
    unit: fieldDefinition?.unit,
    precision: 2,
  });

  return (
    <Tooltip title={fieldDefinition?.description || fieldName}>
      <Paper
        variant="outlined"
        sx={{ 
          minHeight: 108,
          height: '100%',
          p: 1.5,
          borderLeft: `4px solid ${groupColor}`,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: 1,
        }}
      >
        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', textTransform: 'uppercase', lineHeight: 1.2 }}
          >
            {formatLabel(fieldName)}
          </Typography>

          <Typography
            variant="h6"
            component="div"
            sx={{
              mt: 0.5,
              fontFamily: 'monospace',
              fontSize: { xs: '1rem', sm: '1.1rem' },
              lineHeight: 1.25,
              overflowWrap: 'anywhere',
              color: formattedValue === EMPTY_VALUE ? 'text.secondary' : 'text.primary',
            }}
          >
            {formattedValue}
          </Typography>
        </Box>

        {progress !== null && (
          <Box>
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
              <Typography variant="caption" color="text.secondary">
                {formatOperatorValue(fieldDefinition.limits.min)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {formatOperatorValue(fieldDefinition.limits.max)}
              </Typography>
            </Box>
          </Box>
        )}
      </Paper>
    </Tooltip>
  );
};

const FieldGroupDisplay = ({ groupName, groupConfig, fieldValues, fieldDefinitions }) => {
  return (
    <Box sx={{ mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5, minWidth: 0 }}>
        <Box 
          sx={{ 
            width: 4, 
            height: 24, 
            backgroundColor: groupConfig.color,
            mr: 2 
          }} 
        />
        <Typography variant="subtitle1" fontWeight={700} sx={{ minWidth: 0 }}>
          {groupConfig.name}
        </Typography>
        <Chip 
          label={`${groupConfig.fields.length} fields`}
          size="small"
          sx={{ ml: 2 }}
        />
      </Box>
      
      <Grid container rowSpacing={2} columnSpacing={{ xs: 0, sm: 2 }}>
        {groupConfig.fields.map((fieldName) => (
          <Grid item xs={12} sm={6} lg={4} key={fieldName}>
            <FieldValueDisplay
              fieldName={fieldName}
              value={Object.prototype.hasOwnProperty.call(fieldValues, fieldName) ? fieldValues[fieldName] : undefined}
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
      <Box sx={{ py: 0.5 }}>
        <Chip label="Follower inactive" size="small" variant="outlined" />
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
