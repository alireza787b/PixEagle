// dashboard/src/services/apiService.js
import axios from 'axios';
import { endpoints } from './apiEndpoints';

const api = axios.create({
  baseURL: `http://${process.env.REACT_APP_API_HOST}:${process.env.REACT_APP_API_PORT}`,
});

export const sendCommand = (command, data = {}) => {
  return api.post(endpoints[command], data);
};

export default api;
