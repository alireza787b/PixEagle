import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ModelQuickControl from './ModelQuickControl';

const mockSwitchModel = jest.fn();
const mockRefetchActive = jest.fn();
const mockRefetchModels = jest.fn();
let mockActiveState;
let mockInventoryState;

jest.mock('../hooks/useModels', () => ({
  useActiveModel: () => mockActiveState,
  useModels: () => mockInventoryState,
  useSwitchModel: () => ({
    switchModel: mockSwitchModel,
    switching: false,
  }),
  useModelLabels: () => ({
    fetchLabels: jest.fn(),
    loading: false,
  }),
}));

describe('ModelQuickControl', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockActiveState = {
      activeModel: {
        model_id: 'demo',
        model_name: 'demo.pt',
        model_path: 'models/demo.pt',
        task: 'detect',
        num_labels: 4,
      },
      runtime: null,
      capability: { available: true, reason: null },
      loading: false,
      refetch: mockRefetchActive,
    };
    mockInventoryState = {
      models: {
        demo: { name: 'demo.pt', path: 'models/demo.pt' },
      },
      capability: { available: true, reason: null },
      loading: false,
      refetch: mockRefetchModels,
    };
  });

  test('reports standby selection and refreshes both model views', async () => {
    mockSwitchModel.mockResolvedValue({
      success: true,
      action: 'model_configured',
    });

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ModelQuickControl />
      </MemoryRouter>
    );

    const selectButton = await screen.findByRole('button', {
      name: 'Select detection model for Smart Mode',
    });
    await waitFor(() => expect(selectButton).toBeEnabled());
    fireEvent.click(selectButton);

    await waitFor(() => {
      expect(mockSwitchModel).toHaveBeenCalledWith('models/demo.pt', 'auto');
    });
    expect(await screen.findByText('Model selected for Smart Mode')).toBeInTheDocument();
    expect(mockRefetchActive).toHaveBeenCalledTimes(1);
    expect(mockRefetchModels).toHaveBeenCalledTimes(1);
  });

  test('shows an unavailable state without offering model selection', () => {
    mockInventoryState = {
      ...mockInventoryState,
      capability: {
        available: false,
        reason: 'Secure model storage is unavailable on this host',
      },
    };

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ModelQuickControl />
      </MemoryRouter>
    );

    expect(screen.getByText('Unavailable')).toBeInTheDocument();
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {
      name: 'Select detection model for Smart Mode',
    })).not.toBeInTheDocument();
  });

  test('can leave Smart setup when model capability is unavailable', () => {
    const onCancelSetup = jest.fn();
    mockInventoryState = {
      ...mockInventoryState,
      capability: {
        available: false,
        reason: 'AI dependencies are not installed',
      },
    };

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ModelQuickControl setupMode onCancelSetup={onCancelSetup} />
      </MemoryRouter>
    );

    expect(screen.getByText('Smart Model is unavailable. Classic remains active.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep Classic' }));
    expect(onCancelSetup).toHaveBeenCalledTimes(1);
  });

  test('keeps Classic truthful while recovering a missing Smart model', async () => {
    const onCancelSetup = jest.fn();
    const onModelSelected = jest.fn().mockResolvedValue(undefined);
    mockSwitchModel.mockResolvedValue({
      success: true,
      action: 'model_configured',
    });

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ModelQuickControl
          setupMode
          onCancelSetup={onCancelSetup}
          onModelSelected={onModelSelected}
        />
      </MemoryRouter>
    );

    expect(screen.getByText('Select a model to continue. Classic remains active.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep Classic' }));
    expect(onCancelSetup).toHaveBeenCalledTimes(1);

    fireEvent.click(await screen.findByRole('button', {
      name: 'Select detection model for Smart Mode',
    }));
    await waitFor(() => expect(onModelSelected).toHaveBeenCalledWith({
      success: true,
      action: 'model_configured',
    }));
    expect(screen.queryByText('Model selected for Smart Mode')).not.toBeInTheDocument();
  });

  test('offers model management when the Smart model inventory is empty', () => {
    mockActiveState = {
      ...mockActiveState,
      activeModel: null,
    };
    mockInventoryState = {
      ...mockInventoryState,
      models: {},
    };

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ModelQuickControl setupMode />
      </MemoryRouter>
    );

    expect(screen.getByText('Add a compatible model to continue. Classic remains active.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Manage Models' })).toHaveAttribute('href', '/models');
    expect(screen.queryByLabelText('Model')).not.toBeInTheDocument();
  });
});
