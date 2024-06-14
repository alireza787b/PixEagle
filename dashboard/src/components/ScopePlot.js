import React from 'react';
import { Scatter } from 'react-chartjs-2';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

const ScopePlot = ({ title, trackerData }) => {
  const latestData = trackerData[trackerData.length - 1];

  const data = {
    datasets: [
      {
        label: 'Center Point',
        data: [{ x: latestData.center[0], y: latestData.center[1] }],
        backgroundColor: 'rgba(75, 192, 192, 1)',
        pointRadius: 5,
      },
      {
        label: 'Bounding Box',
        data: (() => {
          const [x1, y1, x2, y2] = latestData.bounding_box;
          return [
            { x: x1, y: y1 },
            { x: x2, y: y1 },
            { x: x2, y: y2 },
            { x: x1, y: y2 },
            { x: x1, y: y1 }, // Close the rectangle
          ];
        })(),
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        borderColor: 'rgba(255, 99, 132, 1)',
        borderWidth: 1,
        showLine: true,
        fill: false,
        pointRadius: 0,
      },
    ],
  };

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
