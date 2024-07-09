import React, { useState, useEffect } from 'react';
import { Scatter } from 'react-chartjs-2';
import { Chart, registerables } from 'chart.js';
import ArrowPlugin from '../plugins/ArrowPlugin';
import WebRTCStream from './WebRTCStream';
import { Button, Typography } from '@mui/material';

Chart.register(...registerables);

const ScopePlot = ({ title, trackerData, followerData }) => {
  const [showVideo, setShowVideo] = useState(false);
  const [videoError, setVideoError] = useState(false);

  const toggleVideoOverlay = () => setShowVideo(!showVideo);

  useEffect(() => {
    Chart.register(ArrowPlugin);
  }, []);

  if (!trackerData || trackerData.length === 0) {
    return (
      <div>
        <h3>{title}</h3>
        <p>No data available</p>
      </div>
    );
  }

  const latestTrackerData = trackerData[trackerData.length - 1];
  if (!latestTrackerData || !latestTrackerData.center || !latestTrackerData.bounding_box) {
    return (
      <div>
        <h3>{title}</h3>
        <p>Incomplete tracker data</p>
      </div>
    );
  }

  const maxSpeed = parseFloat(process.env.REACT_APP_MAX_SPEED) || 10;

  const datasets = [
    {
      label: 'Center Point',
      data: [{ x: latestTrackerData.center[0], y: latestTrackerData.center[1] * -1 }],
      backgroundColor: 'rgba(75, 192, 192, 1)',
      pointRadius: 5,
    },
    {
      label: 'Bounding Box',
      data: (() => {
        const [x, y, width, height] = latestTrackerData.bounding_box;
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
    const velocityMagnitude = Math.sqrt(
      latestFollowerData.vel_x ** 2 + latestFollowerData.vel_y ** 2
    );

    const normalizedVelocity = {
      x: (latestFollowerData.vel_x / maxSpeed),
      y: (latestFollowerData.vel_y / maxSpeed),
    };

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

  const flaskHost = process.env.REACT_APP_WEBSOCKET_VIDEO_HOST;
  const flaskPort = process.env.REACT_APP_WEBSOCKET_VIDEO_PORT;
  const videoSrc = `http://${flaskHost}:${flaskPort}/video_feed`;

  return (
    <div style={{ position: 'relative', height: '750px', width: '100%' }}>
      <Button variant="contained" color="primary" onClick={toggleVideoOverlay} style={{ marginBottom: '10px', zIndex: '10' }}>
        {showVideo ? 'Hide Video Overlay' : 'Show Video Overlay'}
      </Button>
      {showVideo && (
        <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 1, pointerEvents: 'none' }}>
          <WebRTCStream protocol="http" src={videoSrc} style={{ width: '100%', height: '100%', opacity: 0.5, objectFit: 'cover' }} onError={() => setVideoError(true)} />
        </div>
      )}
      {videoError && (
        <Typography variant="h6" style={{ color: 'red', textAlign: 'center', position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', zIndex: 2 }}>
          Live feed not available
        </Typography>
      )}
      <Scatter data={data} options={options} style={{ position: 'relative', zIndex: 2 }} />
    </div>
  );
};

export default ScopePlot;
