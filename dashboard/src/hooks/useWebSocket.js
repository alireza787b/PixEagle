import { useEffect, useState, useCallback } from 'react';
import { createDashboardWebSocket, isWebSocketAuthClose } from '../services/apiClient';

const useWebSocket = (url, maxEntries = 300) => {
  const [trackerData, setTrackerData] = useState([]);
  const [rawData, setRawData] = useState([]);

  // Enhanced data validation for flexible tracker schema
  const validateTrackerData = useCallback((data) => {
    // Support both legacy and new schema formats
    const isLegacyFormat = data.tracker_started !== undefined;
    const isEnhancedFormat = data.tracker_data && data.tracker_data.tracking_active !== undefined;
    
    if (isLegacyFormat) {
      return data.tracker_started;
    }

    if (isEnhancedFormat) {
      return data.tracker_data.tracking_active;
    }

    return false;
  }, []);

  const addData = useCallback((data) => {
    if (validateTrackerData(data)) {
      setTrackerData((prevData) => [...prevData, data].slice(-maxEntries));
      setRawData((prevData) => [...prevData, JSON.stringify(data, null, 2)].slice(-maxEntries));
    }
  }, [maxEntries, validateTrackerData]);

  useEffect(() => {
    let socket;
    try {
      socket = createDashboardWebSocket(url);
    } catch (error) {
      console.error('WebSocket authorization failed:', error);
      return undefined;
    }

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

    socket.onclose = (event) => {
      console.log('WebSocket connection closed');
      if (isWebSocketAuthClose(event)) {
        console.error('WebSocket authorization was rejected');
      }
    };

    return () => {
      socket.close();
    };
  }, [url, addData]);

  return { trackerData, rawData };
};

export default useWebSocket;
