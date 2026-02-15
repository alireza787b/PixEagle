// dashboard/src/hooks/useModels.js

/**
 * React hooks for Detection Model Management
 *
 * Provides hooks for:
 * - Fetching available detection models
 * - Fetching active model status (lightweight)
 * - Switching models in SmartTracker
 * - Uploading new models
 * - Downloading models by name
 * - Deleting models
 * - Fetching model labels
 *
 * Project: PixEagle
 * Author: Alireza Ghaderi
 * Repository: https://github.com/alireza787b/PixEagle
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { endpoints } from '../services/apiEndpoints';

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
 * Hook to fetch all available detection models (full inventory).
 * @param {number} refreshInterval - Polling interval in ms (default: 10000)
 */
export const useModels = (refreshInterval = 10000) => {
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
      const response = await axios.get(endpoints.models, buildNoCacheRequestConfig());
      const data = response.data || {};

      const dataString = JSON.stringify(data);
      if (dataString !== JSON.stringify(lastSuccessfulData.current)) {
        setModels(data.models || {});
        setCurrentModel(data.current_model || null);
        setConfiguredModel(data.configured_model || null);
        setConfiguredGpuModel(data.configured_gpu_model || null);
        setConfiguredCpuModel(data.configured_cpu_model || null);
        setRuntime(data.runtime || null);
        setActiveModelId(data.active_model_id || null);
        setActiveModelSource(data.active_model_source || 'none');
        setActiveModelSummary(data.active_model_summary || null);
        lastSuccessfulData.current = data;
      }

      setError(null);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching detection models:', err);
      setError(err.message);

      if (lastSuccessfulData.current) {
        const data = lastSuccessfulData.current;
        setModels(data.models || {});
        setCurrentModel(data.current_model || null);
        setConfiguredModel(data.configured_model || null);
        setConfiguredGpuModel(data.configured_gpu_model || null);
        setConfiguredCpuModel(data.configured_cpu_model || null);
        setRuntime(data.runtime || null);
        setActiveModelId(data.active_model_id || null);
        setActiveModelSource(data.active_model_source || 'none');
        setActiveModelSummary(data.active_model_summary || null);
      }

      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
    const interval = setInterval(fetchModels, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchModels, refreshInterval]);

  // Force rescan: re-discovers model files on disk, ignoring .models.json cache.
  // Use when model files were added/removed/moved outside the API (e.g., manual scp).
  const rescan = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(endpoints.models, {
        ...buildNoCacheRequestConfig(),
        params: { force_rescan: 'true', _t: Date.now() },
      });
      const data = response.data || {};
      setModels(data.models || {});
      setCurrentModel(data.current_model || null);
      setConfiguredModel(data.configured_model || null);
      setConfiguredGpuModel(data.configured_gpu_model || null);
      setConfiguredCpuModel(data.configured_cpu_model || null);
      setRuntime(data.runtime || null);
      setActiveModelId(data.active_model_id || null);
      setActiveModelSource(data.active_model_source || 'none');
      setActiveModelSummary(data.active_model_summary || null);
      lastSuccessfulData.current = data;
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

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
      refetch: fetchModels,
      rescan,
    }),
    [models, currentModel, configuredModel, configuredGpuModel, configuredCpuModel,
     runtime, activeModelId, activeModelSource, activeModelSummary, loading, error, fetchModels, rescan]
  );
};

/**
 * Lightweight hook for dashboard — fetches only the active model status.
 * @param {number} refreshInterval - Polling interval in ms (default: 5000)
 */
export const useActiveModel = (refreshInterval = 5000) => {
  const [activeModel, setActiveModel] = useState(null);
  const [runtime, setRuntime] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchActive = useCallback(async () => {
    try {
      const response = await axios.get(endpoints.activeModel, buildNoCacheRequestConfig());
      const data = response.data || {};
      // active_model_summary contains model_name, model_id, task, device, backend, etc.
      setActiveModel(data.active_model_summary || null);
      setRuntime(data.runtime || null);
      setError(null);
      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActive();
    const interval = setInterval(fetchActive, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchActive, refreshInterval]);

  return useMemo(
    () => ({ activeModel, runtime, loading, error, refetch: fetchActive }),
    [activeModel, runtime, loading, error, fetchActive]
  );
};

/**
 * Hook to fetch model labels on demand.
 */
export const useModelLabels = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLabels = useCallback(async (modelId, options = {}) => {
    const { offset = 0, limit = 500, search = '', forceRescan = false } = options;
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(endpoints.modelLabels(modelId), {
        ...buildNoCacheRequestConfig(),
        params: {
          offset,
          limit,
          search: search || undefined,
          force_rescan: forceRescan ? 'true' : 'false',
          _t: Date.now(),
        },
      });

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
      return { success: false, error: errorMsg, labels: [] };
    } finally {
      setLoading(false);
    }
  }, []);

  return useMemo(() => ({ fetchLabels, loading, error }), [fetchLabels, loading, error]);
};

/**
 * Hook to switch the active detection model.
 */
export const useSwitchModel = () => {
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(null);

  const switchModel = useCallback(async (modelPath, device = 'auto') => {
    setSwitching(true);
    setSwitchError(null);

    try {
      const response = await axios.post(endpoints.switchModel, {
        model_path: modelPath,
        device,
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
        return { success: false, error: response.data.error };
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to switch model';
      setSwitchError(errorMsg);
      setSwitching(false);
      return { success: false, error: errorMsg };
    }
  }, []);

  return useMemo(
    () => ({ switchModel, switching, switchError }),
    [switchModel, switching, switchError]
  );
};

/**
 * Hook to upload a new detection model.
 */
export const useUploadModel = () => {
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

      const response = await axios.post(endpoints.modelUpload, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const pct = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setUploadProgress(pct);
        },
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
        return { success: false, error: response.data.error };
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Upload failed';
      setUploadError(errorMsg);
      setUploading(false);
      setUploadProgress(0);
      return { success: false, error: errorMsg };
    }
  }, []);

  const resetUpload = useCallback(() => {
    setUploading(false);
    setUploadError(null);
    setUploadProgress(0);
  }, []);

  return useMemo(
    () => ({ uploadModel, uploading, uploadError, uploadProgress, resetUpload }),
    [uploadModel, uploading, uploadError, uploadProgress, resetUpload]
  );
};

/**
 * Hook to download a detection model by name or URL.
 */
export const useDownloadModel = () => {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  const downloadModel = useCallback(async (modelName, downloadUrl = null, autoExportNcnn = true) => {
    setDownloading(true);
    setDownloadError(null);

    try {
      const response = await axios.post(endpoints.modelDownload, {
        model_name: modelName,
        download_url: downloadUrl || undefined,
        auto_export_ncnn: autoExportNcnn,
      });

      if (response.data.status === 'success') {
        setDownloading(false);
        return {
          success: true,
          message: response.data.message,
          modelName: response.data.model_name,
          ncnnExported: response.data.ncnn_exported,
          ncnnExport: response.data.ncnn_export || null,
        };
      } else {
        setDownloadError(response.data.error || 'Download failed');
        setDownloading(false);
        return {
          success: false,
          error: response.data.error,
          suggestedUrls: response.data.suggested_urls || [],
        };
      }
    } catch (err) {
      const errorData = err.response?.data;
      const errorMsg = errorData?.error || errorData?.detail || err.message || 'Download failed';
      const suggestedUrls = errorData?.suggested_urls || [];
      setDownloadError(errorMsg);
      setDownloading(false);
      return { success: false, error: errorMsg, suggestedUrls };
    }
  }, []);

  const resetDownload = useCallback(() => {
    setDownloading(false);
    setDownloadError(null);
  }, []);

  return useMemo(
    () => ({ downloadModel, downloading, downloadError, resetDownload }),
    [downloadModel, downloading, downloadError, resetDownload]
  );
};

/**
 * Hook to delete a detection model.
 */
export const useDeleteModel = () => {
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const deleteModel = useCallback(async (modelId) => {
    setDeleting(true);
    setDeleteError(null);

    try {
      const response = await axios.delete(endpoints.modelDelete(modelId));

      if (response.data.status === 'success') {
        setDeleting(false);
        return { success: true, message: response.data.message };
      } else {
        setDeleteError(response.data.error || 'Delete failed');
        setDeleting(false);
        return { success: false, error: response.data.error };
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Delete failed';
      setDeleteError(errorMsg);
      setDeleting(false);
      return { success: false, error: errorMsg };
    }
  }, []);

  return useMemo(
    () => ({ deleteModel, deleting, deleteError }),
    [deleteModel, deleting, deleteError]
  );
};
