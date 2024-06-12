// src/components/Dashboard.js
import React, { useEffect, useState } from 'react';
import io from 'socket.io-client';

const socket = io('http://localhost:5000');

const Dashboard = () => {
  const [trackerData, setTrackerData] = useState({ bounding_box: null, center: null });

  useEffect(() => {
    socket.on('tracker_data', (data) => {
      setTrackerData(data);
    });

    return () => {
      socket.off('tracker_data');
    };
  }, []);

  return (
    <div>
      <h1>PixEagle Dashboard</h1>
      <div>
        <h2>Bounding Box</h2>
        <pre>{JSON.stringify(trackerData.bounding_box, null, 2)}</pre>
      </div>
      <div>
        <h2>Center</h2>
        <pre>{JSON.stringify(trackerData.center, null, 2)}</pre>
      </div>
    </div>
  );
};

export default Dashboard;
