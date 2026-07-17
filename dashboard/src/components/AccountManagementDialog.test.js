import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import AccountManagementDialog from './AccountManagementDialog';
import {
  changeOwnPassword,
  createBrowserUser,
  deleteBrowserUser,
  listBrowserUsers,
  updateBrowserUser,
} from '../services/browserAccountApi';

let mockAuthSession;

jest.mock('../context/AuthSessionContext', () => ({
  useAuthSession: () => mockAuthSession,
}));

jest.mock('../services/browserAccountApi', () => ({
  ...jest.requireActual('../services/browserAccountApi'),
  BROWSER_USER_ROLES: ['viewer', 'operator', 'admin'],
  changeOwnPassword: jest.fn(),
  createBrowserUser: jest.fn(),
  deleteBrowserUser: jest.fn(),
  listBrowserUsers: jest.fn(),
  updateBrowserUser: jest.fn(),
}));

const theme = createTheme({
  transitions: {
    duration: {
      shortest: 0,
      shorter: 0,
      short: 0,
      standard: 0,
      complex: 0,
      enteringScreen: 0,
      leavingScreen: 0,
    },
  },
  components: {
    MuiButtonBase: { defaultProps: { disableRipple: true } },
    MuiDialog: { defaultProps: { transitionDuration: 0 } },
  },
});

const users = [
  { username: 'admin', role: 'admin', enabled: true },
  { username: 'operator', role: 'operator', enabled: true },
];

const renderDialog = () => render(
  <ThemeProvider theme={theme}>
    <AccountManagementDialog open onClose={jest.fn()} />
  </ThemeProvider>
);

const userRow = (username) => screen.getByRole('listitem', { name: `Account ${username}` });

beforeEach(() => {
  jest.clearAllMocks();
  let authOperationGeneration = 0;
  mockAuthSession = {
    principal: { subject: 'operator', role: 'operator', scopes: [] },
    authOperationIsCurrent: jest.fn((generation) => generation === authOperationGeneration),
    captureAuthOperationGeneration: jest.fn(() => authOperationGeneration),
    logout: jest.fn().mockImplementation(async () => {
      authOperationGeneration += 1;
    }),
    refreshSession: jest.fn().mockResolvedValue(undefined),
    replaceSession: jest.fn(),
    replaceSessionIfCurrent: jest.fn((payload, generation) => (
      generation === authOperationGeneration ? payload : null
    )),
    setAuthOperationGeneration: (generation) => {
      authOperationGeneration = generation;
    },
  };
  listBrowserUsers.mockResolvedValue(users);
  createBrowserUser.mockResolvedValue({});
  updateBrowserUser.mockResolvedValue({});
  deleteBrowserUser.mockResolvedValue({});
});

test('lets every authenticated user rotate their password and installs the replacement session', async () => {
  const replacementSession = {
    authenticated: true,
    auth_mode: 'browser_session',
    csrf_required: true,
    csrf_header_name: 'X-PixEagle-CSRF',
    csrf_token: 'replacement-csrf',
    expires_at: 1784275200,
    principal: { subject: 'operator', role: 'operator', scopes: [] },
  };
  changeOwnPassword.mockResolvedValue(replacementSession);
  renderDialog();

  expect(screen.queryByRole('tab', { name: 'Users' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Current password/), {
    target: { value: 'old-secret' },
  });
  fireEvent.change(screen.getByLabelText(/^New password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.change(screen.getByLabelText(/Confirm new password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Change password' }));

  await waitFor(() => {
    expect(changeOwnPassword).toHaveBeenCalledWith({
      currentPassword: 'old-secret',
      newPassword: 'new-secret',
    });
  });
  expect(mockAuthSession.replaceSessionIfCurrent).toHaveBeenCalledWith(replacementSession, 0);
  expect(mockAuthSession.replaceSession).not.toHaveBeenCalled();
  expect(mockAuthSession.refreshSession).not.toHaveBeenCalled();
  expect(await screen.findByText('Password changed.')).toBeInTheDocument();
});

test('refreshes auth state when password rotation does not return a replacement session', async () => {
  changeOwnPassword.mockResolvedValue({ changed: true });
  renderDialog();

  fireEvent.change(screen.getByLabelText(/Current password/), {
    target: { value: 'old-secret' },
  });
  fireEvent.change(screen.getByLabelText(/^New password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.change(screen.getByLabelText(/Confirm new password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Change password' }));

  await waitFor(() => {
    expect(mockAuthSession.refreshSession).toHaveBeenCalledWith({ silent: true });
  });
  expect(mockAuthSession.replaceSession).not.toHaveBeenCalled();
});

test('revokes a replacement session returned after the operator logged out', async () => {
  let resolvePasswordChange;
  const replacementSession = {
    authenticated: true,
    auth_mode: 'browser_session',
    csrf_required: true,
    csrf_header_name: 'X-PixEagle-CSRF',
    csrf_token: 'late-csrf',
    expires_at: 1784275200,
    principal: { subject: 'operator', role: 'operator', scopes: [] },
  };
  changeOwnPassword.mockImplementationOnce(() => new Promise((resolve) => {
    resolvePasswordChange = resolve;
  }));
  renderDialog();

  fireEvent.change(screen.getByLabelText(/Current password/), {
    target: { value: 'old-secret' },
  });
  fireEvent.change(screen.getByLabelText(/^New password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.change(screen.getByLabelText(/Confirm new password/), {
    target: { value: 'new-secret' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Change password' }));
  await waitFor(() => expect(changeOwnPassword).toHaveBeenCalledTimes(1));

  mockAuthSession.setAuthOperationGeneration(1);
  resolvePasswordChange(replacementSession);

  await waitFor(() => expect(mockAuthSession.logout).toHaveBeenCalledTimes(1));
  expect(mockAuthSession.replaceSessionIfCurrent).toHaveBeenCalledWith(replacementSession, 0);
  expect(mockAuthSession.replaceSession).toHaveBeenCalledWith(replacementSession);
  expect(await screen.findByText(/Password changed after the session ended/)).toBeInTheDocument();
});

test('admin role changes require confirmation and surface backend self-mutation errors', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  updateBrowserUser.mockRejectedValue({
    data: {
      code: 'browser_user_self_admin_update_rejected',
      detail: 'Administrators cannot demote their own active account.',
    },
  });
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'Users' }));
  await screen.findByTitle('admin');

  fireEvent.mouseDown(within(userRow('admin')).getByLabelText('Role'));
  fireEvent.click(screen.getByRole('option', { name: 'viewer' }));
  expect(screen.getByText('Change admin role to viewer?')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

  await waitFor(() => {
    expect(updateBrowserUser).toHaveBeenCalledWith('admin', { role: 'viewer' });
  });
  expect(await screen.findByText(
    'Administrators cannot demote their own active account. '
      + '(browser_user_self_admin_update_rejected)'
  )).toBeInTheDocument();
});

test('admin can create, disable, reset, and delete accounts through confirmed mutations', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'Users' }));
  await screen.findByTitle('operator');

  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
  fireEvent.change(screen.getByLabelText(/Username/), { target: { value: 'viewer-one' } });
  fireEvent.change(screen.getByLabelText(/^Initial password/), {
    target: { value: 'initial-secret' },
  });
  fireEvent.change(screen.getByLabelText(/Confirm initial password/), {
    target: { value: 'initial-secret' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));

  await waitFor(() => {
    expect(createBrowserUser).toHaveBeenCalledWith({
      username: 'viewer-one',
      role: 'operator',
      password: 'initial-secret',
      enabled: true,
    });
  });

  fireEvent.click(within(userRow('operator')).getByRole('checkbox', { name: 'Disable operator' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => {
    expect(updateBrowserUser).toHaveBeenCalledWith('operator', { enabled: false });
  });

  fireEvent.click(within(userRow('operator')).getByRole('button', {
    name: 'Reset password for operator',
  }));
  fireEvent.change(screen.getByLabelText(/^New password/), {
    target: { value: 'reset-secret' },
  });
  fireEvent.change(screen.getByLabelText(/Confirm new password/), {
    target: { value: 'reset-secret' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => {
    expect(updateBrowserUser).toHaveBeenCalledWith('operator', { password: 'reset-secret' });
  });

  fireEvent.click(within(userRow('operator')).getByRole('button', { name: 'Delete operator' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => {
    expect(deleteBrowserUser).toHaveBeenCalledWith('operator');
  });
});

test('keeps the dialog content free of horizontal overflow', () => {
  renderDialog();

  expect(screen.getByTestId('account-dialog-content')).toHaveStyle({
    overflowX: 'hidden',
  });
});
