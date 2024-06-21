import React, { useEffect } from 'react';
import PropTypes from 'prop-types';
import { Line } from 'react-chartjs-2';

const StaticPlot = ({ title, data, dataKey }) => {
  useEffect(() => {
    console.log(`${title} - Data updated:`, data);
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div>
        <h3>{title}</h3>
        <p>No data available</p>
      </div>
    );
  }

  const maxWindowSize = 30; // in seconds
  const startTime = new Date(data[0].timestamp).getTime();
  const elapsedTimes = data.map((d) => (new Date(d.timestamp).getTime() - startTime) / 1000);
  const labels = elapsedTimes.map((time) => time.toFixed(1));
  const plotData = data.map((d) => {
    const keys = dataKey.split('.');
    let value = d;
    keys.forEach((key) => {
      value = value[key] !== undefined ? value[key] : 0;
    });
    return value;
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
