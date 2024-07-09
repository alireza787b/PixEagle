import React, { useEffect } from 'react';
import PropTypes from 'prop-types';
import { Line } from 'react-chartjs-2';

const StaticPlot = ({ title, data, dataKey }) => {
  useEffect(() => {
    console.log(`${title} - Data updated:`, data);
  }, [data]);

  // Check if data is valid for different data keys
  const isTrackerDataValid = (dataKey === 'center.0' || dataKey === 'center.1') &&
                             data && data.length > 0 && data.some(d => d.center !== null);
  const isFollowerDataValid = (dataKey === 'vel_x' || dataKey === 'vel_y' || dataKey === 'vel_z') &&
                              data && data.length > 0 && data.some(d => d[dataKey] !== undefined);

  if (!isTrackerDataValid && !isFollowerDataValid) {
    return (
      <div>
        <h3>{title}</h3>
        <p>Waiting for data...</p>
      </div>
    );
  }

  const validData = isTrackerDataValid ? data.filter(d => d.center !== null) : data.filter(d => d[dataKey] !== undefined);

  const maxWindowSize = 30; // in seconds
  const startTime = new Date(validData[0].timestamp).getTime();
  const elapsedTimes = validData.map((d) => (new Date(d.timestamp).getTime() - startTime) / 1000);
  const labels = elapsedTimes.map((time) => time.toFixed(1));
  const plotData = validData.map((d) => {
    if (isTrackerDataValid) {
      const index = dataKey === 'center.0' ? 0 : 1;
      return d.center ? d.center[index] : 0;
    } else {
      return d[dataKey] !== undefined ? d[dataKey] : 0;
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
    <div>
      <Line data={chartData} options={options} />
      {currentValue !== null && (
        <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '0.8em' }}>
          <strong>Current {dataKey}: {currentValue.toFixed(2)}</strong>
        </div>
      )}
    </div>
  );
};

StaticPlot.propTypes = {
  title: PropTypes.string.isRequired,
  data: PropTypes.arrayOf(PropTypes.object).isRequired,
  dataKey: PropTypes.string.isRequired,
};

export default StaticPlot;
