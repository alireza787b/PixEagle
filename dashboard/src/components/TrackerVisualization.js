// src/components/TrackerVisualization.js
import React, { useEffect, useState } from 'react';
import io from 'socket.io-client';
import { Line } from 'react-chartjs-2';

const socket = io('http://localhost:5000');

const TrackerVisualization = () => {
  const [trackerData, setTrackerData] = useState([]);

  useEffect(() => {
    socket.on('tracker_data', (data) => {
      setTrackerData((prevData) => [...prevData, data]);
    });

    return () => {
      socket.off('tracker_data');
    };
  }, []);

  const data = {
    labels: trackerData.map((_, index) => index),
    datasets: [
      {
        label: 'Center X',
        data: trackerData.map((data) => data.center[0]),
        borderColor: 'rgba(75, 192, 192, 1)',
        borderWidth: 1,
        fill: false,
      },
      {
        label: 'Center Y',
        data: trackerData.map((data) => data.center[1]),
        borderColor: 'rgba(255, 99, 132, 1)',
        borderWidth: 1,
        fill: false,
      },
    ],
  };

  return (
    <div>
      <h1>Tracker Visualization</h1>
      <Line data={data} />
    </div>
  );
};

export default TrackerVisualization;
