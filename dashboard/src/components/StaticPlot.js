import React from 'react';
import PropTypes from 'prop-types';
import { Line } from 'react-chartjs-2';
import { Box, Paper, Typography } from '@mui/material';
import { formatOperatorValue } from '../utils/operatorFormat';

const TRACKER_CENTER_KEYS = new Set(['center.0', 'center.1']);

const readFinitePlotValue = (sample, dataKey) => {
  let value;

  if (TRACKER_CENTER_KEYS.has(dataKey)) {
    const index = dataKey === 'center.0' ? 0 : 1;
    value = Array.isArray(sample?.center) ? sample.center[index] : null;
  } else {
    value = sample?.[dataKey];
    if (value === undefined) {
      value = sample?.fields?.[dataKey];
    }
    if (Array.isArray(value)) {
      [value] = value;
    }
  }

  return typeof value === 'number' && Number.isFinite(value) ? value : null;
};

const StaticPlot = ({ title, data, dataKey }) => {
  const samples = Array.isArray(data) ? data : [];
  const plotData = samples.map((sample) => readFinitePlotValue(sample, dataKey));
  const hasFiniteData = plotData.some((value) => value !== null);

  if (!hasFiniteData) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary">Waiting for data...</Typography>
      </Paper>
    );
  }

  const maxWindowSize = 30; // in seconds
  const startTime = new Date(samples[0].timestamp).getTime();
  const elapsedTimes = samples.map((sample) => (
    new Date(sample.timestamp).getTime() - startTime
  ) / 1000);
  const labels = elapsedTimes.map((time) => time.toFixed(1));

  const chartData = {
    labels,
    datasets: [
      {
        label: dataKey,
        data: plotData,
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 1,
        fill: false,
        spanGaps: false,
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
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mt: 1 }}>
        Current {dataKey}: {formatOperatorValue(currentValue)}
      </Typography>
    </Paper>
  );
};

StaticPlot.propTypes = {
  title: PropTypes.string.isRequired,
  data: PropTypes.arrayOf(PropTypes.object).isRequired,
  dataKey: PropTypes.string.isRequired,
};

export default StaticPlot;
