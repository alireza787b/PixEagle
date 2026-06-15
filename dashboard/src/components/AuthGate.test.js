import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import AuthGate from './AuthGate';

let mockAuthSession;

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => mockAuthSession,
}));

const baseAuthSession = {
  authMode: 'local_compat',
  loading: false,
  loginPending: false,
  error: null,
  requiresLogin: false,
  refreshSession: jest.fn(() => Promise.resolve()),
  login: jest.fn(() => Promise.resolve()),
  clearError: jest.fn(),
};

beforeEach(() => {
  mockAuthSession = { ...baseAuthSession };
});

afterEach(() => {
  jest.clearAllMocks();
});

test('passes through children outside browser-session login requirement', () => {
  render(
    <AuthGate>
      <div>Dashboard content</div>
    </AuthGate>
  );

  expect(screen.getByText('Dashboard content')).toBeInTheDocument();
});

test('shows browser-session login form and submits credentials', async () => {
  mockAuthSession = {
    ...baseAuthSession,
    authMode: 'browser_session',
    requiresLogin: true,
    login: jest.fn(() => Promise.resolve()),
  };

  render(
    <AuthGate>
      <div>Dashboard content</div>
    </AuthGate>
  );

  expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Username/), { target: { value: 'operator' } });
  fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));

  await waitFor(() => {
    expect(mockAuthSession.login).toHaveBeenCalledWith({
      username: 'operator',
      password: 'secret',
    });
  });
});

test('blocks dashboard in machine bearer mode', () => {
  mockAuthSession = {
    ...baseAuthSession,
    authMode: 'machine_bearer',
  };

  render(
    <AuthGate>
      <div>Dashboard content</div>
    </AuthGate>
  );

  expect(screen.getByText('Dashboard access unavailable')).toBeInTheDocument();
  expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument();
});
