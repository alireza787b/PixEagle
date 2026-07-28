import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import RestartButton from './RestartButton';

const mockRestartNow = jest.fn();
let mockHasScope;
let mockRestartContext;

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => ({ hasScope: mockHasScope }),
}));

jest.mock('../context/PendingRestartContext', () => ({
  usePendingRestart: () => mockRestartContext,
}));

beforeEach(() => {
  mockRestartNow.mockReset();
  mockRestartNow.mockResolvedValue({ success: true });
  mockHasScope = () => true;
  mockRestartContext = {
    runtimeStatus: {
      restart_action: { available: true, reason: 'available' },
    },
    manualRestartActionAvailable: true,
    restarting: false,
    restartNow: mockRestartNow,
  };
});

test('confirms and executes the typed guarded restart action', async () => {
  render(<RestartButton />);

  fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
  const dialog = await screen.findByRole('dialog');
  expect(dialog).toHaveTextContent('Restart PixEagle?');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Restart' }));

  await waitFor(() => {
    expect(mockRestartNow).toHaveBeenCalledWith({
      requirePending: false,
      reason: 'manual_operator_restart',
      metadata: { ui: 'dashboard_navigation' },
    });
  });
});

test('does not offer restart without system administration scope', () => {
  mockHasScope = () => false;

  render(<RestartButton />);

  expect(screen.getByRole('button', { name: 'Restart' })).toBeDisabled();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

test('shows an operator-visible error when restart is rejected', async () => {
  mockRestartNow.mockResolvedValue({
    success: false,
    error: 'Restart is blocked while following is active.',
  });

  render(<RestartButton />);

  fireEvent.click(screen.getByRole('button', { name: 'Restart' }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.click(within(dialog).getByRole('button', { name: 'Restart' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Restart is blocked while following is active.'
  );
});
