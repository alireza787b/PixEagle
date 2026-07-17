import React, { useState, useEffect } from 'react';
import { Scatter } from 'react-chartjs-2';
import { Chart, registerables } from 'chart.js';
import ArrowPlugin from '../plugins/ArrowPlugin';
import VideoStream from './VideoStream';
import { Box, Button, Paper, Typography } from '@mui/material';
import { videoFeed } from '../services/apiEndpoints';

Chart.register(...registerables);

const ScopePlot = ({ title, trackerData, followerData }) => {
  const [showVideo, setShowVideo] = useState(false);

  const toggleVideoOverlay = () => setShowVideo(!showVideo);

  useEffect(() => {
    Chart.register(ArrowPlugin);
  }, []);

  if (!trackerData || trackerData.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary">No target geometry available.</Typography>
      </Paper>
    );
  }

  const latestTrackerData = trackerData[trackerData.length - 1];
  
  // Enhanced data extraction supporting flexible schema
  const getTrackerCenter = (data) => {
    // New schema format
    if (data.tracker_data) {
      if (data.tracker_data.position_2d) return data.tracker_data.position_2d;
      if (data.tracker_data.position_3d) return data.tracker_data.position_3d.slice(0, 2);
    }
    // Legacy format
    return data.center;
  };
  
  const getTrackerBbox = (data) => {
    // New schema format
    if (data.tracker_data && data.tracker_data.normalized_bbox) {
      return data.tracker_data.normalized_bbox;
    }
    // Legacy format
    return data.bounding_box;
  };
  
  const trackerCenter = getTrackerCenter(latestTrackerData);
  const trackerBbox = getTrackerBbox(latestTrackerData);
  
  if (!latestTrackerData || !trackerCenter || !trackerBbox) {
    return (
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
        <Typography variant="body2" color="text.secondary">Waiting for target center and bounding box.</Typography>
      </Paper>
    );
  }

  const maxSpeed = parseFloat(process.env.REACT_APP_MAX_SPEED) || 10;

  const datasets = [
    {
      label: 'Center Point',
      data: [{ x: trackerCenter[0], y: trackerCenter[1] * -1 }],
      backgroundColor: 'rgba(75, 192, 192, 1)',
      pointRadius: 5,
    },
    {
      label: 'Bounding Box',
      data: (() => {
        const [x, y, width, height] = trackerBbox;
        return [
          { x: x, y: -y },
          { x: x + 2 * width, y: -y },
          { x: x + 2 * width, y: -y - 2 * height },
          { x: x, y: -y - 2 * height },
          { x: x, y: -y },
        ];
      })(),
      backgroundColor: 'rgba(255, 99, 132, 0.2)',
      borderColor: 'rgba(255, 99, 132, 1)',
      borderWidth: 1,
      showLine: true,
      fill: false,
      pointRadius: 0,
    },
  ];

  if (followerData && followerData.length > 0) {
    const latestFollowerData = followerData[followerData.length - 1];
    const velX = Number(latestFollowerData.vel_x);
    const velY = Number(latestFollowerData.vel_y);

    if (Number.isFinite(velX) && Number.isFinite(velY)) {
      // Normalize the velocity and limit the arrow length to 0.5
      const normalizationFactor = maxSpeed * 2; // since we want 0.5 max length
      let normalizedVelocity = {
        x: (velX / normalizationFactor),
        y: (velY / normalizationFactor),
      };

      // Limit the length to a maximum of 0.5
      const maxLength = 0.5;
      const length = Math.sqrt(normalizedVelocity.x ** 2 + normalizedVelocity.y ** 2);
      if (length > maxLength) {
        normalizedVelocity = {
          x: (normalizedVelocity.x / length) * maxLength,
          y: (normalizedVelocity.y / length) * maxLength,
        };
      }

      const arrowEnd = {
        x: normalizedVelocity.x,
        y: normalizedVelocity.y,
      };

      datasets.push({
        label: 'Velocity Vector',
        data: [
          { x: 0, y: 0 },
          arrowEnd,
        ],
        borderColor: 'rgba(0, 255, 0, 1)',
        borderWidth: 2,
        showLine: true,
        pointRadius: 0,
      });
    }
  }

  const data = { datasets };

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
        onClick: (e, legendItem, legend) => {
          const index = legendItem.datasetIndex;
          const meta = legend.chart.getDatasetMeta(index);
          meta.hidden = meta.hidden === null ? !legend.chart.data.datasets[index].hidden : null;
          legend.chart.update();
        },
      },
      title: {
        display: true,
        text: title,
      },
      tooltip: {
        enabled: false,
      },
    },
    scales: {
      x: {
        type: 'linear',
        position: 'bottom',
        min: -1,
        max: 1,
        ticks: {
          stepSize: 0.1,
        },
      },
      y: {
        type: 'linear',
        min: -1,
        max: 1,
        ticks: {
          stepSize: 0.1,
        },
      },
    },
  };

  // Use dynamic videoFeed URL from apiEndpoints (auto-detected host)
  const videoSrc = videoFeed;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1.5, sm: 2 }, overflow: 'hidden' }}>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1 }}>
        <Button variant="outlined" size="small" color="primary" onClick={toggleVideoOverlay}>
          {showVideo ? 'Hide Video Overlay' : 'Show Video Overlay'}
        </Button>
      </Box>
      <Box
        sx={{
          position: 'relative',
          height: { xs: 320, sm: 420, lg: 520 },
          width: '100%',
        }}
      >
        {showVideo && (
          <Box sx={{ position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none', opacity: 0.35 }}>
            <VideoStream protocol="http" src={videoSrc} />
          </Box>
        )}
        <Scatter data={data} options={options} style={{ position: 'relative', zIndex: 2 }} />
      </Box>
    </Paper>
  );
};

export default ScopePlot;
