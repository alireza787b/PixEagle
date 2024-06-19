import React from 'react';
import PropTypes from 'prop-types';

const RawDataLog = ({ rawData }) => {
  return (
    <div style={{ height: '200px', overflowY: 'scroll', border: '1px solid #ccc', padding: '10px' }}>
      {rawData.map((data, index) => (
        <div key={index}>
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
      ))}
    </div>
  );
};

RawDataLog.propTypes = {
  rawData: PropTypes.arrayOf(PropTypes.object).isRequired,
};

export default RawDataLog;
