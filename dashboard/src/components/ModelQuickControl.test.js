import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ModelQuickControl from './ModelQuickControl';

const mockSwitchModel = jest.fn();
const mockRefetchActive = jest.fn();
const mockRefetchModels = jest.fn();

jest.mock('../hooks/useModels', () => ({
  useActiveModel: () => ({
    activeModel: {
      model_id: 'demo',
      model_name: 'demo.pt',
      model_path: 'models/demo.pt',
      task: 'detect',
      num_labels: 4,
    },
    runtime: null,
    loading: false,
    refetch: mockRefetchActive,
  }),
  useModels: () => ({
    models: {
      demo: { name: 'demo.pt', path: 'models/demo.pt' },
    },
    loading: false,
    refetch: mockRefetchModels,
  }),
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
      expect(screen.getByText('Model selected for Smart Mode')).toBeInTheDocument();
      expect(mockRefetchActive).toHaveBeenCalledTimes(1);
      expect(mockRefetchModels).toHaveBeenCalledTimes(1);
    });
  });
});
