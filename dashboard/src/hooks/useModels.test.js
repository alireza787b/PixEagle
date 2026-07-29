import { act, renderHook, waitFor } from '@testing-library/react';
import apiClient from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import * as modelHooks from './useModels';

jest.mock('../services/apiClient', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

describe('model ingestion hooks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('does not export a server-side URL download hook', () => {
    expect(modelHooks.useDownloadModel).toBeUndefined();
  });

  test('exposes the model-management capability reported by the backend', async () => {
    apiClient.get.mockResolvedValue({
      data: {
        status: 'success',
        models: {},
        capability: {
          available: false,
          reason: 'Secure model storage is unavailable on this host',
        },
      },
    });
    const { result, unmount } = renderHook(() => modelHooks.useModels(60000));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.capability).toEqual({
      available: false,
      reason: 'Secure model storage is unavailable on this host',
    });
    unmount();
  });

  test('keeps trust metadata on local multipart uploads', async () => {
    apiClient.post.mockResolvedValue({
      data: {
        status: 'success',
        filename: 'trusted.pt',
        artifact_sha256: 'a'.repeat(64),
        trust_method: 'operator_assertion',
        ncnn_export_requested: true,
        ncnn_exported: false,
        ncnn_export: {
          success: false,
          error: 'pnnx is not installed',
        },
      },
    });
    const file = new File(['checkpoint'], 'trusted.pt', { type: 'application/octet-stream' });
    const { result } = renderHook(() => modelHooks.useUploadModel());

    let response;
    await act(async () => {
      response = await result.current.uploadModel(file, {
        autoExportNcnn: true,
        expectedSha256: 'a'.repeat(64),
        trustModel: true,
        displayName: 'Aerial Vehicle Nano',
        artifactFilename: 'aerial-vehicle-nano.pt',
      });
    });

    expect(response.success).toBe(true);
    expect(response.ncnnExportRequested).toBe(true);
    expect(response.ncnnExported).toBe(false);
    expect(response.ncnnExport.error).toBe('pnnx is not installed');
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    const [url, formData, config] = apiClient.post.mock.calls[0];
    expect(url).toBe(endpoints.modelUpload);
    expect(formData.get('file')).toBe(file);
    expect(formData.get('auto_export_ncnn')).toBe('true');
    expect(formData.get('expected_sha256')).toBe('a'.repeat(64));
    expect(formData.get('trust_model')).toBe('true');
    expect(formData.get('display_name')).toBe('Aerial Vehicle Nano');
    expect(formData.get('artifact_filename')).toBe('aerial-vehicle-nano.pt');
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
  });

  test('preserves model-name collision guidance from the server', async () => {
    apiClient.post.mockRejectedValue({
      response: {
        status: 409,
        data: {
          status: 'error',
          error: "Model file 'trusted.pt' already exists",
          error_code: 'MODEL_NAME_CONFLICT',
          suggested_filename: 'trusted-2.pt',
          retryable: false,
        },
      },
    });
    const file = new File(['checkpoint'], 'trusted.pt', { type: 'application/octet-stream' });
    const { result } = renderHook(() => modelHooks.useUploadModel());

    let response;
    await act(async () => {
      response = await result.current.uploadModel(file, {
        artifactFilename: 'trusted.pt',
      });
    });

    expect(response).toEqual({
      success: false,
      error: "Model file 'trusted.pt' already exists",
      errorCode: 'MODEL_NAME_CONFLICT',
      suggestedFilename: 'trusted-2.pt',
      retryable: false,
      retryAfterSeconds: null,
    });
  });

  test('preserves configured-versus-live model action semantics', async () => {
    apiClient.post.mockResolvedValue({
      data: {
        status: 'success',
        action: 'model_configured',
        message: 'selected for next activation',
        model_info: { path: '/models/aerial.pt' },
        runtime: null,
      },
    });
    const { result } = renderHook(() => modelHooks.useSwitchModel());

    let response;
    await act(async () => {
      response = await result.current.switchModel('/models/aerial.pt');
    });

    expect(response).toMatchObject({
      success: true,
      action: 'model_configured',
      message: 'selected for next activation',
    });
  });

  test('normalizes structured model-selection errors for display', async () => {
    apiClient.post.mockRejectedValue({
      response: {
        data: {
          detail: {
            error_code: 'MODEL_INVALID',
            message: 'The model is not compatible with SmartTracker',
          },
        },
      },
    });
    const { result } = renderHook(() => modelHooks.useSwitchModel());

    let response;
    await act(async () => {
      response = await result.current.switchModel('/models/invalid.pt');
    });

    expect(response).toEqual({
      success: false,
      error: 'The model is not compatible with SmartTracker',
    });
  });
});
