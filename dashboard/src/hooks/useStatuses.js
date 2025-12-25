//dashboard/src/hooks/useStatuses.js
import { useState, useEffect } from 'react';
import axios from 'axios';
import { apiConfig } from '../services/apiEndpoints';

const API_URL = `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`;

export const useTrackerStatus = (interval = 2000) => {
  const [isTracking, setIsTracking] = useState(false);

  useEffect(() => {
    const fetchTrackerStatus = async () => {
      try {
        const response = await axios.get(`${API_URL}/telemetry/tracker_data`);
        const trackerData = response.data;

        if (trackerData.tracker_started) {
          setIsTracking(true);
        } else {
          setIsTracking(false);
        }
      } catch (error) {
        console.error('Error fetching tracker data:', error);
        console.log("URI Used is:", `${API_URL}/telemetry/tracker_data`);
        setIsTracking(false);
      }
    };

    const intervalId = setInterval(fetchTrackerStatus, interval);
    fetchTrackerStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return isTracking;
};

export const useFollowerStatus = (interval = 2000) => {
  const [isFollowing, setIsFollowing] = useState(false);

  useEffect(() => {
    const fetchFollowerStatus = async () => {
      try {
        const response = await axios.get(`${API_URL}/telemetry/follower_data`);
        const followerData = response.data;

        setIsFollowing(followerData.following_active);
      } catch (error) {
        console.error('Error fetching follower data:', error);
        setIsFollowing(false);
      }
    };

    const intervalId = setInterval(fetchFollowerStatus, interval);
    fetchFollowerStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return isFollowing;
};


export const useSmartModeStatus = (interval = 2000) => {
  const [smartModeActive, setSmartModeActive] = useState(false);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await axios.get(`${API_URL}/status`);
        const data = response.data;
        setSmartModeActive(data.smart_mode_active || false);
      } catch (error) {
        console.error('Error fetching smart mode status:', error);
        setSmartModeActive(false);
      }
    };

    const intervalId = setInterval(fetchStatus, interval);
    fetchStatus(); // Initial call

    return () => clearInterval(intervalId);
  }, [interval]);

  return smartModeActive;
};
