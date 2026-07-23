import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ModelsPage from './ModelsPage';

const mockUploadModel = jest.fn();
const mockResetUpload = jest.fn();
const mockSwitchModel = jest.fn();
const mockRefetch = jest.fn();
let mockModelsState;

jest.mock('../hooks/useModels', () => ({
  useModels: () => mockModelsState,
  useSwitchModel: () => ({ switchModel: mockSwitchModel, switching: false }),
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
    mockModelsState = {
      models: {},
      currentModel: null,
      configuredGpuModel: null,
      configuredCpuModel: null,
      runtime: null,
      activeModelId: null,
      activeModelSource: 'none',
      activeModelSummary: null,
      loading: false,
      error: null,
      refetch: mockRefetch,
      rescan: jest.fn(),
    };
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
    fireEvent.change(screen.getByLabelText('Display name (optional)'), {
      target: { value: 'Aerial Vehicle Nano' },
    });
    fireEvent.click(screen.getByLabelText('I trust this checkpoint source and approve model loading'));
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));

    await waitFor(() => {
      expect(mockUploadModel).toHaveBeenCalledWith(file, {
        autoExportNcnn: false,
        expectedSha256: 'a'.repeat(64),
        trustModel: true,
        displayName: 'Aerial Vehicle Nano',
      });
    });
  });

  test('distinguishes selected standby model and applies a new selection', async () => {
    mockModelsState = {
      ...mockModelsState,
      models: {
        selected: { name: 'selected.pt', path: 'models/selected.pt', task: 'detect' },
        alternate: { name: 'alternate.pt', path: 'models/alternate.pt', task: 'obb' },
      },
      currentModel: 'selected.pt',
      activeModelId: 'selected',
      activeModelSource: 'configured',
      activeModelSummary: {
        model_name: 'selected.pt',
        task: 'detect',
        num_labels: 3,
      },
    };
    mockSwitchModel.mockResolvedValue({
      success: true,
      action: 'model_configured',
    });

    render(<ModelsPage />);

    expect(screen.getByText('Selected Model')).toBeInTheDocument();
    expect(screen.getByText('selected')).toBeInTheDocument();
    expect(screen.getByRole('button', {
      name: 'selected.pt is selected for Smart Mode',
    })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', {
      name: 'Select alternate.pt for Smart Mode',
    }));

    await waitFor(() => {
      expect(mockSwitchModel).toHaveBeenCalledWith('models/alternate.pt');
    });
    expect(await screen.findByText('Selected for Smart Mode: alternate.pt')).toBeInTheDocument();
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  test('uses immutable ids when two models share a display name', () => {
    mockModelsState = {
      ...mockModelsState,
      models: {
        selected: { name: 'Shared label', path: 'models/selected.pt', task: 'detect' },
        alternate: { name: 'Shared label', path: 'models/alternate.pt', task: 'detect' },
      },
      currentModel: 'selected.pt',
      activeModelId: 'selected',
      activeModelSource: 'configured',
      activeModelSummary: {
        model_name: 'Shared label',
        task: 'detect',
        num_labels: 3,
      },
    };

    render(<ModelsPage />);

    expect(screen.getByRole('button', {
      name: 'Shared label is selected for Smart Mode',
    })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', {
      name: 'Select Shared label for Smart Mode',
    })).toHaveAttribute('aria-pressed', 'false');
  });

  test('shows structured model selection errors to the operator', async () => {
    mockModelsState = {
      ...mockModelsState,
      models: {
        alternate: { name: 'alternate.pt', path: 'models/alternate.pt', task: 'obb' },
      },
    };
    mockSwitchModel.mockResolvedValue({
      success: false,
      error: 'Model trust evidence is missing',
    });

    render(<ModelsPage />);
    fireEvent.click(screen.getByRole('button', {
      name: 'Select alternate.pt for Smart Mode',
    }));

    expect(await screen.findByText('Model trust evidence is missing')).toBeInTheDocument();
  });

  test('shows the runtime fallback policy from the canonical backend field', () => {
    mockModelsState = {
      ...mockModelsState,
      currentModel: 'aerial.pt',
      runtime: {
        model_name: 'aerial.pt',
        effective_device: 'cuda',
        backend: 'cuda',
        fallback_enabled: true,
      },
      activeModelSource: 'runtime',
      activeModelSummary: {
        model_name: 'aerial.pt',
        task: 'detect',
        num_labels: 3,
      },
    };

    render(<ModelsPage />);

    expect(screen.getByText('GPU-to-CPU Fallback')).toBeInTheDocument();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });
});
