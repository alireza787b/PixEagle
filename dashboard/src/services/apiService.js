// dashboard/src/services/apiService.js
import axios from 'axios';
import { endpoints, apiConfig } from './apiEndpoints';

// Use dynamic config from apiEndpoints (auto-detected host, protocol)
const api = axios.create({
  baseURL: `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`,
});

export const sendCommand = (command, data = {}) => {
  return api.post(endpoints[command], data);
};

export default api;
