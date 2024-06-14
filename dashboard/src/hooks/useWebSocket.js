import { useEffect, useState, useCallback } from 'react';

const useWebSocket = (url, maxEntries = 300) => {
  const [trackerData, setTrackerData] = useState([]);
  const [rawData, setRawData] = useState([]);

  const addData = useCallback((data) => {
    if (data.tracker_started) {
      setTrackerData((prevData) => [...prevData, data].slice(-maxEntries));
      setRawData((prevData) => [...prevData, JSON.stringify(data, null, 2)].slice(-maxEntries));
    }
  }, [maxEntries]);

  useEffect(() => {
    const socket = new WebSocket(url);

    socket.onopen = () => {
      console.log('WebSocket connection established');
    };

    socket.onmessage = (event) => {
      try {
        const receivedData = JSON.parse(event.data);
        addData(receivedData);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    socket.onclose = () => {
      console.log('WebSocket connection closed');
    };

    return () => {
      socket.close();
    };
  }, [url, addData]);

  return { trackerData, rawData };
};

export default useWebSocket;
