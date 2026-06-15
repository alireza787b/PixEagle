import api from './apiClient';
import { endpoints, apiConfig } from './apiEndpoints';

api.defaults.baseURL = `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`;

export const sendCommand = (command, data = {}) => {
  return api.post(endpoints[command], data);
};

export default api;
