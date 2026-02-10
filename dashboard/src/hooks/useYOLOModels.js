// dashboard/src/hooks/useYOLOModels.js

/**
 * React hooks for YOLO Model Management
 *
 * Provides hooks for:
 * - Fetching available YOLO models
 * - Switching models in SmartTracker
 * - Uploading new models
 * - Deleting models
 *
 * Mirrors the pattern from useTrackerSchema.js and useFollowerSchema.js
 *
 * Project: PixEagle
 * Author: Alireza Ghaderi
 * Repository: https://github.com/alireza787b/PixEagle
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { apiConfig } from '../services/apiEndpoints';

const API_URL = `${apiConfig.protocol}://${apiConfig.apiHost}:${apiConfig.apiPort}`;
const NO_CACHE_HEADERS = {
  'Cache-Control': 'no-cache, no-store, must-revalidate',
  Pragma: 'no-cache',
  Expires: '0',
};
const buildNoCacheRequestConfig = () => ({
  headers: NO_CACHE_HEADERS,
  params: { _t: Date.now() },
});

/**
 * Hook to fetch available YOLO models
 * @param {number} refreshInterval - Polling interval in milliseconds (default: 10000)
 * @returns {Object} { models, currentModel, configuredModel, loading, error, refetch }
 */
export const useYOLOModels = (refreshInterval = 10000) => {
  const [models, setModels] = useState(null);
  const [currentModel, setCurrentModel] = useState(null);
  const [configuredModel, setConfiguredModel] = useState(null);
  const [configuredGpuModel, setConfiguredGpuModel] = useState(null);
  const [configuredCpuModel, setConfiguredCpuModel] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [activeModelId, setActiveModelId] = useState(null);
  const [activeModelSource, setActiveModelSource] = useState('none');
  const [activeModelSummary, setActiveModelSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastSuccessfulData = useRef(null);

  const fetchModels = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/yolo/models`, buildNoCacheRequestConfig());

      // Only update if data actually changed
      const dataString = JSON.stringify(response.data);
      if (dataString !== JSON.stringify(lastSuccessfulData.current)) {
        setModels(response.data.models || {});
        setCurrentModel(response.data.current_model || null);
        setConfiguredModel(response.data.configured_model || null);
        setConfiguredGpuModel(response.data.configured_gpu_model || null);
        setConfiguredCpuModel(response.data.configured_cpu_model || null);
        setRuntime(response.data.runtime || null);
        setActiveModelId(response.data.active_model_id || null);
        setActiveModelSource(response.data.active_model_source || 'none');
        setActiveModelSummary(response.data.active_model_summary || null);
        lastSuccessfulData.current = response.data;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching YOLO models:', err);
      setError(err.message);

      // Keep previous successful data on error
      if (lastSuccessfulData.current) {
        setModels(lastSuccessfulData.current.models || {});
        setCurrentModel(lastSuccessfulData.current.current_model || null);
        setConfiguredModel(lastSuccessfulData.current.configured_model || null);
        setConfiguredGpuModel(lastSuccessfulData.current.configured_gpu_model || null);
        setConfiguredCpuModel(lastSuccessfulData.current.configured_cpu_model || null);
        setRuntime(lastSuccessfulData.current.runtime || null);
        setActiveModelId(lastSuccessfulData.current.active_model_id || null);
        setActiveModelSource(lastSuccessfulData.current.active_model_source || 'none');
        setActiveModelSummary(lastSuccessfulData.current.active_model_summary || null);
      }

      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();

    const interval = setInterval(fetchModels, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchModels, refreshInterval]);

  return useMemo(
    () => ({
      models,
      currentModel,
      configuredModel,
      configuredGpuModel,
      configuredCpuModel,
      runtime,
      activeModelId,
      activeModelSource,
      activeModelSummary,
      loading,
      error,
      refetch: fetchModels
    }),
    [
      models,
      currentModel,
      configuredModel,
      configuredGpuModel,
      configuredCpuModel,
      runtime,
      activeModelId,
      activeModelSource,
      activeModelSummary,
      loading,
      error,
      fetchModels
    ]
  );
};

/**
 * Hook to fetch model label metadata on demand (for detail dialogs, search, etc.).
 * @returns {Object} { fetchLabels, loading, error }
 */
export const useYOLOModelLabels = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLabels = useCallback(async (modelId, options = {}) => {
    const {
      offset = 0,
      limit = 500,
      search = '',
      forceRescan = false,
    } = options;

    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(
        `${API_URL}/api/yolo/models/${encodeURIComponent(modelId)}/labels`,
        {
          ...buildNoCacheRequestConfig(),
          params: {
            offset,
            limit,
            search: search || undefined,
            force_rescan: forceRescan ? 'true' : 'false',
            _t: Date.now(),
          },
        }
      );

      const payload = response.data || {};
      if (payload.status !== 'success') {
        throw new Error(payload.error || 'Failed to fetch model labels');
      }

      return {
        success: true,
        modelId: payload.model_id,
        modelName: payload.model_name,
        totalLabels: payload.total_labels ?? 0,
        filteredCount: payload.filtered_count ?? 0,
        returnedCount: payload.returned_count ?? 0,
        hasMore: Boolean(payload.has_more),
        labels: payload.labels || [],
      };
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to fetch model labels';
      setError(errorMsg);
      return {
        success: false,
        error: errorMsg,
        labels: [],
      };
    } finally {
      setLoading(false);
    }
  }, []);

  return useMemo(
    () => ({
      fetchLabels,
      loading,
      error,
    }),
    [fetchLabels, loading, error]
  );
};

/**
 * Hook to switch YOLO model in SmartTracker
 * @returns {Object} { switchModel, switching, switchError }
 */
export const useSwitchYOLOModel = () => {
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const switchModel = useCallback(async (modelPath, device = 'auto') => {
    setSwitching(true);
    setSwitchError(null);

    try {
      const response = await axios.post(`${API_URL}/api/yolo/switch-model`, {
        model_path: modelPath,
        device: device
      });

      if (response.data.status === 'success') {
        setSwitching(false);
        return {
          success: true,
          message: response.data.message,
          modelInfo: response.data.model_info,
          runtime: response.data.runtime || response.data.model_info?.runtime || null,
        };
      } else {
        setSwitchError(response.data.error || 'Failed to switch model');
        setSwitching(false);
        return {
          success: false,
          error: response.data.error
        };
      }
    } catch (err) {
      console.error('Error switching YOLO model:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to switch model';
      setSwitchError(errorMsg);
      setSwitching(false);
      return {
        success: false,
        error: errorMsg
      };
    }
  }, []);

  return useMemo(
    () => ({
      switchModel,
      switching,
      switchError
    }),
    [switchModel, switching, switchError]
  );
};

/**
 * Hook to upload a new YOLO model
 * @returns {Object} { uploadModel, uploading, uploadError, uploadProgress }
 */
export const useUploadYOLOModel = () => {
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);

  const uploadModel = useCallback(async (file, autoExportNcnn = true) => {
    setUploading(true);
    setUploadError(null);
    setUploadProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('auto_export_ncnn', autoExportNcnn ? 'true' : 'false');

      const response = await axios.post(`${API_URL}/api/yolo/upload`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(percentCompleted);
        }
      });

      if (response.data.status === 'success') {
        setUploading(false);
        setUploadProgress(100);
        return {
          success: true,
          message: response.data.message,
          filename: response.data.filename,
          modelInfo: response.data.model_info,
          ncnnExported: response.data.ncnn_exported,
          ncnnExport: response.data.ncnn_export || null,
        };
      } else {
        setUploadError(response.data.error || 'Upload failed');
        setUploading(false);
        setUploadProgress(0);
        return {
          success: false,
          error: response.data.error
        };
      }
    } catch (err) {
      console.error('Error uploading YOLO model:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Upload failed';
      setUploadError(errorMsg);
      setUploading(false);
      setUploadProgress(0);
      return {
        success: false,
        error: errorMsg
      };
    }
  }, []);

  const resetUpload = useCallback(() => {
    setUploading(false);
    setUploadError(null);
    setUploadProgress(0);
  }, []);

  return useMemo(
    () => ({
      uploadModel,
      uploading,
      uploadError,
      uploadProgress,
      resetUpload
    }),
    [uploadModel, uploading, uploadError, uploadProgress, resetUpload]
  );
};

/**
 * Hook to delete a YOLO model
 * @returns {Object} { deleteModel, deleting, deleteError }
 */
export const useDeleteYOLOModel = () => {
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const deleteModel = useCallback(async (modelId) => {
    setDeleting(true);
    setDeleteError(null);

    try {
      const response = await axios.post(`${API_URL}/api/yolo/delete/${modelId}`);

      if (response.data.status === 'success') {
        setDeleting(false);
        return {
          success: true,
          message: response.data.message
        };
      } else {
        setDeleteError(response.data.error || 'Delete failed');
        setDeleting(false);
        return {
          success: false,
          error: response.data.error
        };
      }
    } catch (err) {
      console.error('Error deleting YOLO model:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Delete failed';
      setDeleteError(errorMsg);
      setDeleting(false);
      return {
        success: false,
        error: errorMsg
      };
    }
  }, []);

  return useMemo(
    () => ({
      deleteModel,
      deleting,
      deleteError
    }),
    [deleteModel, deleting, deleteError]
  );
};
