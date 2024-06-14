import React from 'react';
import PropTypes from 'prop-types';
import { Line } from 'react-chartjs-2';

const StaticPlot = ({ title, trackerData, dataKey }) => {
  if (trackerData.length === 0 || !trackerData[0].center) {
    return (
      <div>
        <h3>{title}</h3>
        <p>No data available</p>
      </div>
    );
  }

  const maxWindowSize = 30; // in seconds
  const startTime = new Date(trackerData[0].timestamp).getTime();
  const elapsedTimes = trackerData.map((d) => (new Date(d.timestamp).getTime() - startTime) / 1000);
  const labels = elapsedTimes.map((time) => time.toFixed(1));
  const data = trackerData.map((d) => d.center[dataKey === 'center[0]' ? 0 : 1]);

  const chartData = {
    labels,
    datasets: [
      {
        label: dataKey === 'center[0]' ? 'Center X' : 'Center Y',
        data,
        borderColor: dataKey === 'center[0]' ? 'rgba(75, 192, 192, 1)' : 'rgba(255, 99, 132, 1)',
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
        min: -1,
        max: 1,
        title: {
          display: true,
          text: 'Value',
        },
      },
    },
  };

  const currentValue = trackerData.length > 0 ? data[data.length - 1] : null;

  return (
    <div>
      <Line data={chartData} options={options} />
      {currentValue !== null && (
        <div style={{ textAlign: 'center', marginTop: '10px', fontSize: '0.8em' }}>
          <strong>Current {dataKey === 'center[0]' ? 'Center X' : 'Center Y'}: {currentValue.toFixed(2)}</strong>
        </div>
      )}
    </div>
  );
};

StaticPlot.propTypes = {
  title: PropTypes.string.isRequired,
  trackerData: PropTypes.arrayOf(PropTypes.object).isRequired,
  dataKey: PropTypes.oneOf(['center[0]', 'center[1]']).isRequired,
};

export default StaticPlot;
