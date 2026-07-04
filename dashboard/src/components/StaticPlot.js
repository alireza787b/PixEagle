import React from 'react';
import PropTypes from 'prop-types';
import { Line } from 'react-chartjs-2';
import { Box, Paper, Typography } from '@mui/material';
import { formatOperatorValue } from '../utils/operatorFormat';

const StaticPlot = ({ title, data, dataKey }) => {
  // Check if data is valid for different data keys
  const isTrackerDataValid = (dataKey === 'center.0' || dataKey === 'center.1') &&
                             data && data.length > 0 && data.some(d => d.center !== null);
  const isFollowerDataValid = (dataKey === 'vel_x' || dataKey === 'vel_y' || dataKey === 'vel_z') &&
                              data && data.length > 0 && data.some(d => d[dataKey] !== undefined);
  
  // Schema-aware tracker field validation
  const isSchemaTrackerDataValid = data && data.length > 0 && 
                                   data.some(d => d.fields && d.fields[dataKey] !== undefined);

  if (!isTrackerDataValid && !isFollowerDataValid && !isSchemaTrackerDataValid) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary">Waiting for data...</Typography>
      </Paper>
    );
  }

  let validData;
  if (isTrackerDataValid) {
    validData = data.filter(d => d.center !== null);
  } else if (isFollowerDataValid) {
    validData = data.filter(d => d[dataKey] !== undefined);
  } else {
    validData = data.filter(d => d.fields && d.fields[dataKey] !== undefined);
  }

  const maxWindowSize = 30; // in seconds
  const startTime = new Date(validData[0].timestamp).getTime();
  const elapsedTimes = validData.map((d) => (new Date(d.timestamp).getTime() - startTime) / 1000);
  const labels = elapsedTimes.map((time) => time.toFixed(1));
  const plotData = validData.map((d) => {
    if (isTrackerDataValid) {
      const index = dataKey === 'center.0' ? 0 : 1;
      return d.center ? d.center[index] : 0;
    } else if (isFollowerDataValid) {
      return d[dataKey] !== undefined ? d[dataKey] : 0;
    } else {
      // Schema-driven tracker field data
      const fieldValue = d.fields[dataKey];
      if (Array.isArray(fieldValue)) {
        // For array fields like position_2d, use first element
        return fieldValue[0] || 0;
      }
      return typeof fieldValue === 'number' ? fieldValue : 0;
    }
  });

  const chartData = {
    labels,
    datasets: [
      {
        label: dataKey,
        data: plotData,
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 1,
        fill: false,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 500,
      easing: 'easeInOutQuart',
    },
    plugins: {
      legend: {
        position: 'top',
      },
      title: {
        display: true,
        text: title,
      },
    },
    scales: {
      x: {
        type: 'linear',
        title: {
          display: true,
          text: 'Time (s)',
        },
        min: Math.max(0, elapsedTimes[elapsedTimes.length - 1] - maxWindowSize),
        max: elapsedTimes[elapsedTimes.length - 1] + 1,
      },
      y: {
        type: 'linear',
        title: {
          display: true,
          text: 'Value',
        },
      },
    },
  };

  const currentValue = plotData.length > 0 ? plotData[plotData.length - 1] : null;

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Box sx={{ height: { xs: 220, sm: 260 } }}>
        <Line data={chartData} options={options} />
      </Box>
      {currentValue !== null && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mt: 1 }}>
          Current {dataKey}: {formatOperatorValue(currentValue)}
        </Typography>
      )}
    </Paper>
  );
};

StaticPlot.propTypes = {
  title: PropTypes.string.isRequired,
  data: PropTypes.arrayOf(PropTypes.object).isRequired,
  dataKey: PropTypes.string.isRequired,
};

export default StaticPlot;
