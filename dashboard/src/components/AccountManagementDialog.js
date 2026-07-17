import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  List,
  ListItem,
  MenuItem,
  Select,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import KeyIcon from '@mui/icons-material/Key';
import PersonAddAltIcon from '@mui/icons-material/PersonAddAlt';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import { useAuthSession } from '../context/AuthSessionContext';
import {
  BROWSER_USER_ROLES,
  changeOwnPassword,
  createBrowserUser,
  deleteBrowserUser,
  listBrowserUsers,
  sessionPayloadFromPasswordChange,
  updateBrowserUser,
} from '../services/browserAccountApi';

const emptyPasswordForm = () => ({ current: '', next: '', confirm: '' });
const emptyCreateForm = () => ({
  username: '',
  role: 'operator',
  password: '',
  confirm: '',
  enabled: true,
});

const apiErrorMessage = (error, fallback) => {
  const detail = error?.data?.detail;
  const message = (
    (typeof detail === 'object' && detail?.message)
    || (typeof detail === 'string' && detail)
    || error?.data?.message
    || error?.data?.error
    || error?.message
    || fallback
  );
  const code = error?.data?.code || (typeof detail === 'object' ? detail?.code : null);
  return code && !String(message).includes(code) ? `${message} (${code})` : message;
};

const PasswordInput = ({ label, value, onChange, autoComplete, disabled, error, helperText }) => (
  <TextField
    label={label}
    type="password"
    value={value}
    onChange={onChange}
    autoComplete={autoComplete}
    disabled={disabled}
    error={error}
    helperText={helperText}
    required
    fullWidth
    size="small"
    inputProps={{ maxLength: 4096 }}
  />
);

const OwnPasswordPanel = ({ onMessage }) => {
  const {
    authOperationIsCurrent,
    captureAuthOperationGeneration,
    logout,
    refreshSession,
    replaceSession,
    replaceSessionIfCurrent,
  } = useAuthSession();
  const [form, setForm] = useState(emptyPasswordForm);
  const [pending, setPending] = useState(false);
  const mismatch = Boolean(form.confirm && form.next !== form.confirm);

  const changeField = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    if (pending || !form.current || !form.next || mismatch) return;

    setPending(true);
    onMessage(null);
    const operationGeneration = captureAuthOperationGeneration();
    let payload;
    try {
      payload = await changeOwnPassword({
        currentPassword: form.current,
        newPassword: form.next,
      });
    } catch (error) {
      onMessage({
        severity: 'error',
        text: apiErrorMessage(error, 'Password change failed.'),
      });
      setPending(false);
      return;
    }

    setForm(emptyPasswordForm());
    try {
      const replacementSession = sessionPayloadFromPasswordChange(payload);
      if (replacementSession) {
        const installed = replaceSessionIfCurrent(
          replacementSession,
          operationGeneration
        );
        if (!installed) {
          // The response may have replaced the HttpOnly cookie after logout.
          // Install its CSRF state only long enough to revoke that late session.
          replaceSession(replacementSession);
          await logout();
          onMessage({
            severity: 'warning',
            text: 'Password changed after the session ended. Sign in with the new password.',
          });
          return;
        }
      } else {
        if (!authOperationIsCurrent(operationGeneration)) {
          try {
            await refreshSession({ silent: true });
          } finally {
            await logout();
          }
          onMessage({
            severity: 'warning',
            text: 'Password changed after the session ended. Sign in with the new password.',
          });
          return;
        }
        await refreshSession({ silent: true });
      }
      onMessage({ severity: 'success', text: 'Password changed.' });
    } catch {
      onMessage({
        severity: 'warning',
        text: 'Password changed, but the session could not be refreshed. Sign in again.',
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <Box component="form" onSubmit={submit} sx={{ py: 0.5 }}>
      <Stack spacing={2} sx={{ maxWidth: 520 }}>
        <Typography variant="body2" color="text.secondary">
          Change the password for the signed-in account.
        </Typography>
        <PasswordInput
          label="Current password"
          value={form.current}
          onChange={changeField('current')}
          autoComplete="current-password"
          disabled={pending}
        />
        <PasswordInput
          label="New password"
          value={form.next}
          onChange={changeField('next')}
          autoComplete="new-password"
          disabled={pending}
        />
        <PasswordInput
          label="Confirm new password"
          value={form.confirm}
          onChange={changeField('confirm')}
          autoComplete="new-password"
          disabled={pending}
          error={mismatch}
          helperText={mismatch ? 'Passwords do not match.' : ' '}
        />
        <Box>
          <Button
            type="submit"
            variant="contained"
            startIcon={pending ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
            disabled={pending || !form.current || !form.next || !form.confirm || mismatch}
          >
            Change password
          </Button>
        </Box>
      </Stack>
    </Box>
  );
};

const CreateUserPanel = ({ pending, onCancel, onCreate }) => {
  const [form, setForm] = useState(emptyCreateForm);
  const mismatch = Boolean(form.confirm && form.password !== form.confirm);
  const changeField = (field) => (event) => {
    const value = field === 'enabled' ? event.target.checked : event.target.value;
    setForm((current) => ({ ...current, [field]: value }));
  };

  const submit = (event) => {
    event.preventDefault();
    if (!form.username.trim() || !form.password || mismatch) return;
    onCreate({
      username: form.username.trim(),
      role: form.role,
      password: form.password,
      enabled: form.enabled,
    });
  };

  return (
    <Box component="form" onSubmit={submit} sx={{ pt: 2 }}>
      <Typography variant="subtitle2" gutterBottom>Create account</Typography>
      <Stack spacing={1.5}>
        <TextField
          label="Username"
          value={form.username}
          onChange={changeField('username')}
          autoComplete="off"
          disabled={pending}
          required
          fullWidth
          size="small"
          inputProps={{ maxLength: 120 }}
        />
        <FormControl fullWidth size="small" disabled={pending}>
          <InputLabel id="new-account-role-label">Role</InputLabel>
          <Select
            labelId="new-account-role-label"
            label="Role"
            value={form.role}
            onChange={changeField('role')}
          >
            {BROWSER_USER_ROLES.map((role) => (
              <MenuItem key={role} value={role}>{role}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <PasswordInput
          label="Initial password"
          value={form.password}
          onChange={changeField('password')}
          autoComplete="new-password"
          disabled={pending}
        />
        <PasswordInput
          label="Confirm initial password"
          value={form.confirm}
          onChange={changeField('confirm')}
          autoComplete="new-password"
          disabled={pending}
          error={mismatch}
          helperText={mismatch ? 'Passwords do not match.' : ' '}
        />
        <FormControlLabel
          control={(
            <Switch
              checked={form.enabled}
              onChange={changeField('enabled')}
              disabled={pending}
              inputProps={{ 'aria-label': 'Enable new account' }}
            />
          )}
          label="Enabled"
        />
        <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
          <Button onClick={onCancel} disabled={pending}>Cancel</Button>
          <Button
            type="submit"
            variant="contained"
            startIcon={<PersonAddAltIcon />}
            disabled={pending || !form.username.trim() || !form.password || !form.confirm || mismatch}
          >
            Create
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
};

const AdminUsersPanel = ({ onMessage }) => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const [resetPassword, setResetPassword] = useState({ next: '', confirm: '' });
  const loadGeneration = useRef(0);

  const refreshUsers = useCallback(async () => {
    const generation = loadGeneration.current + 1;
    loadGeneration.current = generation;
    setLoading(true);
    try {
      const records = await listBrowserUsers();
      if (loadGeneration.current === generation) {
        setUsers([...records].sort((left, right) => left.username.localeCompare(right.username)));
      }
      return { ok: true };
    } catch (error) {
      if (loadGeneration.current === generation) {
        onMessage({
          severity: 'error',
          text: apiErrorMessage(error, 'Unable to load browser accounts.'),
        });
      }
      return { ok: false, error };
    } finally {
      if (loadGeneration.current === generation) setLoading(false);
    }
  }, [onMessage]);

  useEffect(() => {
    refreshUsers();
    return () => {
      loadGeneration.current += 1;
    };
  }, [refreshUsers]);

  const runMutation = async (operation, successText) => {
    if (pending) return;
    setPending(true);
    onMessage(null);
    try {
      await operation();
      setConfirmation(null);
      setResetPassword({ next: '', confirm: '' });
      setShowCreate(false);
      const refreshResult = await refreshUsers();
      if (refreshResult.ok) {
        onMessage({ severity: 'success', text: successText });
      } else {
        onMessage({
          severity: 'warning',
          text: `${successText} Account list refresh failed; refresh before another change.`,
        });
      }
    } catch (error) {
      onMessage({
        severity: 'error',
        text: apiErrorMessage(error, 'Account update failed.'),
      });
    } finally {
      setPending(false);
    }
  };

  const createUser = (record) => runMutation(
    () => createBrowserUser(record),
    `Account ${record.username} created.`
  );

  const confirmMutation = () => {
    if (!confirmation) return;
    if (confirmation.kind === 'delete') {
      runMutation(
        () => deleteBrowserUser(confirmation.username),
        `Account ${confirmation.username} deleted.`
      );
      return;
    }
    if (confirmation.kind === 'reset') {
      if (!resetPassword.next || resetPassword.next !== resetPassword.confirm) return;
      runMutation(
        () => updateBrowserUser(confirmation.username, { password: resetPassword.next }),
        `Password reset for ${confirmation.username}.`
      );
      return;
    }
    runMutation(
      () => updateBrowserUser(confirmation.username, confirmation.changes),
      `Account ${confirmation.username} updated.`
    );
  };

  const openConfirmation = (nextConfirmation) => {
    setShowCreate(false);
    setResetPassword({ next: '', confirm: '' });
    setConfirmation(nextConfirmation);
    onMessage(null);
  };

  const resetMismatch = Boolean(
    resetPassword.confirm && resetPassword.next !== resetPassword.confirm
  );

  return (
    <Stack spacing={1.5} sx={{ minWidth: 0 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Typography variant="body2" color="text.secondary">
          Browser accounts
        </Typography>
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Refresh accounts">
            <span>
              <IconButton
                size="small"
                aria-label="Refresh accounts"
                onClick={refreshUsers}
                disabled={loading || pending}
              >
                <RefreshIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Create account">
            <span>
              <IconButton
                size="small"
                aria-label="Create account"
                onClick={() => {
                  setConfirmation(null);
                  setShowCreate(true);
                  onMessage(null);
                }}
                disabled={pending}
              >
                <AddIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
      </Stack>

      {loading ? (
        <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 96 }}>
          <CircularProgress size={24} aria-label="Loading accounts" />
        </Box>
      ) : (
        <List disablePadding aria-label="Browser accounts" sx={{ minWidth: 0 }}>
          {users.map((user, index) => (
            <React.Fragment key={user.username}>
              {index > 0 && <Divider component="li" />}
              <ListItem
                disableGutters
                aria-label={`Account ${user.username}`}
                sx={{
                  alignItems: 'flex-start',
                  display: 'block',
                  py: 1.25,
                  minWidth: 0,
                }}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  alignItems={{ xs: 'stretch', sm: 'center' }}
                  spacing={1}
                  sx={{ minWidth: 0 }}
                >
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={600} noWrap title={user.username}>
                      {user.username}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {user.enabled ? 'Enabled' : 'Disabled'}
                    </Typography>
                  </Box>
                  <Stack
                    direction="row"
                    alignItems="center"
                    spacing={0.5}
                    sx={{ minWidth: 0, flexWrap: 'wrap' }}
                  >
                    <FormControl size="small" sx={{ width: 122 }} disabled={pending}>
                      <InputLabel id={`role-${user.username}`}>Role</InputLabel>
                      <Select
                        labelId={`role-${user.username}`}
                        label="Role"
                        value={user.role}
                        onChange={(event) => openConfirmation({
                          kind: 'update',
                          username: user.username,
                          changes: { role: event.target.value },
                          summary: `Change ${user.username} role to ${event.target.value}?`,
                        })}
                      >
                        {BROWSER_USER_ROLES.map((role) => (
                          <MenuItem key={role} value={role}>{role}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    <Tooltip title={user.enabled ? 'Disable account' : 'Enable account'}>
                      <Switch
                        checked={user.enabled}
                        onChange={() => openConfirmation({
                          kind: 'update',
                          username: user.username,
                          changes: { enabled: !user.enabled },
                          summary: `${user.enabled ? 'Disable' : 'Enable'} ${user.username}?`,
                        })}
                        disabled={pending}
                        inputProps={{
                          'aria-label': `${user.enabled ? 'Disable' : 'Enable'} ${user.username}`,
                        }}
                      />
                    </Tooltip>
                    <Tooltip title="Reset password">
                      <span>
                        <IconButton
                          size="small"
                          aria-label={`Reset password for ${user.username}`}
                          onClick={() => openConfirmation({
                            kind: 'reset',
                            username: user.username,
                            summary: `Reset password for ${user.username}`,
                          })}
                          disabled={pending}
                        >
                          <KeyIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                    <Tooltip title="Delete account">
                      <span>
                        <IconButton
                          size="small"
                          color="error"
                          aria-label={`Delete ${user.username}`}
                          onClick={() => openConfirmation({
                            kind: 'delete',
                            username: user.username,
                            summary: `Delete ${user.username}?`,
                          })}
                          disabled={pending}
                        >
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  </Stack>
                </Stack>
              </ListItem>
            </React.Fragment>
          ))}
          {users.length === 0 && (
            <ListItem disableGutters>
              <Typography variant="body2" color="text.secondary">No accounts returned.</Typography>
            </ListItem>
          )}
        </List>
      )}

      {(showCreate || confirmation) && <Divider />}

      {showCreate && (
        <CreateUserPanel
          pending={pending}
          onCancel={() => setShowCreate(false)}
          onCreate={createUser}
        />
      )}

      {confirmation && (
        <Stack spacing={1.5} sx={{ pt: 0.5 }}>
          <Alert severity="warning">{confirmation.summary}</Alert>
          {confirmation.kind === 'reset' && (
            <Stack spacing={1.5}>
              <PasswordInput
                label="New password"
                value={resetPassword.next}
                onChange={(event) => setResetPassword((current) => ({
                  ...current,
                  next: event.target.value,
                }))}
                autoComplete="new-password"
                disabled={pending}
              />
              <PasswordInput
                label="Confirm new password"
                value={resetPassword.confirm}
                onChange={(event) => setResetPassword((current) => ({
                  ...current,
                  confirm: event.target.value,
                }))}
                autoComplete="new-password"
                disabled={pending}
                error={resetMismatch}
                helperText={resetMismatch ? 'Passwords do not match.' : ' '}
              />
            </Stack>
          )}
          <Stack direction="row" spacing={1} justifyContent="flex-end" flexWrap="wrap" useFlexGap>
            <Button onClick={() => setConfirmation(null)} disabled={pending}>Cancel</Button>
            <Button
              color={confirmation.kind === 'delete' ? 'error' : 'primary'}
              variant="contained"
              onClick={confirmMutation}
              disabled={
                pending
                || (confirmation.kind === 'reset'
                  && (!resetPassword.next || !resetPassword.confirm || resetMismatch))
              }
            >
              Confirm
            </Button>
          </Stack>
        </Stack>
      )}
    </Stack>
  );
};

const AccountManagementDialog = ({ open, onClose }) => {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const { principal } = useAuthSession();
  const isAdmin = principal?.role === 'admin';
  const [tab, setTab] = useState('password');
  const [message, setMessage] = useState(null);

  useEffect(() => {
    if (!open) {
      setTab('password');
      setMessage(null);
    }
  }, [open]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullScreen={fullScreen}
      fullWidth
      maxWidth="sm"
      aria-labelledby="account-dialog-title"
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 680 },
          maxWidth: '100%',
          maxHeight: { xs: '100dvh', sm: 'calc(100dvh - 48px)' },
          m: { xs: 0, sm: 3 },
          overflow: 'hidden',
        },
      }}
    >
      <DialogTitle id="account-dialog-title" sx={{ pr: 6 }}>
        Account
        <IconButton
          aria-label="Close account dialog"
          onClick={onClose}
          sx={{ position: 'absolute', right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      {isAdmin && (
        <Tabs
          value={tab}
          onChange={(_, value) => {
            setTab(value);
            setMessage(null);
          }}
          variant="fullWidth"
          aria-label="Account sections"
        >
          <Tab value="password" label="My password" />
          <Tab value="users" label="Users" />
        </Tabs>
      )}

      <DialogContent
        dividers
        data-testid="account-dialog-content"
        sx={{ overflowX: 'hidden', minHeight: { xs: 0, sm: 360 } }}
      >
        {message && (
          <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>
            {message.text}
          </Alert>
        )}
        {tab === 'users' && isAdmin ? (
          <AdminUsersPanel onMessage={setMessage} />
        ) : (
          <OwnPasswordPanel onMessage={setMessage} />
        )}
      </DialogContent>

      <DialogActions sx={{ px: 2, flexWrap: 'wrap', overflowX: 'hidden' }}>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default AccountManagementDialog;
