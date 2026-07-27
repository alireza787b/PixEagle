import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import AccountManagementDialog from './AccountManagementDialog';
import {
  changeOwnPassword,
  createBearerToken,
  createBrowserUser,
  deleteBrowserUser,
  listBearerTokens,
  listBrowserUsers,
  revokeBearerToken,
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
  createBearerToken: jest.fn(),
  createBrowserUser: jest.fn(),
  deleteBrowserUser: jest.fn(),
  listBearerTokens: jest.fn(),
  listBrowserUsers: jest.fn(),
  revokeBearerToken: jest.fn(),
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

const renderDialog = ({ onClose = jest.fn() } = {}) => render(
  <ThemeProvider theme={theme}>
    <AccountManagementDialog open onClose={onClose} />
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
  listBearerTokens.mockResolvedValue([]);
  createBearerToken.mockResolvedValue({});
  revokeBearerToken.mockResolvedValue({});
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

test('admin can create a scoped API token, copy its one-time secret, and revoke it', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  listBearerTokens.mockResolvedValueOnce([]).mockResolvedValueOnce([{
    token_id: 'token-1',
    name: 'QGC video',
    subject: 'api-client:admin',
    scopes: ['media:read'],
    state: 'active',
    created_at: '2026-07-27T10:00:00Z',
    expires_at: '2026-10-25T10:00:00Z',
    revoked_at: null,
    last_used_at: null,
  }]).mockResolvedValueOnce([{
    token_id: 'token-1',
    name: 'QGC video',
    subject: 'api-client:admin',
    scopes: ['media:read'],
    state: 'revoked',
    created_at: '2026-07-27T10:00:00Z',
    expires_at: '2026-10-25T10:00:00Z',
    revoked_at: '2026-07-27T11:00:00Z',
    last_used_at: null,
  }]);
  createBearerToken.mockResolvedValue({
    token: {
      token_id: 'token-1',
      name: 'QGC video',
      subject: 'api-client:admin',
      scopes: ['media:read'],
      state: 'active',
      created_at: '2026-07-27T10:00:00Z',
      expires_at: '2026-10-25T10:00:00Z',
      revoked_at: null,
      last_used_at: null,
    },
    access_token: 'pxe_one_time_secret',
    token_type: 'Bearer',
  });
  Object.assign(navigator, {
    clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
  });
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'API tokens' }));
  await screen.findByText('No API tokens yet.');
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Create API token' })).not.toBeDisabled();
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create API token' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Token name' }), {
    target: { value: 'QGC video' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));

  await waitFor(() => {
    expect(createBearerToken).toHaveBeenCalledWith({
      name: 'QGC video',
      scopes: ['media:read'],
      expiresInDays: 90,
    });
  });
  expect(await screen.findByDisplayValue('pxe_one_time_secret')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Copy' }));
  await waitFor(() => {
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('pxe_one_time_secret');
  });
  fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  expect(screen.queryByDisplayValue('pxe_one_time_secret')).not.toBeInTheDocument();

  fireEvent.click(within(screen.getByRole('listitem', { name: 'API token QGC video' })).getByRole(
    'button',
    { name: 'Revoke QGC video' }
  ));
  fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
  await waitFor(() => expect(revokeBearerToken).toHaveBeenCalledWith('token-1'));
  expect(await screen.findByText('API token revoked.')).toBeInTheDocument();
});

test('admin can request a lifetime API token with a clear lab warning', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  createBearerToken.mockResolvedValue({
    token: {
      token_id: 'token-lifetime',
      name: 'Lab lifetime',
      subject: 'api-client:admin',
      scopes: ['media:read'],
      state: 'active',
    },
    access_token: 'pxe_lifetime_secret',
    token_type: 'Bearer',
  });
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'API tokens' }));
  await screen.findByText('No API tokens yet.');
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Create API token' })).not.toBeDisabled();
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create API token' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Token name' }), {
    target: { value: 'Lab lifetime' },
  });
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Expires' }));
  fireEvent.click(screen.getByRole('option', { name: 'Never (lab only)' }));
  expect(screen.getByText(/remains valid until revoked/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));

  await waitFor(() => {
    expect(createBearerToken).toHaveBeenCalledWith({
      name: 'Lab lifetime',
      scopes: ['media:read'],
      expiresInDays: null,
    });
  });
});

test('preserves a one-time token secret until the admin explicitly dismisses it', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  const onClose = jest.fn();
  createBearerToken.mockResolvedValue({
    token: {
      token_id: 'token-once',
      name: 'QGC video',
      subject: 'api-client:admin',
      scopes: ['media:read'],
      state: 'active',
    },
    access_token: 'pxe_keep_until_done',
    token_type: 'Bearer',
  });
  renderDialog({ onClose });

  fireEvent.click(screen.getByRole('tab', { name: 'API tokens' }));
  await screen.findByText('No API tokens yet.');
  fireEvent.click(screen.getByRole('button', { name: 'Create API token' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Token name' }), {
    target: { value: 'QGC video' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByDisplayValue('pxe_keep_until_done')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Close account dialog' })).toBeDisabled();
  expect(screen.getByText('Close', { selector: 'button' })).toBeDisabled();
  fireEvent.click(screen.getByRole('tab', { name: 'My password' }));
  expect(screen.getByDisplayValue('pxe_keep_until_done')).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  expect(screen.getByText('Close', { selector: 'button' })).not.toBeDisabled();
  fireEvent.click(screen.getByText('Close', { selector: 'button' }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test('renders the exact privilege scopes and labels runtime authentication truthfully', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  listBearerTokens.mockResolvedValue([{
    token_id: 'token-admin',
    name: 'Automation',
    subject: 'api-client:admin',
    scopes: ['system:admin', 'media:read'],
    state: 'active',
    created_at: '2026-07-27T10:00:00Z',
    expires_at: null,
    revoked_at: null,
    last_used_at: null,
  }]);
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'API tokens' }));
  expect(await screen.findByText('Scopes: media:read, system:admin')).toBeInTheDocument();
  expect(screen.getByText(/Last authenticated: Not authenticated this runtime/)).toBeInTheDocument();
});

test('surfaces an uncertain token creation for explicit operator revocation', async () => {
  mockAuthSession.principal = { subject: 'admin', role: 'admin', scopes: [] };
  listBearerTokens.mockResolvedValueOnce([]).mockResolvedValueOnce([{
    token_id: 'token-uncertain',
    name: 'Uncertain issue',
    subject: 'api-client:admin',
    scopes: ['media:read'],
    state: 'active',
    created_at: '2026-07-27T10:00:00Z',
    expires_at: '2026-10-25T10:00:00Z',
    revoked_at: null,
    last_used_at: null,
  }]);
  createBearerToken.mockRejectedValue(new Error('response lost'));
  renderDialog();

  fireEvent.click(screen.getByRole('tab', { name: 'API tokens' }));
  await screen.findByText('No API tokens yet.');
  fireEvent.click(screen.getByRole('button', { name: 'Create API token' }));
  fireEvent.change(screen.getByRole('textbox', { name: 'Token name' }), {
    target: { value: 'Uncertain issue' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Create' }));

  expect(await screen.findByText(/creation result is uncertain/i)).toBeInTheDocument();
  expect(screen.getByRole('listitem', { name: 'API token Uncertain issue' })).toBeInTheDocument();
  expect(screen.queryByLabelText('One-time token secret')).not.toBeInTheDocument();
});

test('keeps the dialog content free of horizontal overflow', () => {
  renderDialog();

  expect(screen.getByTestId('account-dialog-content')).toHaveStyle({
    overflowX: 'hidden',
  });
});
