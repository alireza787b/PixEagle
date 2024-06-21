/**
 * ScopePlot Component
 * 
 * Challenge:
 * The goal is to accurately render a bounding box and a center point on a Chart.js scatter plot
 * using data obtained from an OpenCV-based tracking system. The primary challenge is to handle
 * the differences in coordinate systems between OpenCV and Chart.js, and apply the necessary 
 * transformations to ensure the bounding box is displayed correctly.
 * 
 * Coordinate Systems:
 * - OpenCV:
 *   - Default: Top-left (0, 0)
 *   - Normalized: Center (0, 0), Top-left (-1, 1), Bottom-right (1, -1)
 * 
 * - Chart.js:
 *   - Normalized: Center (0, 0), Top-left (-1, 1), Bottom-right (1, -1)
 * 
 * Axis Definitions:
 * - Both systems use normalized coordinates, but the y-axis needs to be inverted for Chart.js.
 * - OpenCV coordinates are typically in a range relative to the frame, but we normalize to a range of [-1, 1].
 * 
 * Transformation and Conversion:
 * - Center Point:
 *   - Inverted y-coordinate to match Chart.js: { x: center[0], y: center[1] * -1 }
 * 
 * - Bounding Box:
 *   - Provided as [x, y, width, height] in OpenCV
 *   - To correctly scale the bounding box for Chart.js, we need to:
 *     - Double the width and height for the normalized range.
 *     - Invert the y-coordinates.
 *   - Transformed Coordinates:
 *     - Top-left: { x: x, y: -y }
 *     - Top-right: { x: x + 2*width, y: -y }
 *     - Bottom-right: { x: x + 2*width, y: -y - 2*height }
 *     - Bottom-left: { x: x, y: -y - 2*height }
 * 
 * This ensures the bounding box dimensions match the intended scale in the Chart.js plot,
 * taking into account the normalized coordinate system and inversion required.
 */

import React from 'react';
import { Scatter } from 'react-chartjs-2';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

const ScopePlot = ({ title, trackerData, followerData }) => {
  if (!trackerData || trackerData.length === 0) {
    return (
      <div>
        <h3>{title}</h3>
        <p>No data available</p>
      </div>
    );
  }

  const latestTrackerData = trackerData[trackerData.length - 1];
  const maxSpeed = parseFloat(process.env.REACT_APP_MAX_SPEED);

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
          { x: x, y: -y }, // Top-left corner
          { x: x + 2 * width, y: -y }, // Top-right corner
          { x: x + 2 * width, y: -y - 2 * height }, // Bottom-right corner
          { x: x, y: -y - 2 * height }, // Bottom-left corner
          { x: x, y: -y }, // Close the rectangle
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
      x: (latestFollowerData.vel_x / velocityMagnitude) * maxSpeed,
      y: (latestFollowerData.vel_y / velocityMagnitude) * maxSpeed,
    };

    const arrowEnd = {
      x: normalizedVelocity.x,
      y: normalizedVelocity.y,
    };

    datasets.push({
      label: 'Velocity Vector',
      data: [
        { x: 0, y: 0 }, // Center of the plot (representing the drone center)
        arrowEnd,
      ],
      borderColor: 'rgba(0, 255, 0, 1)',
      borderWidth: 2,
      showLine: true,
      pointRadius: 0,
    });
  }

  const arrowPlugin = {
    id: 'arrowPlugin',
    afterDatasetsDraw: (chart) => {
      const { ctx, scales: { x, y } } = chart;
      const datasetIndex = chart.data.datasets.findIndex(dataset => dataset.label === 'Velocity Vector');
      if (datasetIndex < 0 || !chart.isDatasetVisible(datasetIndex)) return;

      const velocityData = chart.data.datasets[datasetIndex].data;
      if (velocityData.length < 2) return;

      const start = velocityData[0];
      const end = velocityData[1];

      const startX = x.getPixelForValue(start.x);
      const startY = y.getPixelForValue(start.y);
      const endX = x.getPixelForValue(end.x);
      const endY = y.getPixelForValue(end.y);

      const headLength = 10;
      const angle = Math.atan2(endY - startY, endX - startX);

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(endX, endY);
      ctx.lineTo(
        endX - headLength * Math.cos(angle - Math.PI / 6),
        endY - headLength * Math.sin(angle - Math.PI / 6)
      );
      ctx.lineTo(
        endX - headLength * Math.cos(angle + Math.PI / 6),
        endY - headLength * Math.sin(angle + Math.PI / 6)
      );
      ctx.lineTo(endX, endY);
      ctx.fillStyle = 'rgba(0, 255, 0, 1)';
      ctx.fill();
      ctx.restore();
    },
  };

  Chart.register(arrowPlugin);

  const data = { datasets };

  const options = {
    responsive: true,
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
        position: 'bottom',
        min: -1,
        max: 1,
      },
      y: {
        type: 'linear',
        min: -1,
        max: 1,
      },
    },
  };

  return <Scatter data={data} options={options} />;
};

export default ScopePlot;
