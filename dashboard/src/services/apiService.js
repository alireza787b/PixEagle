// dashboard/src/services/apiService.js
import axios from 'axios';

// Load environment variables
const apiHost = process.env.REACT_APP_API_HOST;
const apiPort = process.env.REACT_APP_API_PORT;

// Create an Axios instance with the base URL of the FastAPI backend
const api = axios.create({
  baseURL: `http://${apiHost}:${apiPort}`,
});

/**
 * Sends a command to the FastAPI backend
 * @param {string} command - The command to send
 * @param {Object} data - The data to send with the command
 * @returns {Promise} - The Axios promise for the API call
 */
export const sendCommand = (command, data = {}) => {
  return api.post(`/commands/${command}`, data);
};

export default api;
