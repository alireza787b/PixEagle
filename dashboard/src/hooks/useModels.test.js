import { act, renderHook } from '@testing-library/react';
import apiClient from '../services/apiClient';
import { endpoints } from '../services/apiEndpoints';
import * as modelHooks from './useModels';

jest.mock('../services/apiClient', () => ({
  __esModule: true,
  default: {
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

  test('keeps trust metadata on local multipart uploads', async () => {
    apiClient.post.mockResolvedValue({
      data: {
        status: 'success',
        filename: 'trusted.pt',
        artifact_sha256: 'a'.repeat(64),
        trust_method: 'operator_assertion',
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
      });
    });

    expect(response.success).toBe(true);
    expect(apiClient.post).toHaveBeenCalledTimes(1);
    const [url, formData, config] = apiClient.post.mock.calls[0];
    expect(url).toBe(endpoints.modelUpload);
    expect(formData.get('file')).toBe(file);
    expect(formData.get('auto_export_ncnn')).toBe('true');
    expect(formData.get('expected_sha256')).toBe('a'.repeat(64));
    expect(formData.get('trust_model')).toBe('true');
    expect(config.headers['Content-Type']).toBe('multipart/form-data');
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
