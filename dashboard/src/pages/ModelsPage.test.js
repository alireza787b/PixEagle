import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ModelsPage from './ModelsPage';

const mockUploadModel = jest.fn();
const mockResetUpload = jest.fn();

jest.mock('../hooks/useModels', () => ({
  useModels: () => ({
    models: {},
    currentModel: null,
    configuredGpuModel: null,
    configuredCpuModel: null,
    runtime: null,
    activeModelId: null,
    activeModelSummary: null,
    loading: false,
    error: null,
    refetch: jest.fn(),
    rescan: jest.fn(),
  }),
  useSwitchModel: () => ({ switchModel: jest.fn(), switching: false }),
  useDeleteModel: () => ({ deleteModel: jest.fn(), deleting: false }),
  useUploadModel: () => ({
    uploadModel: mockUploadModel,
    uploading: false,
    uploadProgress: 0,
    resetUpload: mockResetUpload,
  }),
  useModelLabels: () => ({ fetchLabels: jest.fn() }),
}));

jest.mock('../services/apiClient', () => ({
  downloadApiBlob: jest.fn(),
}));

describe('ModelsPage local model registration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUploadModel.mockResolvedValue({ success: true, filename: 'trusted.pt' });
  });

  test('does not expose arbitrary server-side URL ingestion', () => {
    render(<ModelsPage />);

    expect(screen.getByText('No models found. Upload a model below.')).toBeInTheDocument();
    expect(screen.getByText('Choose Model File')).toBeInTheDocument();
    expect(screen.getByLabelText('Expected SHA-256 (recommended)')).toBeInTheDocument();
    expect(screen.queryByLabelText('HTTPS URL')).not.toBeInTheDocument();
    expect(screen.queryByText('Download HTTPS')).not.toBeInTheDocument();
  });

  test('retains trust-aware authenticated file upload options', async () => {
    render(<ModelsPage />);
    const file = new File(['checkpoint'], 'trusted.pt', { type: 'application/octet-stream' });

    fireEvent.change(screen.getByLabelText('Choose Model File'), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText('Expected SHA-256 (recommended)'), {
      target: { value: 'a'.repeat(64) },
    });
    fireEvent.click(screen.getByLabelText('I trust this checkpoint source and approve model loading'));
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => {
      expect(mockUploadModel).toHaveBeenCalledWith(file, {
        autoExportNcnn: false,
        expectedSha256: 'a'.repeat(64),
        trustModel: true,
      });
    });
  });
});
